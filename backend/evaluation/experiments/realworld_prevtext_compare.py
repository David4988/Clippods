"""
Real-podcast comparison: does condition_on_previous_text=False fix large-v3 on
Hindi/Tamil?

    python -m evaluation.experiments.realworld_prevtext_compare [--configs ...]

Configs (all rich_v1 path: word timestamps, VAD, script-aware compression fix):
  base_rich_v1            base, current rich_v1
  large_v3_fix            large-v3, current rich_v1 (condition_on_previous_text=True)
  large_v3_prevtext_off   large-v3, rich_v1 + condition_on_previous_text=False

Main windows: one continuous 5-minute podcast-body window per video (ta1, ta2,
hi1, hi2 body_middle). Openings (pre-body material + first minute of body) run
once with large_v3_prevtext_off to verify body starts and inspect intro behaviour.

One subprocess per config so peak RSS belongs to that config.
Output: <eval_dir>/realworld/compare_prevtext/<config>/<key>.<label>.r<n>.{json,txt,transcript.json}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from dataclasses import replace

from evaluation.experiments.realworld_asr import cut, measure, readable
from evaluation.storage import eval_dir, write_json

CONFIGS = {
    "base_rich_v1": ("base", {}),
    "large_v3_fix": ("large-v3", {}),
    "large_v3_prevtext_off": ("large-v3", {"condition_on_previous_text": False}),
}
REPEATS = {"base_rich_v1": 2, "large_v3_fix": 1, "large_v3_prevtext_off": 2}
MAIN = [("ta1", "body_middle"), ("ta2", "body_middle"), ("hi1", "body_middle"), ("hi2", "body_middle")]
OPENINGS = {"ta2": (0, 187), "hi2": (0, 203)}  # pre-body + ~60 s of body


def usable_measures(transcript) -> dict:
    """Loop duration and missing speech computed from non-suspect segments only."""
    suspect = [s for s in transcript.segments if s.hallucination_suspect]
    loop_s = sum(max(0.0, s.end - s.start) for s in suspect if "repeated_text" in s.flags)
    words = sorted((w.start - 0.3, w.end + 0.3) for s in transcript.segments if not s.hallucination_suspect
                   for w in (s.words or []))
    missing = []
    for rs, re_ in (transcript.speech_regions.regions if transcript.speech_regions else []):
        if re_ - rs < 1.5:
            continue
        covered = sum(max(0.0, min(re_, we) - max(rs, ws)) for ws, we in words if we > rs and ws < re_)
        if covered / (re_ - rs) < 0.2:
            missing.append((round(rs, 1), round(re_, 1)))
    return {
        "loop_seconds": round(loop_s, 1),
        "loop_segments": sum(1 for s in suspect if "repeated_text" in s.flags),
        "missing_speech_usable_s": round(sum(e - s for s, e in missing), 1),
        "missing_regions_usable": missing[:12],
    }


def worker(config: str) -> None:
    import psutil
    from services import transcription

    model, overrides = CONFIGS[config]
    root = eval_dir() / "realworld"
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))
    out = root / "compare_prevtext" / config
    out.mkdir(parents=True, exist_ok=True)

    proc = psutil.Process()
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()

    def sample():
        while not stop.wait(0.2):
            peak["rss"] = max(peak["rss"], proc.memory_info().rss)

    threading.Thread(target=sample, daemon=True).start()
    profile = replace(transcription.PROFILES["rich_v1"], name=config, model=model, **overrides)
    t0 = time.perf_counter()
    if transcription.get_model(profile.model, profile.device, profile.compute_type) is None:
        raise SystemExit(f"{model} failed to load: {transcription._model_load_error}")
    load_s = round(time.perf_counter() - t0, 2)

    jobs = [(key, next(w for w in plan[key]["windows"] if w["label"] == label), REPEATS[config]) for key, label in MAIN]
    if config == "large_v3_prevtext_off":
        for key, (start, duration) in OPENINGS.items():
            jobs.append((key, {"label": "opening_check", "start": start, "duration": duration, "kind": "difficult"}, 1))

    for key, window, repeats in jobs:
        clip = root / "windows" / f"{key}.{window['label']}.{window['start']}.wav"
        cut(root / "audio" / f"{key}.wav", window["start"], window["duration"], clip)
        for rep in range(1, repeats + 1):
            started = time.perf_counter()
            transcript = transcription.transcribe_rich(str(clip), profile=profile, language_mode="auto")
            row = measure(transcript, plan[key]["lang"], window)
            row.update(usable_measures(transcript))
            row.update(config=config, repeat=rep, wall_s=round(time.perf_counter() - started, 1),
                       model_load_s=load_s, peak_rss_mb_so_far=round(peak["rss"] / 2**20))
            stem = f"{key}.{window['label']}.r{rep}"
            write_json(out / f"{stem}.json", row)
            write_json(out / f"{stem}.transcript.json", transcript.to_dict())
            (out / f"{stem}.txt").write_text(readable(transcript, window), encoding="utf-8")
            print(f"  {config} {key}/{window['label']} r{rep}: lang={row['language']}({row['language_probability']}) "
                  f"loops={row['loop_segments']}seg/{row['loop_seconds']}s cov={row['transcript_coverage']} "
                  f"missing={row['missing_speech_usable_s']}s rtf={row['rtf']} peak={row['peak_rss_mb_so_far']}MB",
                  flush=True)
    stop.set()
    write_json(out / "_peak.json", {"config": config, "peak_rss_mb": round(peak["rss"] / 2**20), "model_load_s": load_s})


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="*", default=list(CONFIGS))
    ap.add_argument("--worker")
    args = ap.parse_args(argv)
    if args.worker:
        worker(args.worker)
        return 0
    for config in args.configs:
        print(f"[{config}]", flush=True)
        subprocess.run([sys.executable, "-m", "evaluation.experiments.realworld_prevtext_compare", "--worker", config],
                       check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
