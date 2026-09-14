"""
ASR experiment: Whisper `base` vs `large-v3`, with and without the rich_v1
script-aware compression fix, on the practical-check material.

    python -m evaluation.experiments.asr_model_compare [--repeats 2] [--models base large-v3]

Isolated from production: builds AsrProfile variants in memory, calls
transcribe_rich directly, never changes config or the pipeline.

Each (model, variant) group runs in its own subprocess so peak RSS includes the
model load and nothing else. Results are written to
<eval_dir>/experiments/asr_model_compare/<timestamp>/ (results.json, report.md).

Material (built during the ASR stage, see EV-2.3..2.5):
  en     smoke-en-tts.mp4        English Windows TTS, script looped twice (123 s)
  hi     check-hi-read.wav       8 s synthetic music intro + 6 IndicTTS Hindi read-speech clips
  ta     check-ta-read.wav       8 s synthetic music intro + 6 IndicTTS Tamil read-speech clips
  mixed  check-mixed-hi-en-ta.wav  2 Hindi clips → 22 s English TTS → 2 Tamil clips
All clean speech: results describe behaviour on clean input, not podcast accuracy.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import asdict, replace
from pathlib import Path

from evaluation.storage import eval_dir, write_json

EN_SCRIPT = [
    "Welcome back to the show. Today we are talking about why most startups fail in their first year.",
    "Here's the thing nobody tells you about hiring. The first ten people decide the culture forever.",
    "So why would anyone build a company that way? Honestly, I think most advice on the internet is useless.",
    "We tried that, and it failed twice. And then we lost everything in about three weeks.",
    "That was the moment I realised the product was the problem, not the market.",
    "What would you do differently if you started today? I would talk to customers before writing a single line of code.",
    "There is actually one thing nobody talks about, and it is money. Let me explain.",
    "The real reason is that founders are afraid of hearing no. So they avoid the conversation entirely.",
    "If you remember one thing from this episode, remember this. Distribution beats product, almost every time.",
]
MUSIC_INTRO_S = 8.0
GAP_S = 1.2

VARIANTS = {
    # name: (base profile, overrides)
    "rich_v1": ("rich_v1", {}),
    "rich_v1_nofix": ("rich_v1", {"script_aware_compression": False}),
    "legacy": ("legacy", {}),
}


# ---------------------------------------------------------------------------
# text metrics
# ---------------------------------------------------------------------------

def normalise(text: str) -> str:
    """NFC; drop punctuation, symbols and whitespace; keep letters, marks and digits."""
    text = unicodedata.normalize("NFC", text).lower()
    return "".join(ch for ch in text if unicodedata.category(ch)[0] in ("L", "M", "N"))


def cer(reference: str, hypothesis: str) -> float:
    r, h = normalise(reference), normalise(hypothesis)
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return round(prev[-1] / max(1, len(r)), 4)


def script_share(text: str, script: str) -> float | None:
    from services.transcript_quality import script_shares
    shares = script_shares(text)
    return shares.get(script, 0.0) if shares else None


# ---------------------------------------------------------------------------
# material
# ---------------------------------------------------------------------------

def material() -> dict:
    root = eval_dir()
    media = root / "media"
    scratch = root / "scratch" / "asr_check"
    refs = json.loads((scratch / "references.json").read_text(encoding="utf-8"))

    def clip_seconds(name: str) -> float:
        import wave
        with wave.open(str(scratch / name)) as w:
            return w.getnframes() / w.getframerate()

    hi0, hi7 = clip_seconds("hi_0.wav"), clip_seconds("hi_7.wav")
    ta0, ta7 = clip_seconds("ta_0.wav"), clip_seconds("ta_7.wav")
    en_start = hi0 + GAP_S + hi7 + GAP_S
    ta_start = en_start + 22.0 + GAP_S
    return {
        "en": {"path": str(media / "smoke-en-tts.mp4"), "reference": " ".join(EN_SCRIPT * 2),
               "script": "latin", "intro_s": 0.0},
        "hi": {"path": str(media / "check-hi-read.wav"), "reference": " ".join(r["text"] for r in refs["hi"]),
               "script": "devanagari", "intro_s": MUSIC_INTRO_S},
        "ta": {"path": str(media / "check-ta-read.wav"), "reference": " ".join(r["text"] for r in refs["ta"]),
               "script": "tamil", "intro_s": MUSIC_INTRO_S},
        "mixed": {"path": str(media / "check-mixed-hi-en-ta.wav"), "intro_s": 0.0,
                  "portions": [
                      {"name": "hi", "start": 0.0, "end": en_start - GAP_S / 2, "script": "devanagari",
                       "reference": " ".join(r["text"] for r in refs["hi"][:2])},
                      {"name": "en", "start": en_start - GAP_S / 2, "end": ta_start - GAP_S / 2, "script": "latin",
                       "reference": None},
                      {"name": "ta", "start": ta_start - GAP_S / 2, "end": 10_000.0, "script": "tamil",
                       "reference": " ".join(r["text"] for r in refs["ta"][:2])},
                  ]},
    }


# ---------------------------------------------------------------------------
# per-run measurements
# ---------------------------------------------------------------------------

def _units(transcript):
    """(midpoint_time, text) units: words when available, else segments."""
    units = []
    for s in transcript.segments:
        if s.words:
            units.extend(((w.start + w.end) / 2, w.text) for w in s.words)
        else:
            units.append(((s.start + s.end) / 2, " " + s.text))
    return units


def measure(transcript, item: dict) -> dict:
    q, lang = transcript.quality, transcript.language
    text = " ".join(s.text for s in transcript.segments)
    units = _units(transcript)
    words = [w for s in transcript.segments for w in (s.words or [])]

    result = {
        "text": text,
        "language": lang.language,
        "language_probability": lang.probability,
        "language_top3": lang.top[:3],
        "language_probes": [(p.start, p.language, p.probability) for p in lang.probes],
        "language_uncertain": lang.uncertain,
        "language_reasons": lang.reasons,
        "quality_status": q.status,
        "quality_reasons": q.reasons,
        "flag_counts": q.flag_counts,
        "segments": q.segment_count,
        "hallucination_suspects": q.hallucination_suspect_segments,
        "timing_suspects": q.timing_suspect_segments,
        "low_confidence_segments": q.low_confidence_segments,
        "text_in_music_intro": "".join(t for mid, t in units if mid < item["intro_s"]).strip(),
        "speech_seconds": q.speech_seconds,
        "speech_coverage": q.speech_coverage,
        "text_outside_speech_seconds": q.text_outside_speech_seconds,
        "duration_after_vad": transcript.asr.get("duration_after_vad"),
        "decode_overrides": transcript.asr.get("decode_overrides"),
        "temperatures": sorted({s.temperature for s in transcript.segments if s.temperature is not None}),
        "timings": transcript.timings,
        "rtf": round(transcript.timings["total_s"] / transcript.audio_duration, 3) if transcript.audio_duration else None,
    }
    if words:
        starts = [w.start for w in words]
        durations = sorted(w.end - w.start for w in words)
        result["words"] = {
            "count": len(words),
            "in_speech_fraction": round(sum(1 for w in words if w.in_speech) / len(words), 3),
            "non_monotonic": sum(1 for a, b in zip(starts, starts[1:]) if b < a),
            "zero_or_negative": sum(1 for d in durations if d <= 0),
            "median_duration_s": round(durations[len(durations) // 2], 3),
            "max_duration_s": round(durations[-1], 3),
            "mean_probability": round(sum(w.probability or 0 for w in words) / len(words), 3),
        }
    else:
        result["words"] = None

    if "portions" in item:
        portions = {}
        for portion in item["portions"]:
            ptext = "".join(t for mid, t in units if portion["start"] <= mid < portion["end"])
            portions[portion["name"]] = {
                "cer": cer(portion["reference"], ptext) if portion["reference"] else None,
                "expected_script_share": script_share(ptext, portion["script"]),
                "chars": len(normalise(ptext)),
                "text": ptext.strip()[:200],
            }
        result["portions"] = portions
    else:
        result["cer"] = cer(item["reference"], text)
        result["expected_script_share"] = script_share(text, item["script"])
    return result


# ---------------------------------------------------------------------------
# worker (one model × variant per process)
# ---------------------------------------------------------------------------

def worker(model: str, variant: str, repeats: int, out: Path) -> None:
    import psutil
    from services import transcription

    proc = psutil.Process()
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()

    def sample():
        while not stop.wait(0.2):
            peak["rss"] = max(peak["rss"], proc.memory_info().rss)

    threading.Thread(target=sample, daemon=True).start()
    base_name, overrides = VARIANTS[variant]
    profile = replace(transcription.PROFILES[base_name], name=f"exp_{variant}_{model}", model=model, **overrides)

    t0 = time.perf_counter()
    if transcription.get_model(profile.model, profile.device, profile.compute_type) is None:
        raise SystemExit(f"model {model} failed to load: {transcription._model_load_error}")
    load_s = round(time.perf_counter() - t0, 2)
    rss_after_load = proc.memory_info().rss

    items = material()
    runs = []
    plan = [(name, "auto") for name in ("en", "hi", "ta", "mixed")]
    if variant == "rich_v1":
        plan += [("hi", "hi"), ("ta", "ta")]
    for name, mode in plan:
        for rep in range(repeats):
            rss_before = proc.memory_info().rss
            transcript = transcription.transcribe_rich(items[name]["path"], profile=profile, language_mode=mode)
            runs.append({"item": name, "mode": mode, "repeat": rep + 1,
                         "rss_mb_before": round(rss_before / 2**20), **measure(transcript, items[name])})
            print(f"  {model}/{variant} {name}/{mode} run {rep + 1}: "
                  f"{runs[-1].get('cer', runs[-1].get('portions'))} {runs[-1]['timings']['total_s']}s", flush=True)
    stop.set()
    write_json(out, {
        "model": model, "variant": variant, "profile": asdict(profile),
        "model_load_s": load_s, "rss_mb_after_load": round(rss_after_load / 2**20),
        "peak_rss_mb": round(max(peak["rss"], proc.memory_info().rss) / 2**20), "runs": runs,
    })


# ---------------------------------------------------------------------------
# orchestration + report
# ---------------------------------------------------------------------------

def environment() -> dict:
    import platform
    from importlib.metadata import version
    import psutil
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu": platform.processor(), "logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "packages": {p: version(p) for p in ("faster-whisper", "ctranslate2", "onnxruntime", "numpy")},
    }


def model_files() -> dict:
    from huggingface_hub import scan_cache_dir
    info = {}
    for repo in scan_cache_dir().repos:
        if repo.repo_id.startswith("Systran/faster-whisper-"):
            revisions = sorted(repo.revisions, key=lambda r: r.last_modified, reverse=True)
            info[repo.repo_id] = {
                "size_bytes": repo.size_on_disk,
                "path": str(repo.repo_path),
                "revision": revisions[0].commit_hash if revisions else None,
                "files": {f.file_name: f.size_on_disk for f in revisions[0].files} if revisions else {},
            }
    return info


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--models", nargs="+", default=["base", "large-v3"])
    ap.add_argument("--variants", nargs="+", default=["rich_v1", "rich_v1_nofix", "legacy"])
    ap.add_argument("--worker", nargs=3, metavar=("MODEL", "VARIANT", "OUT"))
    args = ap.parse_args(argv)

    if args.worker:
        model, variant, out = args.worker
        worker(model, variant, args.repeats, Path(out))
        return 0

    out_dir = eval_dir() / "experiments" / "asr_model_compare" / time.strftime("%Y%m%dT%H%M%S")
    out_dir.mkdir(parents=True)
    groups = []
    for model in args.models:
        for variant in args.variants:
            if variant == "legacy" and model != "base":
                continue  # legacy is the production reference; only meaningful with base
            out = out_dir / f"{model}__{variant}.json"
            print(f"[{model} / {variant}]", flush=True)
            started = time.perf_counter()
            subprocess.run([sys.executable, "-m", "evaluation.experiments.asr_model_compare",
                            "--repeats", str(args.repeats), "--worker", model, variant, str(out)], check=True)
            group = json.loads(out.read_text(encoding="utf-8"))
            group["wall_s"] = round(time.perf_counter() - started, 1)
            groups.append(group)

    write_json(out_dir / "results.json", {"environment": environment(), "models": model_files(), "groups": groups})
    print(f"\nresults: {out_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
