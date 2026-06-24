import threading
import time
import uuid
from typing import Dict, Optional

# Sentinel to distinguish between non-passed parameters and parameters set to None
_SENTINEL = object()

# Global job store and lock
_jobs: Dict[str, Dict[str, Optional[object]]] = {}
_lock = threading.Lock()

def create_job() -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "start_time": time.time(),
            "elapsed_seconds": 0,
            "speed": None,
            "eta": None,
            "clips": None,
            "error": None
        }
    return job_id

def update_job(
    job_id: str,
    *,
    status: Optional[str] = _SENTINEL,
    progress: Optional[int] = _SENTINEL,
    message: Optional[str] = _SENTINEL,
    speed: Optional[str] = _SENTINEL,
    eta: Optional[str] = _SENTINEL,
    clips: Optional[list] = _SENTINEL,
    error: Optional[str] = _SENTINEL
) -> None:
    """Safely update fields of a job entry."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status is not _SENTINEL:
            job["status"] = status
            if status in ("completed", "error"):
                job["elapsed_seconds"] = int(time.time() - job["start_time"])
        if progress is not _SENTINEL:
            job["progress"] = progress
        if message is not _SENTINEL:
            job["message"] = message
        if speed is not _SENTINEL:
            job["speed"] = speed
        if eta is not _SENTINEL:
            job["eta"] = eta
        if clips is not _SENTINEL:
            job["clips"] = clips
        if error is not _SENTINEL:
            job["error"] = error

def get_job(job_id: str) -> Optional[Dict[str, Optional[object]]]:
    """Retrieve a copy of the job entry if it exists."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        # Return a copy and dynamically calculate elapsed_seconds for active jobs
        job_copy = dict(job)
        if job_copy.get("status") not in ("completed", "error"):
            job_copy["elapsed_seconds"] = int(time.time() - job_copy["start_time"])
        # Do not expose start_time in the JSON response
        job_copy.pop("start_time", None)
        return job_copy

