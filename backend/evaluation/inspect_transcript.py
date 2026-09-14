"""
Print a readable summary of a cached transcript for a run item.

    python -m evaluation.inspect_transcript <run_id> <item_id> [--segments N] [--flagged]

Shows language decision and probes, quality status, flag counts, speech-region
coverage, and the first N segments (or only flagged ones) with their fields.
"""
from __future__ import annotations

import argparse
import sys

from evaluation import stages
from evaluation.cache import StageCache
from evaluation.storage import read_json, runs_dir


def load(run_id: str, item_id: str):
    record = read_json(runs_dir() / run_id / "items" / item_id / "stages.json")["transcript"]
    path = StageCache().lookup("transcript", record["key"])
    if path is None:
        raise SystemExit(f"transcript cache entry {record['key']} is missing")
    from evaluation.cache import CacheResult
    return stages.load_transcript(CacheResult("transcript", record["key"], path, True, {}))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("item_id")
    ap.add_argument("--segments", type=int, default=8)
    ap.add_argument("--flagged", action="store_true", help="show only flagged segments")
    args = ap.parse_args(argv)

    t = load(args.run_id, args.item_id)
    lang, q = t.language, t.quality
    print(f"profile={t.asr['profile']} mode={lang.mode} decoded_language={lang.language} "
          f"p={lang.probability} top={lang.top[:3]}")
    print(f"probes: {[(p.start, p.language, p.probability) for p in lang.probes]}")
    print(f"language uncertain={lang.uncertain} reasons={lang.reasons}")
    print(f"quality={q.status} reasons={q.reasons}")
    print(f"segments={q.segment_count} words={q.word_count} suspects={q.hallucination_suspect_segments} "
          f"low_conf={q.low_confidence_segments} mixed_script={q.mixed_script_segments}")
    print(f"flags={q.flag_counts}")
    print(f"speech={q.speech_seconds}s covered={q.transcribed_speech_seconds}s coverage={q.speech_coverage} "
          f"text_outside_speech={q.text_outside_speech_seconds}s regions="
          f"{len(t.speech_regions.regions) if t.speech_regions else None}")
    print(f"timings={t.timings} audio_duration={t.audio_duration}")
    shown = 0
    for s in t.segments:
        if args.flagged and not s.flags:
            continue
        if shown >= args.segments:
            break
        shown += 1
        words = "" if s.words is None else f" words={len(s.words)} " + " ".join(
            f"{w.text.strip()}[{w.start:.2f}-{w.end:.2f}{'' if w.in_speech else '!'}]" for w in s.words[:6])
        print(f"  #{s.id} {s.start:7.2f}-{s.end:7.2f} lp={s.avg_logprob} ns={s.no_speech_prob} "
              f"cr={s.compression_ratio} T={s.temperature} ov={s.speech_overlap} scripts={s.scripts} "
              f"flags={s.flags}\n      {s.text[:140]}{words}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
