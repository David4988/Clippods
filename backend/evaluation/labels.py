"""
Human labels for dataset items (DRAFT schema; finalised at Checkpoint 7).

One file per item: datasets/<name>/<version>/labels/<item_id>.json

    {
      "schema": "clippods-eval-labels/1-draft",
      "item_id": "ta-podcast-long-01",
      "status": "draft",                 # draft | complete (freeze requires complete)
      "labeler": "",
      "labeled_at": null,                # ISO date when marked complete
      "duration_s": 5412.3,              # copied from the manifest; bounds every range
      "languages": {
        "dominant": "ta",
        "code_switch_regions": [{"start": 120.0, "end": 185.5, "languages": ["ta", "en"], "note": ""}]
      },
      "gold_moments": [                  # 5–10 moments you would actually post
        {"id": "m1", "start": 612.0, "end": 671.0,
         "type": "hook", "strength": 3, "note": "why this is postable"}
      ],
      "must_not": [                      # regions that must never become clips
        {"start": 0.0, "end": 45.0, "reason": "intro music"}
      ],
      "transcript_excerpts": [           # 3–5 hand-corrected windows of ~2–3 minutes
        {"id": "x1", "start": 900.0, "end": 1050.0, "language": "ta",
         "script": "native", "text": "…"}
      ],
      "notes": ""
    }

Times are seconds from the start of the media file.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA = "clippods-eval-labels/1-draft"
STATUSES = {"draft", "complete"}
MOMENT_TYPES = {"hook", "controversy", "question", "story", "open_loop", "other"}
LANGUAGES = {"en", "hi", "ta"}
# How an excerpt was written down. The code-switching script policy (decision D4)
# is still open, so the labeler records what they actually used.
SCRIPTS = {"native", "romanised", "mixed"}

GOLD_MOMENTS_RANGE = (5, 10)
EXCERPTS_RANGE = (3, 5)
EXCERPT_SECONDS_RANGE = (90.0, 240.0)


@dataclass
class LabelReport:
    item_id: str
    errors: list[str] = field(default_factory=list)      # block freezing
    warnings: list[str] = field(default_factory=list)    # worth a look, don't block

    @property
    def ok(self) -> bool:
        return not self.errors


def template(item_id: str, duration_s: float | None, languages: list[str]) -> dict:
    dominant = languages[0] if len(languages) == 1 else None
    return {
        "schema": SCHEMA,
        "item_id": item_id,
        "status": "draft",
        "labeler": "",
        "labeled_at": None,
        "duration_s": duration_s,
        "languages": {"dominant": dominant, "code_switch_regions": []},
        "gold_moments": [],
        "must_not": [],
        "transcript_excerpts": [],
        "notes": "",
    }


def _range_errors(where: str, entry: dict, duration: float | None) -> list[str]:
    start, end = entry.get("start"), entry.get("end")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return [f"{where}: start and end must be numbers (seconds)"]
    problems = []
    if start < 0:
        problems.append(f"{where}: start {start} is negative")
    if end <= start:
        problems.append(f"{where}: end {end} must be after start {start}")
    if duration is not None and end > duration + 0.5:
        problems.append(f"{where}: end {end} is past the media duration {duration}")
    return problems


def _overlaps(ranges: list[tuple[float, float, str]]) -> list[tuple[str, str]]:
    ordered = sorted(ranges)
    return [(a[2], b[2]) for a, b in zip(ordered, ordered[1:]) if b[0] < a[1]]


def validate_labels(labels: dict, item_id: str, duration_s: float | None, require_complete: bool) -> LabelReport:
    report = LabelReport(item_id)
    err, warn = report.errors.append, report.warnings.append

    if labels.get("schema") != SCHEMA:
        err(f"schema must be {SCHEMA!r}")
    if labels.get("item_id") != item_id:
        err(f"item_id {labels.get('item_id')!r} does not match manifest item {item_id!r}")
    status = labels.get("status")
    if status not in STATUSES:
        err(f"status must be one of {sorted(STATUSES)}")
    if require_complete and status != "complete":
        err("status must be 'complete' before the dataset can be frozen")
    if status == "complete" and not labels.get("labeler"):
        err("labeler is required when status is 'complete'")

    duration = labels.get("duration_s") if duration_s is None else duration_s
    if duration_s is not None and labels.get("duration_s") not in (None, duration_s):
        if abs(float(labels["duration_s"]) - duration_s) > 0.5:
            err(f"duration_s {labels['duration_s']} does not match the media ({duration_s})")

    langs = labels.get("languages") or {}
    if langs.get("dominant") not in LANGUAGES:
        (err if status == "complete" else warn)(f"languages.dominant must be one of {sorted(LANGUAGES)}")
    for i, region in enumerate(langs.get("code_switch_regions") or []):
        where = f"languages.code_switch_regions[{i}]"
        report.errors.extend(_range_errors(where, region, duration))
        if not set(region.get("languages") or []) <= LANGUAGES or len(region.get("languages") or []) < 2:
            err(f"{where}: languages must list 2+ of {sorted(LANGUAGES)}")

    moments = labels.get("gold_moments") or []
    ids = [m.get("id") for m in moments]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        err("gold_moments ids must be present and unique")
    for i, m in enumerate(moments):
        where = f"gold_moments[{i}] ({m.get('id')})"
        report.errors.extend(_range_errors(where, m, duration))
        if m.get("type") not in MOMENT_TYPES:
            err(f"{where}: type must be one of {sorted(MOMENT_TYPES)}")
        if m.get("strength") not in (1, 2, 3):
            err(f"{where}: strength must be 1, 2 or 3")
    lo, hi = GOLD_MOMENTS_RANGE
    if not lo <= len(moments) <= hi:
        (err if require_complete else warn)(f"expected {lo}–{hi} gold_moments, found {len(moments)}")

    must_not_ranges = []
    for i, region in enumerate(labels.get("must_not") or []):
        where = f"must_not[{i}]"
        report.errors.extend(_range_errors(where, region, duration))
        if not region.get("reason"):
            warn(f"{where}: add a reason")
        if isinstance(region.get("start"), (int, float)) and isinstance(region.get("end"), (int, float)):
            must_not_ranges.append((region["start"], region["end"]))
    for m in moments:
        if not isinstance(m.get("start"), (int, float)) or not isinstance(m.get("end"), (int, float)):
            continue
        for s, e in must_not_ranges:
            if m["start"] < e and s < m["end"]:
                err(f"gold moment {m.get('id')} overlaps a must_not region [{s}, {e}]")

    excerpts = labels.get("transcript_excerpts") or []
    ex_ranges = []
    for i, x in enumerate(excerpts):
        where = f"transcript_excerpts[{i}] ({x.get('id')})"
        problems = _range_errors(where, x, duration)
        report.errors.extend(problems)
        if not problems:
            length = x["end"] - x["start"]
            if not EXCERPT_SECONDS_RANGE[0] <= length <= EXCERPT_SECONDS_RANGE[1]:
                warn(f"{where}: {length:.0f}s long; aim for 120–180s")
            ex_ranges.append((x["start"], x["end"], str(x.get("id"))))
        if x.get("language") not in LANGUAGES:
            err(f"{where}: language must be one of {sorted(LANGUAGES)}")
        if x.get("script") not in SCRIPTS:
            err(f"{where}: script must be one of {sorted(SCRIPTS)}")
        if require_complete and not (x.get("text") or "").strip():
            err(f"{where}: text is empty")
    for a, b in _overlaps(ex_ranges):
        err(f"transcript excerpts {a} and {b} overlap")
    lo, hi = EXCERPTS_RANGE
    if not lo <= len(excerpts) <= hi:
        (err if require_complete else warn)(f"expected {lo}–{hi} transcript_excerpts, found {len(excerpts)}")

    return report
