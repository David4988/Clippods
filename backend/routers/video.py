"""
routers/video.py — POST /process endpoint
Orchestrates Tasks 1–5 and returns the final clip list.

Two routes per the contract:
  • application/json    → {\"video_url\": \"string\"}
  • multipart/form-data → file field

All errors are returned as {\"error\": \"...\"} per the contract — never {\"detail\": \"...\"}.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

from job_manager import create_job, update_job, get_job

import ffmpeg as ffmpeg_lib
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.audio_extraction import extract_audio
from services.clip_generation import generate_clips
from services.input_processing import get_video_input
from services.segment_selection import select_segments
from services.transcription import transcribe
from utils import cleanup_file

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class VideoUrlRequest(BaseModel):
    """JSON body for URL-based input — Content-Type: application/json."""
    video_url: str

# ---------------------------------------------------------------------------
# Pipeline Orchestrator (shared by both routes)
# ---------------------------------------------------------------------------

async def _run_pipeline(
    video_url: Optional[str],
    upload: Optional[UploadFile],
) -> list[str]:
    """
    Full pipeline: Input → Audio → Transcribe → Select → Cut → Cleanup.

    Returns basenames [\"clip_0.mp4\", \"clip_1.mp4\", \"clip_2.mp4\"].
    Temp files are always cleaned up, even on failure.
    """
    video_path: Optional[Path] = None
    audio_path: Optional[str] = None
    try:
        # Task 1: get_video_input
        logger.info("Pipeline: resolving video input")
        video_path = await get_video_input(video_url, upload)

        # Duration guard (max 2 hours)
        try:
            probe = ffmpeg_lib.probe(str(video_path))
            video_duration = float(probe["format"]["duration"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read video duration: {exc}") from exc
        MAX_DURATION = 120 * 60
        if video_duration > MAX_DURATION:
            raise HTTPException(status_code=400, detail="Video too long (max 2 hours)")
        logger.info("Pipeline: video duration %.1fs — within limit", video_duration)

        # Task 2: extract_audio
        logger.info("Pipeline: extracting audio from %s", video_path)
        audio_path = await asyncio.to_thread(extract_audio, str(video_path))

        # Task 3: transcribe
        logger.info("Pipeline: transcribing audio")
        transcript = await asyncio.to_thread(transcribe, audio_path)
        segments = transcript["segments"]

        # Task 4: select_segments
        logger.info("Pipeline: selecting segments (video_duration=%.2fs)", video_duration)
        selected = select_segments(segments, video_duration)

        # Task 5: generate_clips
        logger.info("Pipeline: generating %d clips", len(selected))
        clip_paths = await asyncio.to_thread(generate_clips, str(video_path), selected)
        return [Path(p).name for p in clip_paths]
    finally:
        if video_path is not None:
            cleanup_file(video_path)
            logger.info("Cleaned up video temp: %s", video_path)
        if audio_path is not None:
            cleanup_file(audio_path)
            logger.info("Cleaned up audio temp: %s", audio_path)

# ---------------------------------------------------------------------------
# Route 1: JSON body — Content-Type: application/json
# ---------------------------------------------------------------------------

@router.post("/process")
async def process_video_url(body: VideoUrlRequest):
    job_id = create_job()
    def _background():
        update_job(job_id, status="queued")
        try:
            clip_names = asyncio.run(_run_pipeline(video_url=body.video_url, upload=None))
            update_job(job_id, status="completed", clips=clip_names)
        except Exception as exc:
            logger.exception("Background job error")
            update_job(job_id, status="error", error=str(exc))
    threading.Thread(target=_background, daemon=True).start()
    return {"job_id": job_id}

# ---------------------------------------------------------------------------
# Route 2: Multipart upload — Content-Type: multipart/form-data
# ---------------------------------------------------------------------------

@router.post("/process/upload")
async def process_video_upload(file: UploadFile = File(...)):
    job_id = create_job()
    def _background():
        update_job(job_id, status="queued")
        try:
            clip_names = asyncio.run(_run_pipeline(video_url=None, upload=file))
            update_job(job_id, status="completed", clips=clip_names)
        except Exception as exc:
            logger.exception("Background job error")
            update_job(job_id, status="error", error=str(exc))
    threading.Thread(target=_background, daemon=True).start()
    return {"job_id": job_id}

# ---------------------------------------------------------------------------
# Job status endpoint
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}", tags=["Job Status"])
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return job
