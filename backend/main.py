"""
ClipPods — FastAPI Backend
Endpoints: POST /jobs, GET /jobs/{id}, GET /jobs/{id}/clips, GET /clips/{id}/{file}
"""

import uuid
import os
import shutil
import logging
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio

from config import UPLOAD_DIR, OUTPUT_DIR

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
log = logging.getLogger("clippods")

from services.transcription import transcribe
from services.highlight import generate_highlights
from services.clip import extract_clip

app = FastAPI(title="ClipPods API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

class JobState(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    clips: List[Dict] = []
    error: Optional[str] = None

# In-memory job store (no database for MVP)
jobs: dict[str, JobState] = {}
PIPELINE_SEMAPHORE = asyncio.Semaphore(2)  # matches ML1 max_workers=2


@app.on_event("startup")
async def startup_cleanup():
    """Wipe orphan upload/temp files from previous crashes."""
    for d in [UPLOAD_DIR]:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            log.info(f"Startup cleanup: wiped {d}")
    os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload", status_code=202)
async def create_job(file: UploadFile, background_tasks: BackgroundTasks):
    # Issue 3: Upload size guard
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {MAX_UPLOAD_BYTES // (1024*1024)}MB."
        )

    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    file_path = os.path.join(job_dir, "raw.mp3")
    with open(file_path, "wb") as f:
        f.write(contents)

    jobs[job_id] = JobState(job_id=job_id, status="uploaded")
    background_tasks.add_task(process_job, job_id, file_path)
    return {"job_id": job_id, "status": "uploaded"}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {"status": job.status, "progress": job.progress}


@app.get("/results/{job_id}")
async def get_results(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet")
    return {"clips": job.clips}


@app.get("/clips/{job_id}/{filename}")
async def serve_clip(job_id: str, filename: str):
    path = os.path.join(OUTPUT_DIR, job_id, "clips", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="audio/mpeg")


# --- Background Pipeline ---

async def process_job(job_id: str, audio_path: str):
    async with PIPELINE_SEMAPHORE:
        try:
            job = jobs[job_id]
            # Step 1: Transcribe (ML1)
            job.status = "processing_ml1"
            job.progress = 10
            try:
                segments = await asyncio.to_thread(transcribe, audio_path)
            except RuntimeError as e:
                job.status = "failed"
                job.error = str(e)
                return

            # Step 2: Highlights (ML2)
            job.status = "processing_ml2"
            job.progress = 40
            clips = generate_highlights(segments)

            # Task 5.1: Empty Result Handling
            if not clips:
                job.status = "completed"
                job.progress = 100
                job.clips = []
                return

            # Task 4.1: FFmpeg Extraction Loop
            job.status = "generating_clips"
            job.progress = 80
            clips_dir = os.path.join(OUTPUT_DIR, job_id, "clips")
            os.makedirs(clips_dir, exist_ok=True)

            clip_results = []
            for i, clip in enumerate(clips):
                out_path = os.path.join(clips_dir, f"clip_{i+1:03d}.mp3")

                # Issue 2: Guard FFmpeg failures
                try:
                    await asyncio.to_thread(extract_clip, audio_path, clip["start_sec"], clip["end_sec"], out_path)
                except Exception as e:
                    log.warning(f"FFmpeg failed for clip {i+1}: {e}")
                    continue

                if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                    log.warning(f"Clip {i+1} missing or empty, skipping.")
                    continue

                # Task 4.2 Data Mapping
                clip["clip_id"] = f"clip_{i+1:03d}"
                clip["rank"] = i + 1
                clip["audio_url"] = f"/outputs/{job_id}/clips/clip_{i+1:03d}.mp3"
                clip_results.append(clip)

            # Cleanup raw upload
            try:
                job_upload_dir = os.path.join(UPLOAD_DIR, job_id)
                if os.path.isdir(job_upload_dir):
                    shutil.rmtree(job_upload_dir, ignore_errors=True)
            except OSError:
                pass

            job.status = "completed"
            job.progress = 100
            job.clips = clip_results

        except Exception as e:
            job = jobs.get(job_id)
            if job:
                job.status = "failed"
                job.error = str(e)
