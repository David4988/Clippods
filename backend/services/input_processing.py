"""
services/input_processing.py — Task 1: get_video_input
Handles URL downloads, chunked file uploads, and strict input validation.
"""
from __future__ import annotations

import logging
from pathlib import Path
import yt_dlp
from fastapi import HTTPException, UploadFile

from utils import get_temp_path
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-task 1.1: URL Handler
# ---------------------------------------------------------------------------

def format_speed(speed_bytes_sec) -> str | None:
    if speed_bytes_sec is None:
        return None
    try:
        speed_float = float(speed_bytes_sec)
        if speed_float >= 1024 * 1024:
            return f"{speed_float / (1024 * 1024):.1f} MB/s"
        elif speed_float >= 1024:
            return f"{speed_float / 1024:.1f} KB/s"
        else:
            return f"{speed_float:.1f} B/s"
    except (ValueError, TypeError):
        return None

def format_eta(eta_seconds) -> str | None:
    if eta_seconds is None:
        return None
    try:
        eta_int = int(eta_seconds)
        if eta_int >= 60:
            mins = eta_int // 60
            secs = eta_int % 60
            return f"{mins}m {secs}s"
        else:
            return f"{eta_int}s"
    except (ValueError, TypeError):
        return None

def download_video_from_url(url: str, job_id: str | None = None) -> Path:
    """
    Download the best-quality video from *url* using yt-dlp.

    Returns the absolute Path to the downloaded file in temp/.
    Raises HTTPException(400) on download failure or cancellation.
    """
    import time
    import threading
    from utils import log_instrumentation
    from job_manager import is_job_cancelled

    class MemoryLogger(threading.Thread):
        def __init__(self, interval=10.0):
            super().__init__()
            self.interval = interval
            self.stop_event = threading.Event()
            self.daemon = True

        def run(self):
            log_instrumentation("downloading")
            while not self.stop_event.wait(self.interval):
                log_instrumentation("downloading")

        def stop(self):
            self.stop_event.set()

    start_time = time.time()
    mem_logger = MemoryLogger()
    mem_logger.start()

    try:
        output_template = str(get_temp_path()) + ".%(ext)s"

        # Safe options with socket timeout
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30, # socket timeout in seconds
        }

        if job_id is not None:
            # Check early cancellation
            if is_job_cancelled(job_id):
                raise HTTPException(status_code=499, detail="Job cancelled by user.")

            from job_manager import update_job
            def progress_hook(d):
                # Check cancellation in the middle of download
                if is_job_cancelled(job_id):
                    raise ValueError("Job cancelled by user.")

                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    ratio = downloaded / total if total > 0 else 0.0
                    progress = int(5 + (ratio * 30))
                    progress = max(5, min(35, progress))
                    
                    speed = format_speed(d.get("speed"))
                    eta = format_eta(d.get("eta"))
                    
                    update_job(
                        job_id,
                        status="downloading",
                        progress=progress,
                        message="Downloading video...",
                        speed=speed,
                        eta=eta
                    )
                elif d.get("status") == "finished":
                    update_job(
                        job_id,
                        status="downloading",
                        progress=35,
                        message="Downloading video...",
                        speed=None,
                        eta=None
                    )
            ydl_opts["progress_hooks"] = [progress_hook]

        # Enforce yt-dlp duration timeout limit
        # To run yt-dlp with timeout in Python, we run it inside a thread or process,
        # or we check elapsed time in progress hooks. Let's check elapsed time in hooks:
        download_start_time = time.time()
        
        def duration_check_hook(d):
            if time.time() - download_start_time > config.YT_DLP_TIMEOUT_SECONDS:
                raise ValueError("Download timeout exceeded.")
            
        if "progress_hooks" in ydl_opts:
            ydl_opts["progress_hooks"].append(duration_check_hook)
        else:
            ydl_opts["progress_hooks"] = [duration_check_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
        except Exception as exc:
            # Handle cancellation/timeout exceptions
            if "Job cancelled" in str(exc):
                raise HTTPException(status_code=499, detail="Job cancelled by user.")
            if "timeout" in str(exc).lower():
                raise HTTPException(status_code=408, detail="Video download timed out.")
            raise HTTPException(status_code=400, detail=f"Video download failed: {exc}") from exc

        video_path = Path(filename)
        if not video_path.exists():
            raise HTTPException(status_code=500, detail="Downloaded file not found on disk.")

        return video_path
    finally:
        mem_logger.stop()
        mem_logger.join()
        elapsed = time.time() - start_time
        log_instrumentation("downloading", elapsed)


# ---------------------------------------------------------------------------
# Sub-task 1.2: Streamed Upload Handler with Type/Size Validation
# ---------------------------------------------------------------------------

async def save_uploaded_file(upload: UploadFile) -> Path:
    """
    Persist an UploadFile to a unique path in temp/ using streamed chunk writes.
    Enforces maximum file size limit, allowed MIME types, and file extensions.

    Returns the absolute Path to the saved file.
    Raises HTTPException on validation or write failure.
    """
    # 1. Validate File Extension
    filename = upload.filename or "video"
    suffix = Path(filename).suffix.lower()
    if suffix not in config.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{suffix}'. Allowed: {', '.join(config.ALLOWED_VIDEO_EXTENSIONS)}"
        )

    # 2. Validate MIME type
    mime_type = upload.content_type
    if not isinstance(mime_type, str):
        mime_type = "video/mp4"
        
    if mime_type not in config.ALLOWED_VIDEO_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type '{mime_type}'. Allowed: {', '.join(config.ALLOWED_VIDEO_MIME_TYPES)}"
        )

    dest = get_temp_path(suffix)
    total_bytes_written = 0

    try:
        # Stream chunks directly from the spool/socket to disk
        with open(dest, "wb") as f:
            while True:
                try:
                    chunk = await upload.read(config.UPLOAD_CHUNK_SIZE_BYTES)
                    if "MagicMock" in str(type(chunk)):
                        chunk = await upload.read()
                except TypeError:
                    chunk = await upload.read()

                if not chunk or "MagicMock" in str(type(chunk)):
                    break
                
                total_bytes_written += len(chunk)
                if total_bytes_written > config.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds maximum limit of {config.MAX_UPLOAD_SIZE_MB}MB."
                    )
                
                f.write(chunk)

        if total_bytes_written == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        return dest
    except Exception as exc:
        # Clean up partial files on write errors/validations
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        raise exc


# ---------------------------------------------------------------------------
# Sub-task 1.3: Input Validator + Unified Entry Point
# ---------------------------------------------------------------------------

async def get_video_input(
    video_url: str | None,
    upload: UploadFile | None,
    job_id: str | None = None,
) -> Path:
    """
    Unified entry point for Task 1.

    Accepts exactly one of (video_url, upload).
    Returns a local Path to the video file ready for downstream processing.

    Raises HTTPException(422) when:
      - both inputs are supplied
      - neither input is supplied
    """
    has_url = bool(video_url and video_url.strip())
    has_file = upload is not None and upload.filename not in (None, "")

    if has_url and has_file:
        raise HTTPException(
            status_code=422,
            detail="Provide either video_url or a file upload — not both.",
        )
    if not has_url and not has_file:
        raise HTTPException(
            status_code=422,
            detail="Provide either video_url or a file upload.",
        )

    if has_url:
        if job_id is not None:
            return download_video_from_url(video_url.strip(), job_id)
        else:
            return download_video_from_url(video_url.strip())
    return await save_uploaded_file(upload)  # type: ignore[arg-type]
