# Technology Stack & Build System

## Core Stack

**Backend Framework:** FastAPI 0.137.2 (Python async web framework)
**Python Version:** 3.x (uses modern type hints and async/await)
**Deployment:** Vercel (serverless Python) + Render (alternative)

## Key Dependencies

### Video/Audio Processing
- `ffmpeg-python` 0.2.0 — FFmpeg wrapper for audio extraction and clip generation
- `yt-dlp` 2026.6.9 — Video download from URLs (YouTube, etc.)
- `av` — Low-level video container handling

### Speech Recognition
- `faster-whisper` — Local ASR (Automatic Speech Recognition) using Whisper base model
- `ctranslate2` — Optimized inference backend for Whisper

### Web Framework
- `fastapi` 0.137.2 — Modern async web framework
- `uvicorn` 0.49.0 — ASGI server
- `python-multipart` 0.0.32 — File upload support
- `python-dotenv` 1.2.2 — Environment variable management
- `httpx` 0.28.1 — Async HTTP client

### Testing
- `pytest` 9.1.0 — Testing framework
- `pytest-asyncio` 1.4.0 — Async test support

### Utilities
- `pydantic` 2.13.4 — Data validation and serialization
- `psutil` 7.2.2 — System resource monitoring

## Project Structure

```
SaaS_Hackathon/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── job_manager.py       # Background job tracking (in-memory)
│   ├── utils.py             # Shared helpers (temp paths, cleanup, instrumentation)
│   ├── routers/
│   │   └── video.py         # /process endpoints (URL + upload)
│   ├── services/            # Core business logic (one file per pipeline task)
│   │   ├── input_processing.py      # Task 1: URL download / file upload
│   │   ├── audio_extraction.py      # Task 2: FFmpeg audio extraction
│   │   ├── transcription.py         # Task 3: Faster-Whisper ASR
│   │   ├── segment_selection.py     # Task 4: Highlight selection algorithm
│   │   └── clip_generation.py       # Task 5: FFmpeg clip cutting
│   ├── tests/               # Pytest test suite
│   └── outputs/             # Generated clips (unique UUID directories)
├── static/
│   └── index.html           # Single-page frontend UI
└── vercel.json              # Deployment config
```

## Common Commands

### Local Development

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run specific test file
pytest tests/test_segment_selection.py

# Run tests with verbose output
pytest -v
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run specific test
pytest tests/test_integration.py::test_full_pipeline
```

### Environment Setup

```bash
# Copy example env file
cp backend/.env.example backend/.env

# Required environment variables:
# SARVAM_API_KEY=your_api_key  (if using Sarvam AI extensions)
# APP_ENV=development
```

### Deployment

**Vercel:**
```bash
vercel deploy
```

**Render:**
```bash
# Uses render-build.sh to download static ffmpeg binaries
./backend/render-build.sh
```

## Architecture Patterns

### Pipeline Architecture
Each service module implements one discrete task in the video processing pipeline. Tasks are executed sequentially in `routers/video.py`.

### Error Handling
- All services raise `HTTPException` with appropriate status codes
- Contract-compliant error format: `{"error": "message"}` (never `{"detail": "..."}`)
- Custom 422 validation error handler for consistent error responses

### Resource Management
- All temp files are cleaned up in `finally` blocks
- Unique UUID-based file naming prevents collisions
- Instrumentation logging tracks memory/disk usage at each stage

### Job Tracking
- In-memory job store (thread-safe with locks)
- Background threads for async-like processing without actual async workers
- Job status includes: queued, downloading, extracting_audio, transcribing, selecting_segments, generating_clips, completed, error

### FFmpeg Usage
- Audio extraction: 16kHz mono PCM WAV for Whisper compatibility
- Clip generation: Uses re-encoding (libx264 + aac) with audio/video fades
- Accurate seeking: `-ss` before input for frame-accurate cuts
