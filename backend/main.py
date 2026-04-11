import os
import uuid
import shutil
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List

from backend.config import STORAGE_ROOT, MAX_CLIP_COUNT
from backend.models import Job, Segment, Clip, TranscriptChunk
from backend.services.transcription import transcribe_chunk
from backend.services.highlight import score_segments, select_highlights
# from backend.services.clip import render_clip  # ML Engineer 2 – uncomment when ready

app = FastAPI(title="ClipPods SaaS", description="Automated Podcast Clipping API – Tamil / Hindi / Telugu")

# ── Static assets & frontend pages ──────────────────────────────────────────
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", include_in_schema=False)
async def serve_landing():
    return FileResponse("index.html")

@app.get("/app", include_in_schema=False)
async def serve_app():
    return FileResponse("app.html")

# ── Storage directories ──────────────────────────────────────────────────────
UPLOADS_DIR = os.path.join(STORAGE_ROOT, "uploads")
OUTPUTS_DIR = os.path.join(STORAGE_ROOT, "outputs")

for _d in [UPLOADS_DIR, OUTPUTS_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── In-memory job store (replace with Redis/DB in production) ────────────────
_jobs: dict[str, dict] = {}


# ── Pipeline helpers ─────────────────────────────────────────────────────────

async def _split_audio(audio_path: str, video_id: str) -> List[str]:
    """Phase 1.5 – Chunk audio into 5-min segments (overlap 10 s)."""
    print(f"[PIPELINE] Splitting audio into chunks: {audio_path}")
    await asyncio.sleep(1)  # replace with real ffmpeg chunking
    return [
        os.path.join(UPLOADS_DIR, f"{video_id}_chunk0.wav"),
        os.path.join(UPLOADS_DIR, f"{video_id}_chunk1.wav"),
    ]


async def _extract_audio_from_url(url: str, video_id: str) -> tuple[str, str]:
    """Phase 1 – Download video & extract audio via yt-dlp + ffmpeg."""
    video_path = os.path.join(UPLOADS_DIR, f"{video_id}.mp4")
    audio_path = os.path.join(UPLOADS_DIR, f"{video_id}_audio.wav")
    print(f"[PIPELINE] Downloading: {url}")
    await asyncio.sleep(2)  # replace with real yt-dlp call
    return video_path, audio_path


async def _run_pipeline(video_id: str, video_path: str, audio_path: str):
    """Core multi-phase pipeline (runs in background)."""
    try:
        _jobs[video_id]["status"] = "chunking"

        # Phase 1.5 – Chunk audio
        chunks = await _split_audio(audio_path, video_id)

        # Phase 2 – Transcribe all chunks in parallel (ML Engineer 1)
        _jobs[video_id]["status"] = "transcribing"
        transcripts: List[TranscriptChunk] = await asyncio.gather(
            *[transcribe_chunk(c) for c in chunks]
        )

        # Merge transcripts into flat word list
        all_words = [w for t in transcripts for w in t.words]
        full_text = " ".join(t.merged_text for t in transcripts)

        # Phase 3 – Build segments from word timestamps
        _jobs[video_id]["status"] = "segmenting"
        segments = _build_segments(all_words, video_id)

        # Phase 4 – Score & select highlights (ML Engineer 2)
        _jobs[video_id]["status"] = "highlighting"
        scored = score_segments(segments)
        highlights = select_highlights(scored, max_count=MAX_CLIP_COUNT)

        # Phase 5 – Render clips (ML Engineer 2 – clip.py)
        _jobs[video_id]["status"] = "rendering"
        clips = _mock_render_clips(highlights, video_path, video_id)

        _jobs[video_id].update({"status": "completed", "clips": [c.dict() for c in clips]})
        print(f"[PIPELINE] ✅ Job {video_id} complete – {len(clips)} clips generated.")

    except Exception as exc:
        _jobs[video_id]["status"] = "failed"
        _jobs[video_id]["error"] = str(exc)
        print(f"[PIPELINE] ❌ Job {video_id} failed: {exc}")


def _build_segments(words, video_id: str) -> List[Segment]:
    """Group word-level timestamps into ~30-word segments."""
    segments = []
    WINDOW = 30
    for i, start in enumerate(range(0, len(words), WINDOW)):
        chunk_words = words[start: start + WINDOW]
        if not chunk_words:
            break
        text = " ".join(w.word for w in chunk_words)
        segments.append(Segment(
            id=f"{video_id}_seg{i}",
            text=text,
            start_time=chunk_words[0].start_time,
            end_time=chunk_words[-1].end_time,
            sentence_count=text.count(".") + 1,
        ))
    return segments


def _mock_render_clips(highlights: List[Segment], video_path: str, video_id: str) -> List[Clip]:
    """Temporary mock – replace with clip.render_clip() calls."""
    clips = []
    for idx, seg in enumerate(highlights):
        out_path = os.path.join(OUTPUTS_DIR, f"{video_id}_clip{idx}.mp4")
        clips.append(Clip(
            id=f"{video_id}_clip{idx}",
            segment_id=seg.id,
            start_time=seg.start_time,
            end_time=seg.end_time,
            file_path=out_path,
            duration=seg.end_time - seg.start_time,
        ))
    return clips


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Direct file upload endpoint."""
    job_id = str(uuid.uuid4())
    video_path = os.path.join(UPLOADS_DIR, f"{job_id}_{file.filename}")
    audio_path = os.path.join(UPLOADS_DIR, f"{job_id}_audio.wav")

    with open(video_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    _jobs[job_id] = {"status": "queued", "clips": []}
    background_tasks.add_task(_run_pipeline, job_id, video_path, audio_path)
    return {"job_id": job_id, "status": "queued", "message": "File received. Processing started."}


@app.post("/api/url-ingest")
async def ingest_url(payload: dict, background_tasks: BackgroundTasks):
    """YouTube / direct video URL ingest endpoint."""
    url: str = payload.get("url", "")
    if not url:
        raise HTTPException(status_code=422, detail="url field is required")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "clips": []}

    async def _url_wrapper():
        video_path, audio_path = await _extract_audio_from_url(url, job_id)
        await _run_pipeline(job_id, video_path, audio_path)

    background_tasks.add_task(_url_wrapper)
    return {"job_id": job_id, "status": "queued", "message": "URL accepted. Processing started."}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Poll job status and retrieve clip list when complete."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@app.get("/api/clips/{job_id}/{clip_filename}")
async def download_clip(job_id: str, clip_filename: str):
    """Stream a rendered clip file."""
    clip_path = os.path.join(OUTPUTS_DIR, clip_filename)
    if not os.path.exists(clip_path):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(clip_path, media_type="video/mp4", filename=clip_filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
