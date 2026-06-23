"""
services/input_processing.py — Task 1: get_video_input
Handles URL downloads, file uploads, and input validation.
"""
from pathlib import Path

import yt_dlp
from fastapi import HTTPException, UploadFile

from utils import get_temp_path


# ---------------------------------------------------------------------------
# Sub-task 1.1: URL Handler
# ---------------------------------------------------------------------------

def download_video_from_url(url: str) -> Path:
    """
    Download the best-quality video from *url* using yt-dlp.

    Returns the absolute Path to the downloaded file in temp/.
    Raises HTTPException(400) on download failure.
    """
    import time
    import threading
    from utils import log_instrumentation

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

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as exc:
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
# Sub-task 1.2: Upload Handler
# ---------------------------------------------------------------------------

async def save_uploaded_file(upload: UploadFile) -> Path:
    """
    Persist an UploadFile to a unique path in temp/.

    Returns the absolute Path to the saved file.
    Raises HTTPException(400) if the file is empty.
    """
    suffix = Path(upload.filename or "video").suffix or ".mp4"
    dest = get_temp_path(suffix)

    contents = await upload.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    dest.write_bytes(contents)
    return dest


# ---------------------------------------------------------------------------
# Sub-task 1.3: Input Validator + Unified Entry Point
# ---------------------------------------------------------------------------

async def get_video_input(
    video_url: str | None,
    upload: UploadFile | None,
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
        return download_video_from_url(video_url.strip())  # type: ignore[arg-type]
    return await save_uploaded_file(upload)  # type: ignore[arg-type]
