"""
Dataset manifests.

A manifest is a versioned JSON file committed under
backend/evaluation/datasets/<name>/<version>/manifest.json. It references media
by content hash; the media itself stays outside git in <eval_dir>/media/.

    {
      "schema": "clippods-eval-manifest/1",
      "dataset": "clippods-eval",
      "version": "v1",
      "frozen": false,                     # true once approved; never edit a frozen manifest
      "items": [
        {
          "id": "ta-podcast-long-01",       # unique, filesystem safe
          "media": {"filename": "ta-podcast-long-01.mp4", "sha256": "…"},
          "languages": ["ta"],              # subset of en|hi|ta; 2+ = code-switched
          "duration_s": 5412.3,
          "speakers": 2,
          "tags": ["long-form", "podcast", "multi-speaker"],
          "language_mode": "auto",          # auto|en|hi|ta (decision D3)
          "source": {"kind": "youtube", "url": "…"},
          "notes": "why this item is in the set"
        }
      ]
    }

`media.filename` resolves against <eval_dir>/media/. `media.path` (absolute) is
accepted for ad-hoc local work but is not portable, so frozen manifests must use
`filename`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from evaluation.storage import canonical_hash, media_dir, read_json, sha256_file

SCHEMA = "clippods-eval-manifest/1"
LANGUAGES = {"en", "hi", "ta"}
LANGUAGE_MODES = {"auto", "en", "hi", "ta"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


class ManifestError(ValueError):
    pass


@dataclass
class DatasetItem:
    id: str
    media_path: Path
    expected_sha256: str | None
    languages: list[str]
    language_mode: str = "auto"
    tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class Dataset:
    name: str
    version: str
    frozen: bool
    items: list[DatasetItem]
    manifest_path: Path | None
    manifest_sha256: str

    @property
    def label(self) -> str:
        return f"{self.name}-{self.version}"


def load_manifest(path: Path) -> Dataset:
    path = Path(path)
    data = read_json(path)
    return parse_manifest(data, path)


def parse_manifest(data: dict, path: Path | None = None) -> Dataset:
    errors: list[str] = []
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    for key in ("dataset", "version"):
        if not isinstance(data.get(key), str) or not data.get(key):
            errors.append(f"'{key}' must be a non-empty string")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        errors.append("'items' must be a list")
        raw_items = []

    seen: set[str] = set()
    items: list[DatasetItem] = []
    for index, raw in enumerate(raw_items):
        where = f"items[{index}]"
        item_id = raw.get("id")
        if not isinstance(item_id, str) or not _ID_RE.match(item_id):
            errors.append(f"{where}.id must match {_ID_RE.pattern}")
            continue
        where = f"item {item_id!r}"
        if item_id in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(item_id)

        media = raw.get("media") or {}
        if media.get("filename"):
            media_path = media_dir() / media["filename"]
        elif media.get("path"):
            if data.get("frozen"):
                errors.append(f"{where}: frozen manifests must use media.filename, not media.path")
            media_path = Path(media["path"])
        else:
            errors.append(f"{where}: media.filename or media.path is required")
            continue

        languages = raw.get("languages") or []
        if not languages or not set(languages) <= LANGUAGES:
            errors.append(f"{where}: languages must be a non-empty subset of {sorted(LANGUAGES)}")
        mode = raw.get("language_mode", "auto")
        if mode not in LANGUAGE_MODES:
            errors.append(f"{where}: language_mode must be one of {sorted(LANGUAGE_MODES)}")
        if data.get("frozen") and not media.get("sha256"):
            errors.append(f"{where}: frozen manifests must pin media.sha256")

        items.append(DatasetItem(
            id=item_id,
            media_path=media_path,
            expected_sha256=media.get("sha256"),
            languages=list(languages),
            language_mode=mode,
            tags=list(raw.get("tags") or []),
            raw=raw,
        ))

    if errors:
        raise ManifestError("Invalid manifest" + (f" {path}" if path else "") + ":\n  - " + "\n  - ".join(errors))

    return Dataset(
        name=data["dataset"],
        version=data["version"],
        frozen=bool(data.get("frozen")),
        items=items,
        manifest_path=path,
        manifest_sha256=canonical_hash(data),
    )


def adhoc_dataset(media_paths: list[Path], language_mode: str = "auto") -> Dataset:
    """A throwaway, unfrozen dataset for evaluating arbitrary local files (D14)."""
    if language_mode not in LANGUAGE_MODES:
        raise ManifestError(f"language_mode must be one of {sorted(LANGUAGE_MODES)}")
    items = []
    for p in media_paths:
        p = Path(p).resolve()
        item_id = re.sub(r"[^a-z0-9._-]+", "-", p.stem.lower()).strip("-")[:80] or "item"
        items.append(DatasetItem(id=item_id, media_path=p, expected_sha256=None,
                                 languages=[] if language_mode == "auto" else [language_mode],
                                 language_mode=language_mode,
                                 raw={"id": item_id, "media": {"path": str(p)}}))
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise ManifestError(f"ad-hoc media files produce duplicate item ids: {ids}")
    return Dataset(name="adhoc", version="unversioned", frozen=False, items=items,
                   manifest_path=None, manifest_sha256=canonical_hash([i.raw for i in items]))


def verify_media(item: DatasetItem) -> str:
    """Check the media exists and matches its pinned hash. Returns the sha256."""
    if not item.media_path.is_file():
        raise ManifestError(f"item {item.id!r}: media not found at {item.media_path}")
    actual = sha256_file(item.media_path)
    if item.expected_sha256 and actual != item.expected_sha256:
        raise ManifestError(
            f"item {item.id!r}: media sha256 mismatch (expected {item.expected_sha256}, got {actual})"
        )
    return actual
