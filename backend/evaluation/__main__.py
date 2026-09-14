"""
Command line entry point. Run from backend/:

  python -m evaluation run --dataset evaluation/datasets/<name>/<version>/manifest.json \
        --engine legacy_v2@3 --engine legacy_v2@5 [--item ID ...] [--render] [--no-cache]

  python -m evaluation adhoc path/to/video.mp4 [more.mp4 ...] \
        --engine legacy_v2@5 [--language auto|en|hi|ta] [--render] [--no-cache]

  python -m evaluation validate evaluation/datasets/<name>/<version>/manifest.json [--check-media]
  python -m evaluation hash path/to/video.mp4
  python -m evaluation promote <run_id>
  python -m evaluation where
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _engines(values: list[str] | None):
    from evaluation.engines import parse_engine_spec
    specs = [parse_engine_spec(v) for v in (values or ["legacy_v2@3", "legacy_v2@5"])]
    labels = [s.label for s in specs]
    if len(set(labels)) != len(labels):
        raise SystemExit(f"duplicate engine specs: {labels}")
    return specs


def main(argv: list[str] | None = None) -> int:
    # Run artifacts and logs contain Hindi/Tamil; don't depend on the console codepage.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="python -m evaluation", description="ClipPods offline evaluation")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_run_flags(p):
        p.add_argument("--engine", action="append", help="engine spec, e.g. legacy_v2@5 (repeatable; "
                                                         "default: legacy_v2@3 and legacy_v2@5)")
        p.add_argument("--render", action="store_true", help="also cut MP4 clips into the run folder")
        p.add_argument("--no-cache", action="store_true", help="rebuild every stage instead of reusing cache")
        p.add_argument("--note", default="", help="free-text note stored in run.json")

    p_run = sub.add_parser("run", help="evaluate a dataset manifest")
    p_run.add_argument("--dataset", required=True, type=Path)
    p_run.add_argument("--item", action="append", dest="items", help="limit to item id (repeatable)")
    add_run_flags(p_run)

    p_adhoc = sub.add_parser("adhoc", help="evaluate local files without a manifest")
    p_adhoc.add_argument("media", nargs="+", type=Path)
    p_adhoc.add_argument("--language", default="auto", choices=["auto", "en", "hi", "ta"])
    add_run_flags(p_adhoc)

    p_val = sub.add_parser("validate", help="validate a manifest")
    p_val.add_argument("manifest", type=Path)
    p_val.add_argument("--check-media", action="store_true", help="also verify media files and hashes")

    p_hash = sub.add_parser("hash", help="print sha256 of a media file (for manifests)")
    p_hash.add_argument("media", type=Path)

    p_prom = sub.add_parser("promote", help="copy a finished run's JSON into git-tracked results/")
    p_prom.add_argument("run_id")

    sub.add_parser("where", help="show evaluation data directories")

    args = parser.parse_args(argv)

    from evaluation import dataset as ds
    from evaluation import runner, storage

    if args.command == "where":
        for label, path in (("eval dir", storage.eval_dir()), ("media", storage.media_dir()),
                            ("cache", storage.cache_dir()), ("runs", storage.runs_dir()),
                            ("results (git)", runner.RESULTS_DIR)):
            print(f"{label:>14}: {path}")
        return 0

    if args.command == "hash":
        print(storage.sha256_file(args.media))
        return 0

    if args.command == "validate":
        dataset = ds.load_manifest(args.manifest)
        print(f"{dataset.label}: {len(dataset.items)} items, frozen={dataset.frozen}")
        if args.check_media:
            for item in dataset.items:
                ds.verify_media(item)
                print(f"  ok  {item.id}")
        return 0

    if args.command == "promote":
        print(runner.promote_run(args.run_id))
        return 0

    engines = _engines(args.engine)
    if args.command == "run":
        dataset = ds.load_manifest(args.dataset)
        items = args.items
    else:
        dataset = ds.adhoc_dataset(args.media, args.language)
        items = None

    outcome = runner.run_evaluation(
        dataset,
        runner.RunOptions(engines=engines, use_cache=not args.no_cache, render=args.render,
                          item_ids=items, note=args.note),
    )
    print(f"\nrun: {outcome.run_id}\n  at {outcome.run_dir}")
    if outcome.failed_items:
        print(f"  FAILED items: {', '.join(outcome.failed_items)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
