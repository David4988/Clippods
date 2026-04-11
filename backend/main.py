"""
ClipPods — FastAPI Backend
Endpoints: POST /jobs, GET /jobs/{id}, GET /jobs/{id}/clips, GET /clips/{id}/{file}
"""

import uuid
import os
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import UPLOAD_DIR, OUTPUT_DIR
from services.transcription import transcribe
from services.highlight import chunk_transcript, score_chunks
from services.clip import extract_clip

app = FastAPI(title="ClipPods API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (no database for MVP)
jobs: dict[str, dict] = {}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/jobs")
async def create_job(file: UploadFile, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    file_path = os.path.join(job_dir, "raw.mp3")
    with open(file_path, "wb") as f:
        f.write(await file.read())

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "clips": [],
        "error": None,
    }

    background_tasks.add_task(process_job, job_id, file_path)
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/jobs/{job_id}/clips")
async def get_clips(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"clips": jobs[job_id]["clips"]}


@app.get("/clips/{job_id}/{filename}")
async def serve_clip(job_id: str, filename: str):
    path = os.path.join(OUTPUT_DIR, job_id, "clips", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="audio/mpeg")


# --- Background Pipeline ---

def process_job(job_id: str, audio_path: str):
    try:
        # Step 1: Transcribe
        jobs[job_id]["status"] = "transcribing"
        jobs[job_id]["progress"] = 10
        segments = transcribe(audio_path)

        # Step 2: Chunk
        jobs[job_id]["status"] = "chunking"
        jobs[job_id]["progress"] = 40
        chunks = chunk_transcript(segments)

        # Step 3: Score
        jobs[job_id]["status"] = "scoring"
        jobs[job_id]["progress"] = 60
        scored = score_chunks(chunks, audio_path)

        # Step 4: Extract top clips
        jobs[job_id]["status"] = "extracting"
        jobs[job_id]["progress"] = 80
        clips_dir = os.path.join(OUTPUT_DIR, job_id, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        clip_results = []
        for i, sc in enumerate(scored[:5]):
            out_path = os.path.join(clips_dir, f"clip_{i+1:03d}.mp3")
            extract_clip(audio_path, sc.start_sec, sc.end_sec, out_path)
            clip_results.append({
                "clip_id": f"clip_{i+1:03d}",
                "rank": i + 1,
                "score": sc.score,
                "start_sec": sc.start_sec,
                "end_sec": sc.end_sec,
                "duration_sec": sc.duration_sec,
                "transcript": sc.text[:200],
                "audio_url": f"/clips/{job_id}/clip_{i+1:03d}.mp3",
            })

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["clips"] = clip_results

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
