# clippods-eval v1

Status: **not frozen, no items**. You (the product owner) choose every video.
The tooling here only makes adding, labelling, checking and freezing them
mechanical. Nothing is frozen until you run `freeze` yourself, after review.

Run every command from `backend/` with `.venv312`:

```powershell
cd backend
..\.venv312\Scripts\python.exe -m evaluation <command>
```

## Target composition (master plan §10.1)

| Slot | Language | Length | Character | Suggested tags |
|---|---|---|---|---|
| 1–2 | English | 5–20 min | one high-energy, one low-energy | `high-energy` / `low-energy` |
| 3–4 | English | 60–120 min | 2–3 speaker podcast; interview | `podcast`, `interview`, `multi-speaker` |
| 5–6 | Hindi | 10–20 min + 60–120 min | podcast; monologue | `podcast`, `monologue` |
| 7–8 | Tamil | 10–20 min + 60–120 min | podcast; monologue | `podcast`, `monologue` |
| 9 | Hinglish | 20–60 min | conversational, code-switched | `--languages hi,en` |
| 10 | Tanglish | 20–60 min | conversational, code-switched | `--languages ta,en` |
| 11 | any | any | music/silence-heavy | `music-heavy` |
| 12 | any | any | difficult audio (remote call, echo, noise) | `difficult-audio` |
| 13 | any | any | multi-speaker panel, cross-talk | `multi-speaker`, `panel` |
| 14 | any | < 3 min | very short input (exact-5 stress) | — |
| 15–16 | spare | — | failure cases found during development | — |

One video can fill several character slots (e.g. a Tamil panel with background
music). `dataset check` prints how the current items cover these slots. The
report is informational; you decide whether the set is good enough.

Around 15 videos and 15–20 hours of media is the expected size. Budget roughly
115 MB of audio cache per hour of media, plus the videos themselves.

## What I need from you

For each video:

1. **The file.** Save it into the media directory (`python -m evaluation where`
   shows it; default `<repo>/eval_data/media/`). Use the original download and
   don't re-encode it, because the hash pins the exact bytes. You're responsible for
   having the right to use the content for internal evaluation. Media never goes into git.
2. **Add it to the manifest:**

   ```powershell
   ..\.venv312\Scripts\python.exe -m evaluation dataset add `
     --manifest evaluation/datasets/clippods-eval/v1/manifest.json `
     --media ..\eval_data\media\<file>.mp4 `
     --id ta-podcast-long-01 --languages ta `
     --tags podcast,multi-speaker,long-form --speakers 2 `
     --source-url "https://www.youtube.com/watch?v=..." `
     --notes "why this video is in the set"
   ```

   `--id`: lowercase letters, digits, `.`, `_`, `-` (e.g. `<lang>-<kind>-<length>-<nn>`).
   `--languages`: every language actually spoken (`hi,en` for Hinglish).
   `--language-mode` defaults to `auto` (D3). Only set `en|hi|ta` if this item
   should also be evaluated with a forced language.
   Add `--copy` if the file is somewhere else and should be copied in.

3. **Create its label file** (never overwrites existing labels):

   ```powershell
   ..\.venv312\Scripts\python.exe -m evaluation dataset label-template `
     --manifest evaluation/datasets/clippods-eval/v1/manifest.json --item ta-podcast-long-01
   ```

4. **Fill in `labels/<item_id>.json`** (see *Labels* below), then set
   `"status": "complete"`, your name in `"labeler"`, and the date in `"labeled_at"`.

5. **Check** as often as you like:

   ```powershell
   ..\.venv312\Scripts\python.exe -m evaluation dataset check evaluation/datasets/clippods-eval/v1/manifest.json
   ..\.venv312\Scripts\python.exe -m evaluation dataset check evaluation/datasets/clippods-eval/v1/manifest.json --for-freeze
   ```

6. **Tell me when the set is ready for review.** After that review, you freeze it:

   ```powershell
   ..\.venv312\Scripts\python.exe -m evaluation dataset freeze evaluation/datasets/clippods-eval/v1/manifest.json --by "<your name>"
   ```

   Freeze runs the strict check, pins a hash of every label file and sets
   `frozen: true`. After that, `add` refuses to edit the manifest and `check`
   reports any label file that changed. Changes go into a `v2` folder.

## Labels

The schema is a **draft** (`clippods-eval-labels/1-draft`); it's finalised at
Checkpoint 7 before labelling starts in earnest. Label one item first so we can
adjust it together. All times are seconds from the start of the file (e.g. `754.5` = 12:34.5).

| Field | What to put there | Required for freeze |
|---|---|---|
| `languages.dominant` | main spoken language: `en`, `hi` or `ta` | yes |
| `languages.code_switch_regions` | stretches where speakers mix languages: `start`, `end`, `languages` (2+) | only if present |
| `gold_moments` | **5–10** moments you would actually post: `id`, `start`, `end`, `type` (`hook`, `controversy`, `question`, `story`, `open_loop`, `other`), `strength` (1 = okay, 2 = good, 3 = would definitely post), `note` | yes |
| `must_not` | regions that must never become clips (ads, sponsor reads, intro/outro, dead air): `start`, `end`, `reason` | if any |
| `transcript_excerpts` | **3–5** non-overlapping windows of ~2–3 minutes, transcribed by hand exactly as spoken: `id`, `start`, `end`, `language`, `script`, `text` | yes |
| `notes` | anything unusual about the item | no |

Guidance:

- **Gold moments:** mark the span you would post, starting and ending where
  *you* would cut. Don't adjust them to any system output. They must not
  overlap `must_not` regions. For `open_loop`, end where the deliberate
  cliffhanger ends, not mid-sentence.
- **Transcript excerpts:** spread them across the video (beginning, middle,
  end), not only the clearest parts. For Hindi and Tamil, write what is said in the
  language it is said in. Don't translate.
- **`script`:** record how you wrote the excerpt: `native` (Devanagari / Tamil
  script), `romanised`, or `mixed` (e.g. native script with English words in Latin).
  The code-switching script policy is still open (D4), so write what feels natural
  and record it. We decide the policy after seeing the results.

Example of a completed file:

```json
{
  "schema": "clippods-eval-labels/1-draft",
  "item_id": "ta-podcast-long-01",
  "status": "complete",
  "labeler": "owner",
  "labeled_at": "2026-09-20",
  "duration_s": 5412.3,
  "languages": {
    "dominant": "ta",
    "code_switch_regions": [{"start": 1210.0, "end": 1275.5, "languages": ["ta", "en"], "note": "startup jargon"}]
  },
  "gold_moments": [
    {"id": "m1", "start": 612.0, "end": 671.0, "type": "hook", "strength": 3, "note": "strong opinion on funding"},
    {"id": "m2", "start": 1830.5, "end": 1902.0, "type": "open_loop", "strength": 2, "note": "sets up the failure story"}
  ],
  "must_not": [{"start": 0.0, "end": 45.0, "reason": "intro music"}],
  "transcript_excerpts": [
    {"id": "x1", "start": 900.0, "end": 1050.0, "language": "ta", "script": "native", "text": "..."}
  ],
  "notes": ""
}
```

(The example shows 2 moments and 1 excerpt for brevity. Freeze needs 5–10 and 3–5.)
