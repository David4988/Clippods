# ClipPods offline evaluation harness

Runs pipeline stages on **local** media files, caches the expensive stages, runs
one or more selection engines, and writes versioned run artifacts. It lets every
change to ASR, boundaries or selection be measured against the previous version
(master plan §10, §11 Phase 0).

It is isolated from production: nothing in `routers/`, `main.py` or the job
worker imports this package, and it never writes to `backend/temp` or
`backend/outputs` beyond the transient files the production functions create
(which it moves out immediately).

Run every command from `backend/`.

## Quick start

```bash
python -m evaluation where                                   # show data directories
python -m evaluation adhoc path/to/podcast.mp4 --engine legacy_v2@3 --engine legacy_v2@5
python -m evaluation adhoc path/to/podcast.mp4 --language ta --render   # also cut MP4s
```

Local files of any size are accepted. The public 100 MB upload limit does not
apply here (decision D14).

## Commands

| Command | Purpose |
|---|---|
| `run --dataset <manifest.json> [--item ID]… [--engine SPEC]… [--render] [--no-cache] [--note TEXT]` | Evaluate a versioned dataset |
| `adhoc <media>… [--language auto\|en\|hi\|ta] [--engine SPEC]… [--render] [--no-cache]` | Evaluate arbitrary local files |
| `validate <manifest.json> [--check-media]` | Validate a manifest (and media hashes) |
| `hash <media>` | sha256 for pinning media in a manifest |
| `promote <run_id>` | Copy a finished run's small JSON into git-tracked `evaluation/results/` |
| `where` | Print data directories |
| `dataset add --manifest M --media FILE --id ID --languages ta[,en] [--tags …] [--speakers N] [--source-url URL] [--notes TEXT] [--copy]` | Hash + probe a media file and append it to an unfrozen manifest |
| `dataset label-template --manifest M --item ID` | Create `labels/<ID>.json` from the draft label schema (never overwrites) |
| `dataset check M [--for-freeze] [--skip-hashes]` | Validate manifest, media hashes, labels and composition coverage |
| `dataset freeze M --by NAME` | Strict check, pin label hashes, set `frozen: true` (product owner only) |

Dataset preparation steps and the label schema are documented in
`datasets/clippods-eval/v1/README.md`.

Engine specs are `<engine>@<clip_count>`. Available now: `legacy_v2` (the
production `select_segments`, unchanged). Default: `legacy_v2@3` (historical)
and `legacy_v2@5` (fair comparison with the 5-clip target).

## Where things live

| What | Location | In git? |
|---|---|---|
| Dataset manifests, labels | `backend/evaluation/datasets/<name>/<version>/` | yes |
| Promoted results (small JSON) | `backend/evaluation/results/<run_id>/` | yes |
| Media | `<eval_dir>/media/` | **no** |
| Stage cache | `<eval_dir>/cache/` | no |
| Full runs (analysis traces, clips) | `<eval_dir>/runs/<run_id>/` | no |

`<eval_dir>` defaults to `<repo>/eval_data/` (git-ignored). Override with
`CLIPPODS_EVAL_DIR`. It is separate from the production GC, so evaluation
artifacts are never deleted by the 24-hour output sweep (D18).

## Run layout

```text
runs/<run_id>/
  run.json          dataset + manifest hash, engines, git commit/branch/dirty,
                    package versions, machine, per-item status and errors
  summary.json      one row per item × engine
  items/<item_id>/
    stages.json     per stage: cache key, hit/miss, config, wall time, peak RSS, RTF
    <engine>@<n>/
      selection.json
      analysis.json   engine trace (UTF-8; readable on Windows)
      metrics.json
      clips/          only with --render
```

## Stage cache

```text
key = sha256({stage, stage_version, inputs, config})
```

- **inputs** chain upstream keys (`probe`/`audio` ← media sha256, `transcript_legacy` ← audio key),
  so changing an early stage invalidates everything after it.
- **config** holds every output-affecting parameter (model, compute type, beam
  size, library versions…). A new ASR configuration is a new key; old entries remain for comparison.
- **stage_version** is bumped by hand when stage code changes behaviour without a config change.
- Entries are built in a temp folder and renamed into place; `_entry.json` is
  written last and marks an entry complete. Interrupted builds never look valid.
- The legacy transcription stage **refuses** to cache the production stub
  transcript that appears when Faster-Whisper cannot load.
- Media hashes are memoised by (path, size, mtime) so multi-GB files are hashed once.

Stages today: `probe`, `audio` (16 kHz mono WAV, ≈ 115 MB per hour of media),
`transcript_legacy` (Faster-Whisper `base`, cpu/int8, beam 5; ignores
`language_mode`, which is recorded as `language_mode_honoured: false`).
Selection is not cached. It is the thing under test and is cheap to recompute.

## Metrics available now

Clip count, identical and overlapping pairs, max overlap ratio, out-of-bounds,
duration distribution, coverage, legacy candidate/fallback counts, and stage
timings/RSS. Metrics that need VAD, word timing, gold labels or human review are
listed in every `metrics.json` under `not_yet_measured` so a report never
implies they were checked.

## Resetting

Delete `<eval_dir>/cache/<stage>/` to force a stage to rebuild everywhere, or use
`--no-cache` for one run. Deleting `<eval_dir>` entirely is safe; manifests,
labels and promoted results live in git.
