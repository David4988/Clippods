import threading
import time
import uuid
from typing import Dict, Optional, Any

# Sentinel to distinguish between non-passed parameters and parameters set to None
_SENTINEL = object()

# Global job store and locks
_jobs: Dict[str, Dict[str, Optional[object]]] = {}
_jobs_lock = threading.Lock()

# Active subprocess store (for cancellation)
_active_processes: Dict[str, Any] = {}
_processes_lock = threading.Lock()

# Global cancelled set (to check cancellations fast without locks where possible, or just lock)
def create_job() -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "start_time": time.time(),
            "elapsed_seconds": 0,
            "speed": None,
            "eta": None,
            "clips": None,
            "error": None,
            "run_uuid": None
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
    error: Optional[str] = _SENTINEL,
    run_uuid: Optional[str] = _SENTINEL
) -> None:
    """Safely update fields of a job entry."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        
        # Prevent updates to cancelled jobs, except final error/cleanup
        if job.get("status") == "cancelled" and status not in ("completed", "error"):
            return

        if status is not _SENTINEL:
            job["status"] = status
            if status in ("completed", "error", "cancelled"):
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
        if run_uuid is not _SENTINEL:
            job["run_uuid"] = run_uuid

def get_job(job_id: str) -> Optional[Dict[str, Optional[object]]]:
    """Retrieve a copy of the job entry if it exists, calculating queue position."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        
        job_copy = dict(job)
        if job_copy.get("status") not in ("completed", "error", "cancelled"):
            job_copy["elapsed_seconds"] = int(time.time() - job_copy["start_time"])
        
        # Calculate queue position for queued jobs
        if job_copy.get("status") == "queued":
            # List all queued jobs sorted by start_time
            queued_jobs = [
                (jid, j["start_time"])
                for jid, j in _jobs.items()
                if j.get("status") == "queued"
            ]
            queued_jobs.sort(key=lambda x: x[1])
            
            try:
                position = [x[0] for x in queued_jobs].index(job_id) + 1
                job_copy["queue_position"] = position
                job_copy["estimated_wait_seconds"] = position * 45 # assume 45s per queued video highlight run
            except ValueError:
                job_copy["queue_position"] = 1
                job_copy["estimated_wait_seconds"] = 45
        else:
            job_copy["queue_position"] = None
            job_copy["estimated_wait_seconds"] = None

        # Do not expose start_time in the JSON response
        job_copy.pop("start_time", None)
        return job_copy

# ---------------------------------------------------------------------------
# Subprocess Tracking (Milestone 8)
# ---------------------------------------------------------------------------

def set_active_process(job_id: str, proc: Any) -> None:
    """Store the running subprocess handle for the job."""
    with _processes_lock:
        _active_processes[job_id] = proc

def clear_active_process(job_id: str) -> None:
    """Clear the active subprocess entry for the job."""
    with _processes_lock:
        _active_processes.pop(job_id, None)

# ---------------------------------------------------------------------------
# Job Cancellation (Milestone 8)
# ---------------------------------------------------------------------------

def cancel_job(job_id: str) -> bool:
    """
    Cancel an in-progress or queued job.
    Kills the running subprocess if registered, and updates job status to 'cancelled'.

    Returns True if successfully cancelled, False otherwise.
    """
    # 1. Update job status
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return False
        
        cancellable_states = {
            "queued",
            "downloading",
            "extracting_audio",
            "transcribing",
            "selecting_segments",
            "generating_clips"
        }
        if job.get("status") not in cancellable_states:
            return False

        job["status"] = "cancelled"
        job["message"] = "Job cancelled by user."
        job["error"] = "Job cancelled by user."
        job["elapsed_seconds"] = int(time.time() - job["start_time"])

    # 2. Terminate the active subprocess
    with _processes_lock:
        proc = _active_processes.pop(job_id, None)
        if proc:
            try:
                proc.kill()
            except OSError:
                pass

    return True

def is_job_cancelled(job_id: str | None) -> bool:
    """Check if the job is cancelled."""
    if not job_id:
        return False
    with _jobs_lock:
        job = _jobs.get(job_id)
        return job is not None and job.get("status") == "cancelled"
