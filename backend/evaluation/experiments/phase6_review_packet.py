"""
Phase 6 listening review packet: old vs new picker, blind.

    python -m evaluation.experiments.phase6_review_packet <run_id> [<run_id> ...] [--seed N] [--out NAME]
        [--engines OLD NEW]

For every item in the given harness runs that has both engines' selections
(default `legacy_v2@5` and `boundary_v1@5`), cuts each clip's audio from the cached 16 kHz WAV
into an .m4a, labels the two engines "A" and "B" in a random (seeded) order per
item, and writes:

  <eval_dir>/realworld/<NAME, default phase6_review>/
      review.md          what to listen to, clip text, blanks for ratings
      key.json           which engine is A/B per item — open only after rating
      <item>/A_1.m4a …   clip audio

Uses only cached artifacts: no ASR, no selection re-run.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from evaluation.storage import eval_dir, read_json, write_json

DEFAULT_ENGINES = ("legacy_v2@5", "boundary_v1@5")


def _cache_path(stage: str, key: str) -> Path:
    return eval_dir() / "cache" / stage / key[:2] / key


def _clip_text(transcript, start: float, end: float) -> str:
    words = [w.text for s in transcript.segments for w in (s.words or [])
             if start <= (w.start + w.end) / 2 <= end]
    if words:
        return " ".join(t.strip() for t in words)
    return " ".join(s.text for s in transcript.segments if s.start < end and s.end > start)


def _cut(wav: Path, start: float, end: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}",
                    "-i", str(wav), "-t", f"{end - start:.3f}", "-c:a", "aac", "-b:a", "128k", str(dest)],
                   check=True)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    from services.transcript import Transcript

    ap = argparse.ArgumentParser()
    ap.add_argument("run_ids", nargs="+")
    ap.add_argument("--seed", type=int, default=20261019)
    ap.add_argument("--out", default="phase6_review", help="folder name under <eval_dir>/realworld/")
    ap.add_argument("--engines", nargs=2, default=list(DEFAULT_ENGINES), metavar=("OLD", "NEW"))
    args = ap.parse_args(argv)
    engines = tuple(args.engines)

    out = eval_dir() / "realworld" / args.out
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    key: dict = {"seed": args.seed, "runs": args.run_ids, "engines": engines, "items": {}}
    md = ["# ClipPods — clip listening review (blind)", "",
          "For each video, listen to set **A** and set **B** (5 clips each). For every clip note:",
          "**clean start?** (doesn't begin mid-sentence or mid-word) · **clean end?** (doesn't stop mid-thought) · "
          "**worth posting?** (1–5). Then say which set you'd rather post overall.",
          "", "Don't open `key.json` until you've finished.", ""]

    for run_id in args.run_ids:
        run_dir = eval_dir() / "runs" / run_id
        run = read_json(run_dir / "run.json")
        for item_id, record in run["items"].items():
            item_dir = run_dir / "items" / item_id
            if record.get("status") != "ok" or not all((item_dir / e / "selection.json").exists() for e in engines):
                continue
            stages = record["stages"]
            wav = _cache_path("audio", stages["audio"]["key"]) / "audio.wav"
            transcript = Transcript.from_dict(read_json(_cache_path("transcript", stages["transcript"]["key"])
                                                        / "transcript.json"))
            order = list(engines)
            rng.shuffle(order)
            labels = dict(zip("AB", order))
            key["items"][item_id] = {"run_id": run_id, **labels}
            md += [f"## {item_id}  ({transcript.language.language}, {transcript.audio_duration / 60:.0f} min)", ""]
            for label, engine in labels.items():
                clips = read_json(item_dir / engine / "selection.json")["clips"]
                md += [f"### Set {label}", "",
                       "| # | file | length | clean start? | clean end? | worth posting (1–5) |",
                       "|---|---|---|---|---|---|"]
                texts = []
                for n, c in enumerate(clips, 1):
                    name = f"{label}_{n}.m4a"
                    _cut(wav, c["start"], c["end"], out / item_id / name)
                    md.append(f"| {n} | `{item_id}/{name}` | {c['end'] - c['start']:.0f} s | | | |")
                    texts.append(f"{n}. _{_clip_text(transcript, c['start'], c['end'])[:600]}_")
                md += ["", *texts, ""]
            md += [f"**Overall for {item_id}: prefer A / B / no difference:** ", ""]
            print(f"  {item_id}: done", flush=True)     # labels stay in key.json only

    write_json(out / "key.json", key)
    (out / "review.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {out / 'review.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
