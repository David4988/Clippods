"""
Diagnostic: are the real-audio repetition loops caused by the rich_v1
script-aware compression fix, by previous-text conditioning, or both?

    python -m evaluation.experiments.realworld_loop_diagnostic [--model large-v3]

Runs two decode variants on windows that looped with rich_v1:
  A  rich_v1 without the fix (Whisper's compression-ratio loop guard restored)
  B  rich_v1 with the fix + condition_on_previous_text=False
Results: <eval_dir>/realworld/asr/diagnostic/<model>/<key>.<label>.<variant>.{json,txt}
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import replace

from evaluation.experiments.realworld_asr import measure, readable
from evaluation.storage import eval_dir, write_json

WINDOWS = [("ta1", "body_early"), ("hi1", "body_early")]
VARIANTS = {
    "A_nofix": {"script_aware_compression": False},
    "B_fix_no_condition": {"condition_on_previous_text": False},
}


def main(argv=None) -> int:
    import psutil
    from services import transcription

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--windows", nargs="*", help="key:label pairs (default: ta1/hi1 body_early)")
    ap.add_argument("--variants", nargs="*", choices=list(VARIANTS))
    args = ap.parse_args(argv)
    windows = [tuple(w.split(":")) for w in args.windows] if args.windows else WINDOWS
    variants = {k: v for k, v in VARIANTS.items() if not args.variants or k in args.variants}

    root = eval_dir() / "realworld"
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))
    out = root / "asr" / "diagnostic" / args.model
    out.mkdir(parents=True, exist_ok=True)

    proc = psutil.Process()
    peak = {"rss": proc.memory_info().rss}
    stop = threading.Event()
    threading.Thread(target=lambda: [peak.__setitem__("rss", max(peak["rss"], proc.memory_info().rss))
                                     for _ in iter(lambda: stop.wait(0.2), True)], daemon=True).start()

    for key, label in windows:
        window = next(w for w in plan[key]["windows"] if w["label"] == label)
        clip = root / "windows" / f"{key}.{label}.{window['start']}.wav"
        for name, overrides in variants.items():
            profile = replace(transcription.PROFILES["rich_v1"], name=f"diag_{name}", model=args.model, **overrides)
            started = time.perf_counter()
            transcript = transcription.transcribe_rich(str(clip), profile=profile, language_mode="auto")
            row = measure(transcript, plan[key]["lang"], window)
            row.update(variant=name, overrides=overrides, wall_s=round(time.perf_counter() - started, 1),
                       peak_rss_mb_so_far=round(peak["rss"] / 2**20))
            write_json(out / f"{key}.{label}.{name}.json", row)
            (out / f"{key}.{label}.{name}.txt").write_text(readable(transcript, window), encoding="utf-8")
            print(f"{args.model} {key}/{label} {name}: lang={row['language']} halluc={row['hallucination_suspects']}/"
                  f"{row['segments']} flags={row['flag_counts']} temps={row['temperatures']} "
                  f"cov={row['transcript_coverage']} rtf={row['rtf']}", flush=True)
    stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
