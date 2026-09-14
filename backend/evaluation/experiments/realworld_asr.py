"""
Steps 2–6 of the real-world ASR validation: rich_v1 on labelled windows.

    python -m evaluation.experiments.realworld_asr --model base [--keys ta1 en1 hi1]

Windows come from <eval_dir>/realworld/windows.json (chosen after the structure
inspection), each labelled `podcast_body` (early/middle/late) or a difficult
region (`intro_highlight`, `sponsor`, ...). Labels are never merged in reporting.

One subprocess per (model, video) so peak RSS covers exactly that video's work.
Writes <eval_dir>/realworld/asr/<model>/<key>.json plus readable
<key>.<label>.txt transcripts with absolute video timestamps.

No references exist for this audio, so the metrics are reference-free:
language decision, script mix, flags, word-timestamp sanity, VAD coverage,
untranscribed speech (VAD speech regions with almost no words), timings, RAM.
Transcript quality judgements come from reading the .txt files.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import wave
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from evaluation.storage import eval_dir, write_json

SR = 16000
EXPECTED_SCRIPT = {"en": "latin", "hi": "devanagari", "ta": "tamil"}


def cut(src: Path, start: float, duration: float, dest: Path) -> None:
    if dest.exists():
        return
    with wave.open(str(src)) as w:
        w.setpos(int(start * SR))
        frames = w.readframes(int(duration * SR))
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(frames)


def untranscribed_speech(transcript, min_region_s: float = 1.5, tolerance_s: float = 0.3) -> dict:
    """VAD speech regions (≥ min_region_s) where words cover < 20 % of the region."""
    if not transcript.speech_regions:
        return {"regions": None, "seconds": None, "examples": []}
    words = sorted((w.start - tolerance_s, w.end + tolerance_s)
                   for s in transcript.segments for w in (s.words or []))
    missing = []
    for rs, re_ in transcript.speech_regions.regions:
        length = re_ - rs
        if length < min_region_s:
            continue
        covered = 0.0
        for ws, we in words:
            if we <= rs:
                continue
            if ws >= re_:
                break
            covered += min(re_, we) - max(rs, ws)
        if covered / length < 0.2:
            missing.append((round(rs, 2), round(re_, 2)))
    return {"regions": len(missing), "seconds": round(sum(e - s for s, e in missing), 1), "examples": missing[:8]}


def measure(transcript, lang: str, window: dict) -> dict:
    from services.transcript_quality import script_shares

    q, info = transcript.quality, transcript.language
    text = " ".join(s.text for s in transcript.segments)
    words = [w for s in transcript.segments for w in (s.words or [])]
    starts = [w.start for w in words]
    durations = sorted(w.end - w.start for w in words)
    speech_s = q.speech_seconds or 0.0
    shares = script_shares(text)
    return {
        "label": window["label"], "start": window["start"], "duration": window["duration"],
        "expected_language": lang,
        "language": info.language, "language_probability": info.probability, "language_top3": info.top[:3],
        "language_probes": [(round(window["start"] + p.start), p.language, p.probability) for p in info.probes],
        "language_uncertain": info.uncertain, "language_reasons": info.reasons,
        "script_shares": shares,
        "expected_script_share": shares.get(EXPECTED_SCRIPT[lang]) if shares else None,
        "quality_status": q.status, "quality_reasons": q.reasons,
        "flag_counts": q.flag_counts, "segments": q.segment_count,
        "hallucination_suspects": q.hallucination_suspect_segments,
        "timing_suspects": q.timing_suspect_segments,
        "low_confidence_segments": q.low_confidence_segments,
        "mixed_script_segments": q.mixed_script_segments,
        "temperatures": dict(Counter(s.temperature for s in transcript.segments)),
        "words": {
            "count": len(words),
            "per_speech_minute": round(len(words) / (speech_s / 60), 1) if speech_s else None,
            "in_speech_fraction": round(sum(1 for w in words if w.in_speech) / len(words), 3) if words else None,
            "non_monotonic": sum(1 for a, b in zip(starts, starts[1:]) if b < a),
            "zero_or_negative": sum(1 for d in durations if d <= 0),
            "longer_than_2s": sum(1 for d in durations if d > 2.0),
            "median_duration_s": round(durations[len(durations) // 2], 3) if durations else None,
            "mean_probability": round(sum(w.probability or 0 for w in words) / len(words), 3) if words else None,
        },
        "speech_seconds": q.speech_seconds,
        "speech_ratio_of_window": round(speech_s / window["duration"], 3),
        "transcript_coverage": q.speech_coverage,
        "text_outside_speech_seconds": q.text_outside_speech_seconds,
        "untranscribed_speech": untranscribed_speech(transcript),
        "timings": transcript.timings,
        "rtf": round(transcript.timings["total_s"] / window["duration"], 3),
    }


def readable(transcript, window: dict) -> str:
    lines = [f"# {window['label']} {window['start']}s +{window['duration']}s  language={transcript.language.language} "
             f"p={transcript.language.probability} status={transcript.quality.status}"]
    for s in transcript.segments:
        flags = f"  {{{', '.join(s.flags)}}}" if s.flags else ""
        t0 = window["start"] + s.start
        lines.append(f"[{int(t0 // 60):3d}:{t0 % 60:05.2f}] {s.text}{flags}")
    return "\n".join(lines)


def worker(model: str, key: str, labels: list[str] | None = None) -> None:
    import psutil
    from services import transcription

    root = eval_dir() / "realworld"
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))[key]
    out_dir = root / "asr" / model
    out_dir.mkdir(parents=True, exist_ok=True)
    win_dir = root / "windows"
    win_dir.mkdir(exist_ok=True)

    proc = psutil.Process()
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()

    def sample():
        while not stop.wait(0.2):
            peak["rss"] = max(peak["rss"], proc.memory_info().rss)

    threading.Thread(target=sample, daemon=True).start()
    profile = replace(transcription.PROFILES["rich_v1"], name=f"realworld_{model}", model=model)
    t0 = time.perf_counter()
    if transcription.get_model(profile.model, profile.device, profile.compute_type) is None:
        raise SystemExit(f"model {model} failed to load: {transcription._model_load_error}")
    load_s = round(time.perf_counter() - t0, 2)

    results = []
    for window in plan["windows"]:
        if labels and window["label"] not in labels:
            continue
        clip = win_dir / f"{key}.{window['label']}.{window['start']}.wav"
        cut(root / "audio" / f"{key}.wav", window["start"], window["duration"], clip)
        started = time.perf_counter()
        transcript = transcription.transcribe_rich(str(clip), profile=profile, language_mode="auto")
        row = measure(transcript, plan["lang"], window)
        row["wall_s"] = round(time.perf_counter() - started, 1)
        results.append(row)
        (out_dir / f"{key}.{window['label']}.txt").write_text(readable(transcript, window), encoding="utf-8")
        write_json(out_dir / f"{key}.{window['label']}.transcript.json", transcript.to_dict())
        print(f"  {model} {key} {window['label']:>16} lang={row['language']}({row['language_probability']}) "
              f"script={row['expected_script_share']} suspects={row['hallucination_suspects']} "
              f"cov={row['transcript_coverage']} missing={row['untranscribed_speech']['seconds']}s "
              f"rtf={row['rtf']}", flush=True)
    stop.set()
    write_json(out_dir / f"{key}.json", {
        "model": model, "key": key, "lang": plan["lang"], "body_start": plan["body_start"],
        "model_load_s": load_s, "peak_rss_mb": round(max(peak["rss"], proc.memory_info().rss) / 2**20),
        "windows": results,
    })


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base")
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--worker", nargs=2, metavar=("MODEL", "KEY"))
    ap.add_argument("--labels", nargs="*", help="only these window labels")
    args = ap.parse_args(argv)
    if args.worker:
        worker(*args.worker, labels=args.labels)
        return 0
    plan = json.loads((eval_dir() / "realworld" / "windows.json").read_text(encoding="utf-8"))
    for key in plan:
        if args.keys and key not in args.keys:
            continue
        print(f"[{args.model} / {key}]", flush=True)
        cmd = [sys.executable, "-m", "evaluation.experiments.realworld_asr", "--worker", args.model, key]
        if args.labels:
            cmd += ["--labels", *args.labels]
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
