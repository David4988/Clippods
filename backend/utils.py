"""
utils.py — Shared helper functions for the pipeline.
"""
import os
import uuid
import tempfile
from pathlib import Path

if os.environ.get("VERCEL"):
    TEMP_DIR = Path(tempfile.gettempdir()) / "clippods_temp"
else:
    TEMP_DIR = Path(__file__).parent / "temp"

try:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only filesystem fallback
    TEMP_DIR = Path(tempfile.gettempdir())


def get_temp_path(suffix: str = "") -> Path:
    """Return a unique temp file path with an optional suffix."""
    return TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"


def cleanup_file(path: Path | str) -> None:
    """Delete a file if it exists."""
    p = Path(path)
    if p.exists():
        p.unlink()
