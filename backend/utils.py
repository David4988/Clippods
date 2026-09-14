"""
utils.py — Shared helper functions for the pipeline.
"""
import json
import os
import uuid
import tempfile
from pathlib import Path
from typing import Any

from config import TEMP_DIR


def write_json_atomic(path: Path | str, data: Any) -> Path:
    """
    Write *data* as UTF-8 JSON, atomically.

    The encoding must be explicit: on Windows the default text codec is the
    locale code page (cp1252 here), which cannot encode Hindi, Tamil or the
    arrows the selection trace contains, and a failed write used to leave a
    0-byte analysis.json. The temp file lives in the destination directory so
    os.replace is a same-volume rename, atomic on Windows and POSIX.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def get_temp_path(suffix: str = "") -> Path:
    """Return a unique temp file path with an optional suffix."""
    return TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"


def cleanup_file(path: Path | str) -> None:
    """Delete a file if it exists."""
    p = Path(path)
    if p.exists():
        p.unlink()


def cleanup_temp_artifacts(path: Path | str) -> None:
    """
    Delete *path* plus every sibling temp file sharing its UUID stem.

    yt-dlp downloads video and audio as separate streams before merging, and
    leaves the intermediate ``<uuid>.f401.mp4.part`` fragments behind — tens of
    megabytes per job that only the 4-hour GC sweep would ever reclaim. Every
    artifact for one download shares the UUID that get_temp_path() generated, so
    matching on that prefix cleans them all without touching another job's files.
    """
    p = Path(path)
    stem = p.name.split(".")[0]

    # A uuid4 hex is a fixed 32 chars, so a prefix match cannot hit another job.
    if len(stem) != 32:
        cleanup_file(p)
        return

    for sibling in TEMP_DIR.glob(f"{stem}*"):
        if sibling.is_file():
            try:
                sibling.unlink()
            except OSError:
                pass
    cleanup_file(p)


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
    import config
    from job_manager import active_temp_stems, evict_expired_jobs

    gc_logger = logging.getLogger("garbage_collector")
    gc_logger.info("Starting garbage collection sweep...")

    now = time.time()
    temp_max_age_sec = config.TEMP_FILE_MAX_AGE_HOURS * 3600
    outputs_max_age_sec = config.OUTPUT_DIR_MAX_AGE_HOURS * 3600
    debug_max_age_sec = config.DEBUG_RUN_MAX_AGE_HOURS * 3600

    # Files registered to a job that has not finished are never old enough to
    # delete, however long ASR has been running on them.
    protected_stems = active_temp_stems()

    # 1. Clean expired temp files
    temp_deleted = 0
    temp_protected = 0
    if config.TEMP_DIR.exists():
        for item in config.TEMP_DIR.iterdir():
            if item.is_file():
                try:
                    mtime = item.stat().st_mtime
                    if now - mtime > temp_max_age_sec:
                        if item.name.split(".")[0] in protected_stems:
                            temp_protected += 1
                            continue
                        item.unlink()
                        temp_deleted += 1
                except Exception as e:
                    gc_logger.warning("Failed to delete temp file %s: %s", item, e)

    # 2. Clean expired output run folders
    outputs_deleted = 0
    debug_runs_kept = 0
    if config.OUTPUTS_DIR.exists():
        for run_dir in config.OUTPUTS_DIR.iterdir():
            if run_dir.is_dir():
                try:
                    is_debug_run = config.ENABLE_DEBUGGER and (run_dir / "analysis.json").exists()
                    max_age = debug_max_age_sec if is_debug_run else outputs_max_age_sec
                    if is_debug_run and max_age <= 0:
                        debug_runs_kept += 1
                        continue
                    mtime = run_dir.stat().st_mtime
                    if now - mtime > max_age:
                        shutil.rmtree(run_dir)
                        outputs_deleted += 1
                except Exception as e:
                    gc_logger.warning("Failed to delete output dir %s: %s", run_dir, e)

    # 3. Evict finished job records from memory
    jobs_evicted = evict_expired_jobs(config.JOB_RECORD_TTL_HOURS * 3600, now=now)

    gc_logger.info(
        "Garbage collection sweep completed. Deleted %d temp files (%d protected by active jobs), "
        "%d output run folders (%d debug runs retained), evicted %d job records.",
        temp_deleted,
        temp_protected,
        outputs_deleted,
        debug_runs_kept,
        jobs_evicted,
    )

