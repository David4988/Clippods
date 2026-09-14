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

  python -m evaluation dataset add --manifest M --media FILE --id ID --languages ta[,en] [...]
  python -m evaluation dataset label-template --manifest M --item ID
  python -m evaluation dataset check M [--for-freeze] [--skip-hashes]
  python -m evaluation dataset freeze M --by NAME
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


def _print_check(report) -> None:
    print(f"{report.dataset}: {report.item_count} items, frozen={report.frozen}")
    t = report.totals
    if t:
        print(f"  total {t['hours']} h of media; audio cache ≈ {t['audio_cache_gb_estimate']} GB; "
              f"items per language {t['by_language']}")
    if report.composition:
        print("  composition vs target (informational):")
        for name, have, target in report.composition:
            mark = "ok " if have >= target else "-- "
            print(f"    {mark}{name}: {have}/{target}")
    for label_report in report.label_reports:
        state = "ok" if label_report.ok else f"{len(label_report.errors)} error(s)"
        print(f"  labels {label_report.item_id}: {state}")
        for e in label_report.errors:
            print(f"    ERROR   {e}")
        for w in label_report.warnings:
            print(f"    warning {w}")
    for e in report.errors:
        print(f"  ERROR   {e}")
    for w in report.warnings:
        if not w.startswith("composition:"):
            print(f"  warning {w}")
    print("  RESULT: " + ("ok" if report.ok else "not ready"))


def _dataset_command(args) -> int:
    from evaluation import dataset_tools as tools

    split = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]
    try:
        if args.dataset_command == "add":
            item = tools.add_item(
                args.manifest, args.media, args.item_id, split(args.languages),
                language_mode=args.language_mode, tags=split(args.tags), speakers=args.speakers,
                source_url=args.source_url, notes=args.notes, copy_into_media_dir=args.copy)
            print(f"added {item['id']}: {item['media']['filename']} ({item['duration_s']} s, "
                  f"sha256 {item['media']['sha256'][:12]}…)")
            return 0
        if args.dataset_command == "label-template":
            print(tools.label_template(args.manifest, args.item))
            return 0
        if args.dataset_command == "check":
            report = tools.check(args.manifest, for_freeze=args.for_freeze, verify_hashes=not args.skip_hashes)
            _print_check(report)
            return 0 if report.ok else 1
        if args.dataset_command == "freeze":
            report = tools.freeze(args.manifest, args.by)
            _print_check(report)
            if report.frozen:
                print("  FROZEN. Do not edit this manifest or its labels; create a new version for changes.")
                return 0
            return 1
    except (tools.DatasetToolError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


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

    p_ds = sub.add_parser("dataset", help="prepare, check and freeze a dataset manifest")
    ds_sub = p_ds.add_subparsers(dest="dataset_command", required=True)

    p_add = ds_sub.add_parser("add", help="hash + probe a media file and append it to a manifest")
    p_add.add_argument("--manifest", required=True, type=Path)
    p_add.add_argument("--media", required=True, type=Path)
    p_add.add_argument("--id", required=True, dest="item_id")
    p_add.add_argument("--languages", required=True, help="comma separated subset of en,hi,ta")
    p_add.add_argument("--language-mode", default="auto", choices=["auto", "en", "hi", "ta"])
    p_add.add_argument("--tags", default="", help="comma separated, e.g. podcast,multi-speaker")
    p_add.add_argument("--speakers", type=int)
    p_add.add_argument("--source-url")
    p_add.add_argument("--notes", default="", help="why this item is in the set")
    p_add.add_argument("--copy", action="store_true", help="copy the file into the media directory first")

    p_tpl = ds_sub.add_parser("label-template", help="create labels/<item>.json (never overwrites)")
    p_tpl.add_argument("--manifest", required=True, type=Path)
    p_tpl.add_argument("--item", required=True)

    p_chk = ds_sub.add_parser("check", help="validate manifest, media, labels and composition")
    p_chk.add_argument("manifest", type=Path)
    p_chk.add_argument("--for-freeze", action="store_true", help="apply the strict rules freeze uses")
    p_chk.add_argument("--skip-hashes", action="store_true", help="don't re-hash media (faster)")

    p_frz = ds_sub.add_parser("freeze", help="strict check, pin label hashes, set frozen=true")
    p_frz.add_argument("manifest", type=Path)
    p_frz.add_argument("--by", required=True, help="who approved the freeze")

    args = parser.parse_args(argv)

    from evaluation import dataset as ds
    from evaluation import runner, storage

    if args.command == "dataset":
        return _dataset_command(args)

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
