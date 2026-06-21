"""
routers/video.py — POST /process endpoint
Orchestrates Tasks 1–5 and returns the final clip list.

Two routes per the contract:
  • application/json    → {"video_url": "string"}
  • multipart/form-data → file field

All errors are returned as {"error": "..."} per the contract — never {"detail": "..."}.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

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


class ProcessVideoResponse(BaseModel):
    """Contract-defined success response."""
    clips: list[str]   # ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]


# ---------------------------------------------------------------------------
# Error mapping — converts pipeline HTTPExceptions to contract error strings
#
# Contract (clippods_contracts.md):
#   400 (invalid URL / bad file)  → "Invalid video URL"
#   502/504 (Sarvam / ASR)        → "Audio not clear enough"
#   400 (video too long)          → "Video too long (max 15 minutes)"
#   422 (both / neither input)    → handled in main.py validation handler
#   any other                     → re-raise as {"error": detail}
# ---------------------------------------------------------------------------

def _error_response(exc: HTTPException) -> JSONResponse:
    """Map a pipeline HTTPException to the contract-defined error shape."""
    detail = str(exc.detail).lower()

    if exc.status_code == 422:
        if "not both" in detail:
            msg = "Provide either video_url or file, not both"
        else:
            msg = "No input provided"

    elif exc.status_code in (502, 504):
        # Sarvam / network errors → ASR failure message
        msg = "Audio not clear enough"

    elif "too long" in detail or "max 2" in detail or "duration" in detail:
        msg = "Video too long (max 2 hours)"

    elif exc.status_code == 400:
        # Covers download failure, missing file, no audio track, corrupt video
        msg = "Invalid video URL"

    else:
        msg = exc.detail  # 500s — pass raw detail through


# ---------------------------------------------------------------------------
# Pipeline Orchestrator (shared by both routes)
# ---------------------------------------------------------------------------

async def _run_pipeline(
    video_url: Optional[str],
    upload: Optional[UploadFile],
) -> list[str]:
    """
    Full pipeline: Input → Audio → Transcribe → Select → Cut → Cleanup.

    Returns basenames ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"].
    Temp files are always cleaned up, even on failure.
    """
    video_path: Optional[Path] = None
    audio_path: Optional[str]  = None

    try:
        # ── Task 1: get_video_input ─────────────────────────────────────────
        logger.info("Pipeline: resolving video input")
        video_path = await get_video_input(video_url, upload)

        # ── Duration guard (contract: max 2 hours) ─────────────────────────
        try:
            probe          = ffmpeg_lib.probe(str(video_path))
            video_duration = float(probe["format"]["duration"])
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read video duration: {exc}",
            ) from exc

        MAX_DURATION = 120 * 60  # 7200 seconds
        if video_duration > MAX_DURATION:
            raise HTTPException(
                status_code=400,
                detail="Video too long (max 2 hours)",
            )
        logger.info("Pipeline: video duration %.1fs — within limit", video_duration)

        # ── Task 2: extract_audio ───────────────────────────────────────────
        logger.info("Pipeline: extracting audio from %s", video_path)
        audio_path = await asyncio.to_thread(extract_audio, str(video_path))

        # ── Task 3: transcribe ──────────────────────────────────────────────
        logger.info("Pipeline: transcribing audio")
        transcript = await asyncio.to_thread(transcribe, audio_path)
        segments   = transcript["segments"]

        # ── Task 4: select_segments ─────────────────────────────────────────
        # video_duration already probed and validated by the duration guard above
        logger.info("Pipeline: selecting segments (video_duration=%.2fs)", video_duration)
        selected = select_segments(segments, video_duration)

        # ── Task 5: generate_clips ──────────────────────────────────────────
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
#   POST /process
#   {"video_url": "https://..."}
# ---------------------------------------------------------------------------

@router.post(
    "/process",
    summary="Process a video URL and return 3 highlight clips",
    response_description="Basenames of the generated clip files",
)
async def process_video_url(body: VideoUrlRequest):
    """
    **POST /process** — `application/json`

    ```json
    { "video_url": "https://youtube.com/..." }
    ```

    Success: `{"clips": ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]}`
    Failure: `{"error": "..."}`
    """
    try:
        clip_names = await _run_pipeline(video_url=body.video_url, upload=None)
        return {"clips": clip_names}
    except HTTPException as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("Unexpected error in process_video_url")
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Route 2: Multipart upload — Content-Type: multipart/form-data
#   POST /process/upload
#   file=<video binary>
# ---------------------------------------------------------------------------

@router.post(
    "/process/upload",
    summary="Upload a video file and return 3 highlight clips",
    response_description="Basenames of the generated clip files",
)
async def process_video_upload(
    file: UploadFile = File(..., description="Video file to process"),
):
    """
    **POST /process/upload** — `multipart/form-data`

    Upload a video file in the `file` field.

    Success: `{"clips": ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]}`
    Failure: `{"error": "..."}`
    """
    try:
        clip_names = await _run_pipeline(video_url=None, upload=file)
        return {"clips": clip_names}
    except HTTPException as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("Unexpected error in process_video_upload")
        return JSONResponse(status_code=500, content={"error": str(exc)})
