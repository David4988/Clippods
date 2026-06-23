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


def log_instrumentation(stage: str, elapsed_time: float | None = None) -> None:
    """
    Log memory, virtual memory, disk space, current stage, and elapsed time.
    """
    import psutil
    import shutil
    import logging

    logger = logging.getLogger("instrumentation")
    try:
        process = psutil.Process()
        rss = process.memory_info().rss
        vmem = psutil.virtual_memory()

        try:
            disk_free = shutil.disk_usage(TEMP_DIR).free
        except Exception:
            disk_free = shutil.disk_usage(tempfile.gettempdir()).free

        elapsed_str = f"{elapsed_time:.4f}s" if elapsed_time is not None else "N/A"

        vmem_dict = {
            "total": vmem.total,
            "available": vmem.available,
            "percent": vmem.percent,
            "used": vmem.used,
            "free": vmem.free
        }

        logger.info(
            f"[INSTRUMENTATION] Stage: '{stage}' | "
            f"Process RSS: {rss} bytes ({rss / (1024*1024):.2f} MB) | "
            f"Virtual Memory: {vmem_dict} | "
            f"Temp Disk Free: {disk_free} bytes ({disk_free / (1024*1024*1024):.2f} GB) | "
            f"Elapsed: {elapsed_str}"
        )
    except Exception as e:
        logger.error(f"Failed to log instrumentation: {e}", exc_info=True)
