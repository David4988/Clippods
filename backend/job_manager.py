import threading
import uuid
from typing import Dict, Optional

# Global job store and lock
_jobs: Dict[str, Dict[str, Optional[object]]] = {}
_lock = threading.Lock()

def create_job() -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {"status": "queued", "clips": None, "error": None}
    return job_id

def update_job(job_id: str, *, status: Optional[str] = None, clips: Optional[list] = None, error: Optional[str] = None) -> None:
    """Safely update fields of a job entry."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status is not None:
            job["status"] = status
        if clips is not None:
            job["clips"] = clips
        if error is not None:
            job["error"] = error

def get_job(job_id: str) -> Optional[Dict[str, Optional[object]]]:
    """Retrieve a copy of the job entry if it exists."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        # Return a shallow copy to avoid external mutation
        return dict(job)
