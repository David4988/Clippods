import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List

from config import STORAGE_ROOT, MAX_CLIP_COUNT, CHUNK_DURATION_SECONDS, CHUNK_OVERLAP_SECONDS
from models import Job, Segment, Clip, TranscriptChunk
from services.transcription import transcribe_chunk
from services.highlight import score_segments, select_highlights
from services.clip import generate_clips

app = FastAPI(
    title="ClipPods SaaS",
    description="Automated Podcast Clipping API – Tamil / Hindi / Telugu",
)

# ── Static assets ─────────────────────────────────────────────────────────────
# FIX: mount ONLY a safe public folder, not "." (project root exposes source code)
_FRONTEND_PUBLIC = "frontend/public"
os.makedirs(_FRONTEND_PUBLIC, exist_ok=True)
app.mount("/static", StaticFiles(directory=_FRONTEND_PUBLIC), name="static")


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

# ── In-memory job store (replace with Redis/DB for multi-worker production) ──
_jobs: dict[str, dict] = {}

# ── Concurrency gate: max 3 simultaneous pipeline jobs ───────────────────────
_pipeline_semaphore = asyncio.Semaphore(3)

# ── Upload policy ─────────────────────────────────────────────────────────────
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024           # 500 MB hard cap
_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav"}


# ── Pipeline helpers ──────────────────────────────────────────────────────────

async def _split_audio(audio_path: str, video_id: str) -> List[str]:
    """Phase 1.5 – Chunk audio into CHUNK_DURATION_SECONDS segments (with overlap)."""
    print(f"[PIPELINE] Probing duration: {audio_path}")

    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=30)
    duration = float(stdout.decode().strip() or "0")

    chunk_paths: List[str] = []
    for i, start in enumerate(range(0, int(duration), CHUNK_DURATION_SECONDS)):
        chunk_path = os.path.join(UPLOADS_DIR, f"{video_id}_chunk{i}.wav")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(CHUNK_DURATION_SECONDS + CHUNK_OVERLAP_SECONDS),
            "-i", audio_path,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            chunk_path,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0:
            chunk_paths.append(chunk_path)
            print(f"[PIPELINE] ✅ Chunk {i}: {chunk_path}")
        else:
            print(f"[PIPELINE] ❌ Chunk {i} failed: {stderr.decode()}")

    return chunk_paths


async def _extract_audio_from_url(url: str, video_id: str) -> tuple[str, str]:
    """Phase 1 – Download via yt-dlp then extract 16 kHz mono WAV via ffmpeg."""
    video_path = os.path.join(UPLOADS_DIR, f"{video_id}.mp4")
    audio_path = os.path.join(UPLOADS_DIR, f"{video_id}_audio.wav")

    print(f"[PIPELINE] yt-dlp downloading: {url}")
    ydl = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", video_path,
        url,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(ydl.communicate(), timeout=600)
    if ydl.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {stderr.decode()}")

    print(f"[PIPELINE] Extracting audio → {audio_path}")
    ffmpeg = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(ffmpeg.communicate(), timeout=120)
    if ffmpeg.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {stderr.decode()}")

    return video_path, audio_path


async def _run_pipeline(video_id: str, video_path: str, audio_path: str):
    """Core multi-phase pipeline – runs inside a BackgroundTask."""
    async with _pipeline_semaphore:
        try:
            # Phase 1 – Extract audio if not already done (direct uploads)
            if not os.path.exists(audio_path):
                _jobs[video_id]["status"] = "extracting_audio"
                print(f"[PIPELINE] Extracting audio → {audio_path}")
                ffmpeg = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(ffmpeg.communicate(), timeout=300)
                if ffmpeg.returncode != 0:
                    raise RuntimeError(f"Audio extraction failed: {stderr.decode()}")
                print(f"[PIPELINE] ✅ Audio extracted: {audio_path}")

            # Phase 1.5 – Chunk audio
            _jobs[video_id]["status"] = "chunking"
            chunks = await _split_audio(audio_path, video_id)

            # Phase 2 – Transcribe all chunks in parallel (ML Engineer 1)
            _jobs[video_id]["status"] = "transcribing"
            transcripts: List[TranscriptChunk] = await asyncio.gather(
                *[transcribe_chunk(c) for c in chunks]
            )

            # Merge transcripts into flat word list
            all_words = [w for t in transcripts for w in t.words]

            # Phase 3 – Build segments from word timestamps
            _jobs[video_id]["status"] = "segmenting"
            segments = _build_segments(all_words, video_id)

            # Phase 4 – Score & select highlights (CPU-bound → offloaded to thread)
            _jobs[video_id]["status"] = "highlighting"
            scored = await asyncio.to_thread(score_segments, segments)
            highlights = await asyncio.to_thread(select_highlights, scored, MAX_CLIP_COUNT)

            # Phase 5 – Render clips with non-blocking async FFmpeg
            _jobs[video_id]["status"] = "rendering"
            clip_results = await generate_clips(video_path, highlights, video_id)

            # clip_results is a list of (segment_index, path) tuples —
            # use the index to correctly map each clip to its source highlight,
            # even when some clips in the middle fail.
            clips = [
                Clip(
                    id=f"{video_id}_clip{seg_idx}",
                    segment_id=highlights[seg_idx].id,
                    start_time=highlights[seg_idx].start_time,
                    end_time=highlights[seg_idx].end_time,
                    file_path=clip_path,
                    duration=highlights[seg_idx].end_time - highlights[seg_idx].start_time,
                )
                for seg_idx, clip_path in clip_results
            ]

            # Persist results into the job store
            _jobs[video_id]["status"] = "completed"
            _jobs[video_id]["clips"] = [c.dict() for c in clips]
            print(f"[PIPELINE] ✅ Job {video_id} completed – {len(clips)} clip(s).")

        except Exception as exc:
            _jobs[video_id]["status"] = "failed"
            _jobs[video_id]["error"] = str(exc)
            print(f"[PIPELINE] ❌ Job {video_id} failed: {exc}")

        finally:
            # Clean up extracted audio to free disk space
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    print(f"[PIPELINE] 🧹 Removed temp audio: {audio_path}")
                except OSError:
                    pass


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


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Direct file upload endpoint."""

    # FIX: Validate file extension before touching disk
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    job_id = str(uuid.uuid4())
    video_path = os.path.join(UPLOADS_DIR, f"{job_id}_{file.filename}")
    audio_path = os.path.join(UPLOADS_DIR, f"{job_id}_audio.wav")

    # FIX: Stream upload 1 MB at a time with a hard 500 MB size cap
    written = 0
    with open(video_path, "wb") as buf:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > _MAX_UPLOAD_BYTES:
                buf.close()
                os.remove(video_path)
                raise HTTPException(
                    status_code=413,
                    detail="File too large. Maximum allowed size is 500 MB.",
                )
            buf.write(chunk)

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

    # FIX: Path traversal protection – reject any filename that escapes OUTPUTS_DIR
    safe_root = os.path.realpath(OUTPUTS_DIR)
    clip_path = os.path.realpath(os.path.join(OUTPUTS_DIR, clip_filename))
    if not clip_path.startswith(safe_root + os.sep):
        raise HTTPException(status_code=403, detail="Access denied.")

    if not os.path.exists(clip_path):
        raise HTTPException(status_code=404, detail="Clip not found")

    return FileResponse(clip_path, media_type="video/mp4", filename=clip_filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
