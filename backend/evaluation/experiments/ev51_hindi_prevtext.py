"""
EV-5.1 — held-out Hindi prediction: does the language-probe signal predict whether
a Hindi/Hinglish file should decode its first pass with previous-text ON or OFF?

    python -m evaluation.experiments.ev51_hindi_prevtext

Two arms, FIRST PASS ONLY (no adaptive retry, no region retry, no policy change):
  A  hi_v1 as currently defined          (large-v3, manual language=hi, prevtext ON)
  B  same profile with condition_on_previous_text=False

Windows: hi3 body_early/middle/late (held out) + hi2 body_early/body_late.
Probes are instrumentation only: the same window selection production uses, with the
top-3 probability distribution kept (production discards it). Decoding is untouched.

Output: <eval_dir>/realworld/ev51/
"""
from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from evaluation.experiments.realworld_asr import cut
from evaluation.storage import eval_dir, write_json

SR = 16000
CASES = [("hi3", "body_early"), ("hi3", "body_middle"), ("hi3", "body_late"),
         ("hi2", "body_early"), ("hi2", "body_late")]
PROBE_WINDOW_S = 30.0
PROBE_COUNT = 8


# ---------------------------------------------------------------------------
# probe instrumentation (mirrors services.transcription._probe_languages windowing)
# ---------------------------------------------------------------------------

def probe_windows(model, audio, speech, count: int = PROBE_COUNT) -> list[dict]:
    import math

    regions = speech.regions if speech is not None and speech.regions else [(0.0, len(audio) / SR)]
    total_speech = sum(e - s for s, e in regions)
    if total_speech < 1.0:
        return []
    if total_speech <= PROBE_WINDOW_S * count:
        anchors = [i * PROBE_WINDOW_S for i in range(math.ceil(total_speech / PROBE_WINDOW_S))]
    else:
        stride = (total_speech - PROBE_WINDOW_S) / (count - 1) if count > 1 else 0.0
        anchors = [i * stride for i in range(count)]

    probes = []
    for anchor in anchors:
        pieces, gathered, speech_before = [], 0.0, 0.0
        first_start = last_end = None
        for s, e in regions:
            length = e - s
            if speech_before + length <= anchor:
                speech_before += length
                continue
            start = s + max(0.0, anchor - speech_before)
            speech_before += length
            take = min(e - start, PROBE_WINDOW_S - gathered)
            if take <= 0:
                break
            pieces.append(audio[int(start * SR):int((start + take) * SR)])
            gathered += take
            first_start = start if first_start is None else first_start
            last_end = start + take
            if gathered >= PROBE_WINDOW_S:
                break
        if gathered < 1.0:
            continue
        language, probability, all_probs = model.detect_language(audio=np.concatenate(pieces))
        top3 = [[code, round(float(p), 4)] for code, p in (all_probs or [])[:3]]
        probes.append({"start": round(first_start, 2), "end": round(last_end, 2),
                       "language": language, "probability": round(float(probability), 4),
                       "top3": top3})
    return probes


def probe_summary(probes: list[dict]) -> dict:
    if not probes:
        return {"count": 0}
    ps = [p["probability"] for p in probes]
    mean = sum(ps) / len(ps)
    var = sum((x - mean) ** 2 for x in ps) / len(ps)
    return {
        "count": len(probes),
        "min_probability": round(min(ps), 4),
        "mean_probability": round(mean, 4),
        "std_probability": round(var ** 0.5, 4),
        "english_argmax": sum(1 for p in probes if p["language"] == "en"),
        "english_argmax_share": round(sum(1 for p in probes if p["language"] == "en") / len(probes), 3),
        "argmax_languages": sorted({p["language"] for p in probes}),
    }


# ---------------------------------------------------------------------------
# outcome metrics
# ---------------------------------------------------------------------------

def outcome(transcript, wall_s: float) -> dict:
    from services import transcript_quality

    segs = transcript.segments
    speech_s = transcript.speech_regions.speech_seconds if transcript.speech_regions else None
    trusted = [s for s in segs if s.text and not transcript_quality.segment_suspicion(s)]
    trusted_words = sum(len(s.words) if s.words is not None else len(s.text.split()) for s in trusted)
    all_words = sum(len(s.words) if s.words is not None else len(s.text.split()) for s in segs)
    scripts = transcript_quality.script_shares(" ".join(s.text for s in segs))
    status, reasons, spans = transcript_quality.gate(transcript)
    return {
        "speech_seconds": speech_s,
        "trusted_words": trusted_words,
        "all_words": all_words,
        "trusted_words_per_speech_minute": round(trusted_words / (speech_s / 60), 1) if speech_s else None,
        "latin_share": round(scripts.get("latin", 0.0), 3),
        "devanagari_share": round(scripts.get("devanagari", 0.0), 3),
        "scripts": scripts,
        "loop_seconds": round(sum(s.end - s.start for s in segs if "repeated_text" in s.flags), 1),
        "suspicious_segments": sum(1 for s in segs if transcript_quality.segment_suspicion(s)),
        "hallucination_suspects": sum(1 for s in segs if s.hallucination_suspect),
        "segments": len(segs),
        "gate_status": status,
        "gate_reasons": reasons,
        "gate_spans": len(spans),
        "transcript_status": transcript.quality.status,
        "wall_s": round(wall_s, 1),
        "rtf": round(wall_s / transcript.audio_duration, 3) if transcript.audio_duration else None,
        "decode_s": transcript.timings.get("decode_s"),
        "decode_rtf": round(transcript.timings["decode_s"] / transcript.audio_duration, 3)
        if transcript.timings.get("decode_s") and transcript.audio_duration else None,
        "temperatures": {str(k): v for k, v in sorted(
            {s.temperature: sum(1 for x in segs if x.temperature == s.temperature) for s in segs}.items())},
    }


def readable(transcript, offset: float) -> str:
    def clock(x):
        x += offset
        return f"{int(x // 60)}:{x % 60:05.2f}"
    lines = []
    for s in transcript.segments:
        flags = f"  {{{', '.join(s.flags)}}}" if s.flags else ""
        lines.append(f"[{clock(s.start)}] {s.text}{flags}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    import psutil
    from services import transcription

    root = eval_dir() / "realworld"
    out = root / "ev51"
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))

    arm_a = transcription.PROFILES["hi_v1"]
    arm_b = replace(arm_a, name="hi_v1_prevtext_off", condition_on_previous_text=False)
    assert arm_a.condition_on_previous_text is True, "arm A must be previous-text ON"
    assert arm_b.condition_on_previous_text is False
    arms = [("A_on", arm_a), ("B_off", arm_b)]

    model = transcription.get_model(arm_a.model, arm_a.device, arm_a.compute_type)
    if model is None:
        print(f"FAILED: {arm_a.model} could not be loaded: {transcription._model_load_error}")
        return 1

    proc = psutil.Process()
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()

    def sample():
        while not stop.wait(0.2):
            peak["rss"] = max(peak["rss"], proc.memory_info().rss)

    threading.Thread(target=sample, daemon=True).start()

    rows = []
    for key, label in CASES:
        window = next(w for w in plan[key]["windows"] if w["label"] == label)
        clip = root / "windows" / f"{key}.{label}.{window['start']}.wav"
        cut(root / "audio" / f"{key}.wav", window["start"], window["duration"], clip)

        # Prepared once per window: identical VAD + audio for both arms.
        prepared = transcription.prepare_audio(str(clip), model, probe_count=0)
        probes = probe_windows(model, prepared.audio, prepared.speech)
        summary = probe_summary(probes)
        write_json(out / f"{key}.{label}.probes.json",
                   {"file": key, "window": label, "start": window["start"],
                    "probe_model": arm_a.model, "summary": summary, "probes": probes})
        print(f"  {key}/{label} probes: en_argmax={summary.get('english_argmax')}/{summary.get('count')} "
              f"min={summary.get('min_probability')} mean={summary.get('mean_probability')} "
              f"std={summary.get('std_probability')}", flush=True)

        for arm_name, profile in arms:
            started = time.perf_counter()
            try:
                transcript = transcription.transcribe_rich(
                    str(clip), profile=profile, language_mode="hi", prepared=prepared)
            except Exception as exc:
                print(f"  FAILED {key}/{label} {arm_name}: {type(exc).__name__}: {exc}", flush=True)
                rows.append({"file": key, "window": label, "arm": arm_name,
                             "error": f"{type(exc).__name__}: {exc}"})
                continue
            row = {
                "file": key, "window": label, "window_start": window["start"],
                "arm": arm_name,
                "provenance": {
                    "profile": profile.name, "model": profile.model,
                    "condition_on_previous_text": profile.condition_on_previous_text,
                    "language_mode": "hi", "decoded_language": transcript.language.language,
                    "temperature": list(profile.temperature),
                    "compression_ratio_threshold": profile.compression_ratio_threshold,
                    "word_timestamps": profile.word_timestamps, "vad_filter": profile.vad_filter,
                    "first_pass_only": True, "retries": 0,
                    "asr": transcript.asr.get("versions"),
                },
                "probe_summary": summary,
                **outcome(transcript, time.perf_counter() - started),
                "peak_rss_mb_so_far": round(peak["rss"] / 2**20),
            }
            rows.append(row)
            stem = f"{key}.{label}.{arm_name}"
            write_json(out / f"{stem}.json", row)
            write_json(out / f"{stem}.transcript.json", transcript.to_dict())
            (out / f"{stem}.txt").write_text(readable(transcript, window["start"]), encoding="utf-8")
            print(f"  {key}/{label} {arm_name}: latin={row['latin_share']} deva={row['devanagari_share']} "
                  f"trusted_wpm={row['trusted_words_per_speech_minute']} loops={row['loop_seconds']}s "
                  f"gate={row['gate_status']} rtf={row['rtf']}", flush=True)

    stop.set()
    write_json(out / "ev51_summary.json", {"cases": rows, "peak_rss_mb": round(peak["rss"] / 2**20)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
