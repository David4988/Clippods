# clippods-eval v1

Status: **not frozen**. Items are chosen and labelled in Phase 2.

Media files are **not** in git. Put them in `<eval_dir>/media/` (see
`python -m evaluation where`) and pin each one with `python -m evaluation hash <file>`.

## Target composition (master plan §10.1)

| Slot | Language | Length | Character |
|---|---|---|---|
| 1–2 | English | 5–15 min | high-energy / low-energy |
| 3–4 | English | 60–120 min | 2–3 speaker podcast; interview |
| 5–6 | Hindi | 10–20 min + 60–120 min | podcast; monologue |
| 7–8 | Tamil | 10–20 min + 60–120 min | podcast; monologue |
| 9 | Hinglish | 20–60 min | conversational, code-switched |
| 10 | Tanglish | 20–60 min | conversational, code-switched |
| 11 | any | any | music/silence-heavy |
| 12 | any | any | difficult audio (remote call, echo, noise) |
| 13 | any | any | multi-speaker panel, cross-talk |
| 14 | any | < 3 min | very short input (exact-5 stress) |
| 15–16 | spare | — | failure cases found during development |

## Item fields

See `backend/evaluation/dataset.py` for the schema and validation rules. Frozen
manifests must use `media.filename` (not absolute paths) and pin `media.sha256`.

## Labels (`labels/`, versioned)

Added in Phase 2, one file per item, e.g. `labels/<item_id>.json`:

- `gold_moments`: 5–10 moments you would post: `start`, `end`, `type`
  (`hook | controversy | question | story | open_loop`), optional note.
- `must_not`: regions that must not become clips (ads, intros).
- `transcript_excerpts`: 3–5 hand-corrected 2–3 minute windows for WER/CER.
- `languages`: dominant language and code-switch regions.

The label schema is finalised at Checkpoint 7, before any labelling starts.
