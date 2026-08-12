"""
utils.py — Shared helper functions for the pipeline.
"""
import os
import uuid
import tempfile
from pathlib import Path

from config import TEMP_DIR


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

def run_garbage_collection() -> None:
    """
    Scans temp/ and outputs/ directories, deleting expired files and runs.
    Called periodically on FastAPI server startup loop.
    """
    import time
    import shutil
    import logging
    from config import (
        TEMP_DIR,
        OUTPUTS_DIR,
        TEMP_FILE_MAX_AGE_HOURS,
        OUTPUT_DIR_MAX_AGE_HOURS
    )

    gc_logger = logging.getLogger("garbage_collector")
    gc_logger.info("Starting garbage collection sweep...")

    now = time.time()
    temp_max_age_sec = TEMP_FILE_MAX_AGE_HOURS * 3600
    outputs_max_age_sec = OUTPUT_DIR_MAX_AGE_HOURS * 3600

    # 1. Clean expired temp files
    temp_deleted = 0
    if TEMP_DIR.exists():
        for item in TEMP_DIR.iterdir():
            if item.is_file():
                try:
                    mtime = item.stat().st_mtime
                    if now - mtime > temp_max_age_sec:
                        item.unlink()
                        temp_deleted += 1
                except Exception as e:
                    gc_logger.warning("Failed to delete temp file %s: %s", item, e)

    # 2. Clean expired output run folders
    outputs_deleted = 0
    if OUTPUTS_DIR.exists():
        for run_dir in OUTPUTS_DIR.iterdir():
            if run_dir.is_dir():
                try:
                    mtime = run_dir.stat().st_mtime
                    if now - mtime > outputs_max_age_sec:
                        shutil.rmtree(run_dir)
                        outputs_deleted += 1
                except Exception as e:
                    gc_logger.warning("Failed to delete output dir %s: %s", run_dir, e)

    gc_logger.info(
        "Garbage collection sweep completed. Deleted %d temp files, %d outputs run folders.",
        temp_deleted,
        outputs_deleted
    )

