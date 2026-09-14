"""
Evaluation data locations and safe file IO.

Everything the harness writes lives under the evaluation data directory, which is
deliberately separate from backend/temp and backend/outputs so the production
garbage collector never touches it (decision D18), and is git-ignored so media
never enters git (D16).

    <eval_dir>/
      media/     local source videos referenced by dataset manifests
      cache/     content-addressed stage outputs (see cache.py)
      runs/      one folder per evaluation run (see runner.py)
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DEFAULT_EVAL_DIR = REPO_DIR / "eval_data"


def eval_dir() -> Path:
    """Root of evaluation data. Override with CLIPPODS_EVAL_DIR."""
    configured = os.environ.get("CLIPPODS_EVAL_DIR")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_EVAL_DIR
    return root


def media_dir() -> Path:
    return eval_dir() / "media"


def cache_dir() -> Path:
    return eval_dir() / "cache"


def runs_dir() -> Path:
    return eval_dir() / "runs"


def write_json(path: Path, data: Any) -> Path:
    """UTF-8, atomic JSON write (shared with the production pipeline)."""
    from utils import write_json_atomic
    return write_json_atomic(path, data)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_hash(value: Any) -> str:
    """Stable sha256 of a JSON-serialisable value (key order independent)."""
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """
    Content hash of a media file, memoised in <cache>/file_hashes.json keyed by
    (resolved path, size, mtime_ns) so multi-GB podcasts are only hashed once.
    """
    path = Path(path).resolve()
    stat = path.stat()
    index_path = cache_dir() / "file_hashes.json"
    index: dict = read_json(index_path) if index_path.exists() else {}
    fingerprint = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
    if fingerprint in index:
        return index[fingerprint]

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    index[fingerprint] = value
    write_json(index_path, index)
    return value
