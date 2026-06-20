"""
utils.py — Shared helper functions for the pipeline.
"""
import os
import uuid
from pathlib import Path

TEMP_DIR = Path(__file__).parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def get_temp_path(suffix: str = "") -> Path:
    """Return a unique temp file path with an optional suffix."""
    return TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"


def cleanup_file(path: Path | str) -> None:
    """Delete a file if it exists."""
    p = Path(path)
    if p.exists():
        p.unlink()
