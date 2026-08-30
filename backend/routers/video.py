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
import os
import uuid
from pathlib import Path
from typing import Optional

from job_manager import create_job, update_job, get_job, cancel_job, is_job_cancelled
from services.job_worker import worker_pool

import ffmpeg as ffmpeg_lib
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.audio_extraction import extract_audio
from services.clip_generation import generate_clips
from services.input_processing import get_video_input, save_uploaded_file
from services.segment_selection import select_segments
from services.transcription import transcribe
from utils import cleanup_file, cleanup_temp_artifacts
from config import KEEP_ORIGINAL_FOR_DEBUG

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
    video_path: Optional[Path] = None,
    job_id: Optional[str] = None,
) -> list[str]:
    """
    Full pipeline: Input → Audio → Transcribe → Select → Cut → Cleanup.

    Returns basenames ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"].
    Temp files are always cleaned up, even on failure.
    Also generates analysis.json for the Algorithm Debugger.
    """
    audio_path: Optional[str] = None
    try:
        # Check cancellation before starting
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # Task 1: get_video_input
        if video_path is not None:
            logger.info("Pipeline: using uploaded file path")
        else:
            logger.info("Pipeline: downloading video from URL")
            if job_id is not None:
                update_job(job_id, status="downloading", progress=5, message="Downloading video...")
            video_path = await get_video_input(video_url, None, job_id=job_id)

        # Check cancellation after download/input saving
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # Uploads jump straight from 5% to 40% with a long silent gap while
        # ffprobe + audio extraction run. Report the analysis step so the UI has
        # something to move.
        if job_id is not None:
            update_job(job_id, status="extracting_audio", progress=20, message="Analyzing video...")

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
        if job_id is not None:
            update_job(job_id, status="extracting_audio", progress=40, message="Extracting audio...")
        
        # Pass job_id so FFmpeg subprocess is registered and can be cancelled
        audio_path = await asyncio.to_thread(extract_audio, str(video_path), job_id)

        # Check cancellation after audio extraction
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # Task 3: transcribe
        logger.info("Pipeline: transcribing audio")
        if job_id is not None:
            update_job(job_id, status="transcribing", progress=60, message="Transcribing audio...")
        transcript = await asyncio.to_thread(transcribe, audio_path)
        segments = transcript["segments"]

        # Check cancellation after transcription
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # Task 4: select_segments (with analysis collection)
        logger.info("Pipeline: selecting segments (video_duration=%.2fs)", video_duration)
        if job_id is not None:
            update_job(job_id, status="selecting_segments", progress=75, message="Selecting highlights...")

        result = select_segments(segments, video_duration, collect_analysis=True)
        if isinstance(result, tuple):
            selected, analysis_data = result
        else:
            selected = result
            analysis_data = None

        # Check cancellation after segment selection
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # Task 5: generate_clips
        logger.info("Pipeline: generating %d clips", len(selected))
        if job_id is not None:
            update_job(job_id, status="generating_clips", progress=80, message="Generating clips...")
        
        # Pass job_id so FFmpeg cutting subprocesses can be cancelled
        clip_paths = await asyncio.to_thread(generate_clips, str(video_path), selected, job_id)

        # Check cancellation after clip generation
        if is_job_cancelled(job_id):
            raise HTTPException(status_code=499, detail="Job cancelled by user.")

        # --- Save analysis.json alongside clips ---
        if analysis_data is not None and clip_paths:
            try:
                import json
                import shutil

                clip_dir = Path(clip_paths[0]).parent
                run_uuid = clip_dir.name

                # Enrich metadata
                analysis_data["meta"]["job_id"] = job_id
                analysis_data["meta"]["run_uuid"] = run_uuid
                analysis_data["meta"]["source"] = "youtube" if video_url else "upload"
                analysis_data["meta"]["source_url"] = video_url
                analysis_data["meta"]["filename"] = Path(str(video_path)).name

                # Enrich final clips with filenames
                for i, fc in enumerate(analysis_data.get("final_clips", [])):
                    if i < len(clip_paths):
                        fc["filename"] = Path(clip_paths[i]).name

                # Write analysis.json
                analysis_path = clip_dir / "analysis.json"
                analysis_path.write_text(
                    json.dumps(analysis_data, indent=2, ensure_ascii=False)
                )
                logger.info("Pipeline: saved analysis.json to %s", analysis_path)

                # Copy original video for debugger playback (based on config)
                if KEEP_ORIGINAL_FOR_DEBUG and video_path is not None:
                    ext = Path(str(video_path)).suffix or ".mp4"
                    original_dest = clip_dir / f"original{ext}"
                    shutil.copy2(str(video_path), str(original_dest))
                    logger.info("Pipeline: copied original video for debugger to %s", original_dest)

                # Store run_uuid in job for API lookup
                if job_id is not None:
                    update_job(job_id, run_uuid=run_uuid)

            except Exception as exc:
                # Analysis saving is non-critical — don't fail the pipeline
                logger.warning("Pipeline: failed to save analysis.json: %s", exc)

        # Build rich metadata clip list
        rich_clips = []
        for i, path_str in enumerate(clip_paths):
            seg = selected[i]
            rich_clips.append({
                "filename": Path(path_str).name,
                "score": seg.get("score", 85),
                "title": f"Clip {i + 1}",
                "duration": round(seg["end"] - seg["start"], 1)
            })
        return rich_clips
    finally:
        if video_path is not None:
            # Also removes yt-dlp's leftover .part fragments for this download.
            cleanup_temp_artifacts(video_path)
            logger.info("Cleaned up video temp: %s", video_path)
        if audio_path is not None:
            cleanup_file(audio_path)
            logger.info("Cleaned up audio temp: %s", audio_path)

def _job_error_message(exc: BaseException) -> str:
    """
    Render an exception for display in the UI. str(HTTPException) is
    "400: <detail>", and that status-code prefix is noise for the end user.
    """
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc) or exc.__class__.__name__


def _run_background_job(job_id: str, video_url: Optional[str], video_path: Optional[Path] = None):
    """
    Submits _run_pipeline to the correct execution mode.
    If there is a running event loop (testing environment), schedules it on the current loop.
    Otherwise, runs it using asyncio.run() on the background worker thread.
    """
    import asyncio
    
    # Check if there is an active running event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Testing environment with active loop (e.g. TestClient)
        coro = _run_pipeline(video_url=video_url, video_path=video_path, job_id=job_id)
        task = loop.create_task(coro)
        
        def on_done(t):
            try:
                clip_names = t.result()
                if is_job_cancelled(job_id):
                    return
                update_job(job_id, status="completed", progress=100, message="Completed successfully", clips=clip_names)
            except Exception as exc:
                if is_job_cancelled(job_id) or "cancelled" in str(exc).lower():
                    logger.info("Background job %s successfully stopped by cancellation.", job_id)
                    update_job(job_id, status="cancelled", error="Job cancelled by user.")
                else:
                    logger.exception("Background job error")
                    update_job(job_id, status="error", error=_job_error_message(exc), message="Processing failed")
            finally:
                if video_path and video_path.exists():
                    try:
                        video_path.unlink()
                    except OSError:
                        pass
        task.add_done_callback(on_done)
    else:
        # Production worker thread
        try:
            if is_job_cancelled(job_id):
                return
            clip_names = asyncio.run(_run_pipeline(video_url=video_url, video_path=video_path, job_id=job_id))
            if is_job_cancelled(job_id):
                return
            update_job(job_id, status="completed", progress=100, message="Completed successfully", clips=clip_names)
        except Exception as exc:
            if is_job_cancelled(job_id) or "cancelled" in str(exc).lower():
                logger.info("Background job %s successfully stopped by cancellation.", job_id)
                update_job(job_id, status="cancelled", error="Job cancelled by user.")
            else:
                logger.exception("Background job error")
                update_job(job_id, status="error", error=_job_error_message(exc), message="Processing failed")
        finally:
            if video_path and video_path.exists():
                try:
                    video_path.unlink()
                except OSError:
                    pass

# ---------------------------------------------------------------------------
# Route 1: JSON body — Content-Type: application/json
# ---------------------------------------------------------------------------

@router.post("/process", status_code=status.HTTP_202_ACCEPTED)
async def process_video_url(body: VideoUrlRequest):
    # Validate non-empty URL
    if not body.video_url.strip():
        return JSONResponse(status_code=400, content={"error": "Provide a video_url URL."})

    job_id = create_job()

    # Synchronous test bypass
    if getattr(worker_pool, "synchronous", False):
        try:
            update_job(job_id, status="downloading", progress=5, message="Downloading video...")
            clip_names = await _run_pipeline(video_url=body.video_url, job_id=job_id)
            update_job(job_id, status="completed", progress=100, message="Completed successfully", clips=clip_names)
        except Exception as exc:
            update_job(job_id, status="error", error=_job_error_message(exc), message="Processing failed")
        return {"job_id": job_id}

    def _background_run():
        update_job(job_id, status="downloading", progress=5, message="Downloading video...")
        _run_background_job(job_id, video_url=body.video_url)

    # Submit job task to worker pool queue
    queued = worker_pool.submit_job(job_id, _background_run)
    if not queued:
        # Queue full
        update_job(job_id, status="error", error="Server load limit exceeded. Queue is full.")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Server is busy. Please try again later."}
        )

    return {"job_id": job_id}

# ---------------------------------------------------------------------------
# Route 2: Multipart upload — Content-Type: multipart/form-data
# ---------------------------------------------------------------------------

@router.post("/process/upload", status_code=status.HTTP_202_ACCEPTED)
async def process_video_upload(file: UploadFile = File(...)):
    # Stream and validate the file upload to disk in chunks
    try:
        saved_path = await save_uploaded_file(file)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": f"File upload failed: {exc}"})

    job_id = create_job()

    # Synchronous test bypass
    if getattr(worker_pool, "synchronous", False):
        try:
            update_job(job_id, status="processing", progress=5, message="Queued")
            clip_names = await _run_pipeline(video_url=None, video_path=saved_path, job_id=job_id)
            update_job(job_id, status="completed", progress=100, message="Completed successfully", clips=clip_names)
        except Exception as exc:
            update_job(job_id, status="error", error=_job_error_message(exc), message="Processing failed")
        finally:
            if saved_path.exists():
                try:
                    saved_path.unlink()
                except OSError:
                    pass
        return {"job_id": job_id}

    def _background_run():
        update_job(job_id, status="processing", progress=5, message="Queued")
        _run_background_job(job_id, video_url=None, video_path=saved_path)

    # Submit job task to worker pool queue
    queued = worker_pool.submit_job(job_id, _background_run)
    if not queued:
        # Clean up the file upload immediately if queue is full
        if saved_path.exists():
            try:
                saved_path.unlink()
            except OSError:
                pass
        update_job(job_id, status="error", error="Server load limit exceeded. Queue is full.")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Server is busy. Please try again later."}
        )

    return {"job_id": job_id}

# ---------------------------------------------------------------------------
# Job status endpoint
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}", tags=["Job Status"])
async def get_job_status(job_id: str):
    # Validate job_id looks like a valid UUID before lookup to prevent system abuse
    try:
        uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid job ID format"})

    job = get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return job

# ---------------------------------------------------------------------------
# Job Cancellation Endpoint (Milestone 8)
# ---------------------------------------------------------------------------

@router.post("/cancel/{job_id}", tags=["Job Status"])
async def process_job_cancellation(job_id: str):
    # Validate job_id format
    try:
        uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid job ID format"})

    cancelled = cancel_job(job_id)
    if not cancelled:
        # Check if job exists
        job = get_job(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"error": "Job not found"})
        return JSONResponse(
            status_code=400,
            content={"error": f"Job is in '{job['status']}' status and cannot be cancelled."}
        )
    
    return {"status": "cancelled", "message": "Job cancellation request sent successfully."}
