"""
ClipPods — FastAPI Backend
Endpoints: POST /jobs, GET /jobs/{id}, GET /jobs/{id}/clips, GET /clips/{id}/{file}

Fixed: proper error handling at every pipeline step, guards against empty results.
Frontend is served as static files from the project root.
"""

import uuid
import os
import traceback
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, BackgroundTasks, HTTPException, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import static_ffmpeg
static_ffmpeg.add_paths()

from .config import UPLOAD_DIR, OUTPUT_DIR
from .services.transcription import transcribe
from .services.translation import translate_segments
from .services.highlight import chunk_transcript, score_chunks
from .services.clip import extract_video_clip, mux_video_with_audio
from .services.tts import generate_clip_audio

app = FastAPI(title="ClipPods SaaS Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve project root reliably regardless of the uvicorn worker/reloader subprocess
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)

# In-memory job store (no database for MVP)
jobs: dict[str, dict] = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    """Serve the landing page (index.html)."""
    return FileResponse(os.path.join(_ROOT_DIR, "index.html"))


@app.post("/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    source_lang: str = Form("ta-IN"),
    target_lang: str = Form(""),
):
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    if not file and not youtube_url:
        raise HTTPException(status_code=400, detail="Must provide either file or youtube_url")

    # If the user uploaded a file, we save it immediately
    file_path = None
    if file and file.filename:
        ext = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
        file_path = os.path.join(job_dir, f"input{ext}")
        with open(file_path, "wb") as f:
            f.write(await file.read())

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "clips": [],
        "error": None,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }

    background_tasks.add_task(process_job, job_id, file_path, youtube_url, source_lang, target_lang)
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
    media_type = "video/mp4" if filename.endswith(".mp4") else "audio/mpeg"
    return FileResponse(path, media_type=media_type)


# --- Background Pipeline ---

def process_job(job_id: str, audio_path: Optional[str], youtube_url: Optional[str], source_lang: str, target_lang: str):
    from .services.download import download_youtube_video
    try:
        # Step 0: Download if needed
        if youtube_url and not (audio_path and os.path.exists(audio_path)):
            jobs[job_id]["status"] = "downloading"
            jobs[job_id]["progress"] = 5
            job_dir = os.path.join(UPLOAD_DIR, job_id)
            audio_path = download_youtube_video(youtube_url, job_dir)
            print(f"OK Step 0 done: Downloaded youtube video to {audio_path}")

        print(f"\n{'='*50}")
        print(f"--- Processing job {job_id}")
        print(f"   File: {audio_path}")
        print(f"   Language: {source_lang} -> {target_lang or 'none'}")
        print(f"{'='*50}")

        from .services.clip import preprocess_video
        
        # Step 0.5: Preprocess video
        processed_path = os.path.join(UPLOAD_DIR, job_id, "processed.mp4")
        audio_path = preprocess_video(audio_path, processed_path)
        print(f"OK Step 0.5 done: Preprocessed video at {audio_path}")
        
        # Step 1: Transcribe
        jobs[job_id]["status"] = "transcribing"
        jobs[job_id]["progress"] = 10
        segments = transcribe(audio_path, source_lang)
        print(f"OK Step 1 done: {len(segments)} segments")

        # Step 1.5: Translate (optional)
        if target_lang:
            jobs[job_id]["status"] = "translating"
            jobs[job_id]["progress"] = 25
            segments = translate_segments(segments, source_lang, target_lang)
            print(f"OK Step 1.5 done: translated {len(segments)} segments")

        # Step 2: Chunk
        jobs[job_id]["status"] = "chunking"
        jobs[job_id]["progress"] = 40
        chunks = chunk_transcript(segments)
        print(f"OK Step 2 done: {len(chunks)} chunks")

        if not chunks:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["clips"] = []
            print("WARNING No chunks produced — completing with 0 clips")
            return

        # Step 3: Score
        jobs[job_id]["status"] = "scoring"
        jobs[job_id]["progress"] = 60
        scored = score_chunks(chunks, audio_path)
        print(f"OK Step 3 done: {len(scored)} scored chunks")

        if not scored:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["clips"] = []
            print("WARNING No scored chunks — completing with 0 clips")
            return

        # Step 4: Extract top clips
        jobs[job_id]["status"] = "extracting"
        jobs[job_id]["progress"] = 80
        clips_dir = os.path.join(OUTPUT_DIR, job_id, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        clip_results = []
        for i, sc in enumerate(scored[:5]):
            try:
                out_path = os.path.join(clips_dir, f"clip_{i+1:03d}.mp4")
                
                if target_lang:
                    print(f"  INFO Synthesizing TTS & muxing video for clip {i+1}...")
                    tts_path = os.path.join(clips_dir, f"tts_{i+1:03d}.mp3")
                    raw_video = os.path.join(clips_dir, f"raw_{i+1:03d}.mp4")
                    
                    generate_clip_audio(sc.text, target_lang, tts_path)
                    extract_video_clip(audio_path, sc.start_sec, sc.end_sec, raw_video)
                    mux_video_with_audio(raw_video, tts_path, out_path)
                    
                    try:
                        os.remove(tts_path)
                        os.remove(raw_video)
                    except:
                        pass
                else:
                    extract_video_clip(audio_path, sc.start_sec, sc.end_sec, out_path)

                clip_results.append({
                    "clip_id": f"clip_{i+1:03d}",
                    "rank": i + 1,
                    "score": sc.score,
                    "start_sec": sc.start_sec,
                    "end_sec": sc.end_sec,
                    "duration_sec": sc.duration_sec,
                    "transcript": sc.text[:200],
                    "audio_url": f"/clips/{job_id}/clip_{i+1:03d}.mp4",
                })
                print(f"  OK Clip {i+1}: {sc.start_sec:.1f}s–{sc.end_sec:.1f}s (score {sc.score})")
            except Exception as clip_err:
                print(f"  WARNING Clip {i+1} extraction failed: {clip_err}")

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["clips"] = clip_results
        print(f"DONE Job {job_id} completed with {len(clip_results)} clips!")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        print(f"ERROR Job {job_id} FAILED: {e}")
        traceback.print_exc()

# Mount all frontend static files (index.html, app.html, app.css, app.js, etc.)
# html=True makes it serve index.html for "/" automatically
# This MUST be the last mount — it acts as the catch-all
app.mount("/", StaticFiles(directory=_ROOT_DIR, html=True), name="frontend")
