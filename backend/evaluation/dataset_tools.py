"""
Dataset preparation tooling (Phase 2).

The product owner chooses the videos. These helpers only make adding, checking
and freezing them mechanical and hard to get wrong:

    add_item        hash + probe a local media file and append it to a manifest
    label_template  create labels/<item_id>.json with the draft schema
    check           manifest + media hashes + labels + composition report
    freeze          check strictly, then pin label hashes and set frozen=true

A frozen manifest is never edited; changes go into a new version folder.
"""
from __future__ import annotations

import hashlib
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from evaluation import dataset as ds
from evaluation import labels as lb
from evaluation.storage import media_dir, read_json, sha256_file, write_json

# Target composition from master plan §10.1, used for an informational report only.
TARGET_SLOTS = [
    ("English short (5–20 min)", lambda i: i["languages"] == ["en"] and _bucket(i) == "short", 2),
    ("English long (60–120 min)", lambda i: i["languages"] == ["en"] and _bucket(i) == "long", 2),
    ("Hindi short", lambda i: i["languages"] == ["hi"] and _bucket(i) == "short", 1),
    ("Hindi long", lambda i: i["languages"] == ["hi"] and _bucket(i) == "long", 1),
    ("Tamil short", lambda i: i["languages"] == ["ta"] and _bucket(i) == "short", 1),
    ("Tamil long", lambda i: i["languages"] == ["ta"] and _bucket(i) == "long", 1),
    ("Hinglish (code-switched)", lambda i: sorted(i["languages"]) == ["en", "hi"], 1),
    ("Tanglish (code-switched)", lambda i: sorted(i["languages"]) == ["en", "ta"], 1),
    ("Music/silence-heavy", lambda i: "music-heavy" in i.get("tags", []), 1),
    ("Difficult audio", lambda i: "difficult-audio" in i.get("tags", []), 1),
    ("Multi-speaker / cross-talk", lambda i: "multi-speaker" in i.get("tags", []), 1),
    ("Very short (< 3 min)", lambda i: _bucket(i) == "very-short", 1),
]

SUGGESTED_TAGS = ["podcast", "interview", "monologue", "panel", "multi-speaker", "high-energy",
                  "low-energy", "music-heavy", "difficult-audio", "long-form", "short-form"]


def _bucket(item: dict) -> str:
    d = item.get("duration_s") or 0
    if d < 180:
        return "very-short"
    if d < 30 * 60:
        return "short"
    if d < 60 * 60:
        return "medium"
    return "long"


class DatasetToolError(RuntimeError):
    pass


def labels_dir(manifest_path: Path) -> Path:
    return Path(manifest_path).parent / "labels"


def _load_raw(manifest_path: Path) -> dict:
    data = read_json(manifest_path)
    ds.parse_manifest(data, manifest_path)  # validate before touching it
    return data


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _probe_duration(path: Path) -> float:
    import ffmpeg
    probe = ffmpeg.probe(str(path))
    if not any(s.get("codec_type") == "audio" for s in probe.get("streams", [])):
        raise DatasetToolError(f"{path.name} has no audio stream")
    return round(float(probe["format"]["duration"]), 3)


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------

def add_item(manifest_path: Path, media: Path, item_id: str, languages: list[str], *,
             language_mode: str = "auto", tags: list[str] | None = None, speakers: int | None = None,
             source_url: str | None = None, notes: str = "", copy_into_media_dir: bool = False) -> dict:
    manifest_path = Path(manifest_path)
    data = _load_raw(manifest_path)
    if data.get("frozen"):
        raise DatasetToolError(f"{manifest_path} is frozen; create a new version instead of editing it")
    if any(i.get("id") == item_id for i in data["items"]):
        raise DatasetToolError(f"item id {item_id!r} already exists")

    media = Path(media).resolve()
    if not media.is_file():
        raise DatasetToolError(f"media not found: {media}")
    target = media_dir() / media.name
    if media.parent != media_dir().resolve():
        if not copy_into_media_dir:
            raise DatasetToolError(
                f"{media.name} is not in the media directory ({media_dir()}). Move it there, "
                "or pass --copy to copy it in. Frozen manifests reference media by filename.")
        if target.exists():
            raise DatasetToolError(f"{target} already exists; refusing to overwrite")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media, target)
        media = target

    if any(i.get("media", {}).get("filename") == media.name for i in data["items"]):
        raise DatasetToolError(f"{media.name} is already used by another item")

    item = {
        "id": item_id,
        "media": {"filename": media.name, "sha256": sha256_file(media)},
        "languages": languages,
        "language_mode": language_mode,
        "duration_s": _probe_duration(media),
        "speakers": speakers,
        "tags": tags or [],
        "source": {"kind": "youtube" if source_url and "youtu" in source_url else ("url" if source_url else "local"),
                   "url": source_url},
        "notes": notes,
        "added_at": time.strftime("%Y-%m-%d"),
    }
    data["items"].append(item)
    ds.parse_manifest(data, manifest_path)  # the result must still be valid
    write_json(manifest_path, data)
    return item


# ---------------------------------------------------------------------------
# label templates
# ---------------------------------------------------------------------------

def label_template(manifest_path: Path, item_id: str) -> Path:
    data = _load_raw(manifest_path)
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if item is None:
        raise DatasetToolError(f"no item {item_id!r} in {manifest_path}")
    path = labels_dir(manifest_path) / f"{item_id}.json"
    if path.exists():
        raise DatasetToolError(f"{path} already exists; refusing to overwrite labels")
    write_json(path, lb.template(item_id, item.get("duration_s"), item.get("languages") or []))
    return path


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

@dataclass
class CheckReport:
    dataset: str
    frozen: bool
    item_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    label_reports: list[lb.LabelReport] = field(default_factory=list)
    composition: list[tuple[str, int, int]] = field(default_factory=list)  # (slot, have, target)
    totals: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors and all(r.ok for r in self.label_reports)


def check(manifest_path: Path, *, for_freeze: bool = False, verify_hashes: bool = True) -> CheckReport:
    manifest_path = Path(manifest_path)
    data = read_json(manifest_path)
    try:
        dataset = ds.parse_manifest(data, manifest_path)
    except ds.ManifestError as exc:
        report = CheckReport(f"{data.get('dataset')}-{data.get('version')}", bool(data.get("frozen")), 0)
        report.errors.append(str(exc))
        return report

    report = CheckReport(dataset.label, dataset.frozen, len(dataset.items))
    if for_freeze and not dataset.items:
        report.errors.append("the manifest has no items")

    raw_items = {i["id"]: i for i in data["items"]}
    for item in dataset.items:
        raw = raw_items[item.id]
        if not item.media_path.is_file():
            report.errors.append(f"{item.id}: media missing at {item.media_path}")
        elif verify_hashes:
            try:
                ds.verify_media(item)
            except ds.ManifestError as exc:
                report.errors.append(str(exc))
        if raw.get("duration_s") is None:
            report.errors.append(f"{item.id}: duration_s missing (add items with `dataset add`)")
        if not raw.get("media", {}).get("filename"):
            report.errors.append(f"{item.id}: use media.filename (absolute paths are not portable)")

        label_path = labels_dir(manifest_path) / f"{item.id}.json"
        if not label_path.exists():
            (report.errors if for_freeze else report.warnings).append(f"{item.id}: no labels file yet")
            continue
        labels = read_json(label_path)
        report.label_reports.append(lb.validate_labels(labels, item.id, raw.get("duration_s"), for_freeze))
        pinned = raw.get("labels_sha256")
        if dataset.frozen and pinned and pinned != _file_sha256(label_path):
            report.errors.append(f"{item.id}: labels changed after the dataset was frozen")

    items = list(raw_items.values())
    report.composition = [(name, sum(1 for i in items if match(i)), target) for name, match, target in TARGET_SLOTS]
    for name, have, target in report.composition:
        if have < target:
            report.warnings.append(f"composition: {name}: {have}/{target}")
    report.totals = {
        "items": len(items),
        "hours": round(sum(i.get("duration_s") or 0 for i in items) / 3600, 2),
        "audio_cache_gb_estimate": round(sum(i.get("duration_s") or 0 for i in items) * 32000 / 2**30, 2),
        "by_language": {lang: sum(1 for i in items if lang in i["languages"]) for lang in sorted(ds.LANGUAGES)},
    }
    return report


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------

def freeze(manifest_path: Path, frozen_by: str) -> CheckReport:
    manifest_path = Path(manifest_path)
    if not frozen_by.strip():
        raise DatasetToolError("freeze requires --by <name>")
    data = read_json(manifest_path)
    if data.get("frozen"):
        raise DatasetToolError(f"{manifest_path} is already frozen")

    report = check(manifest_path, for_freeze=True)
    if not report.ok:
        return report

    for item in data["items"]:
        item["labels_sha256"] = _file_sha256(labels_dir(manifest_path) / f"{item['id']}.json")
    data["frozen"] = True
    data["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    data["frozen_by"] = frozen_by
    ds.parse_manifest(data, manifest_path)
    write_json(manifest_path, data)
    report.frozen = True
    return report
