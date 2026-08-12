# ClipPods — Team Documentation

> Developer onboarding guide for the ClipPods codebase.  
> Last Updated: 2026-07-14

---

## 1. Project Overview

### What ClipPods Does

ClipPods takes a video (YouTube URL or file upload) and automatically produces **3 short highlight clips** by:
1. Downloading/receiving the video
2. Extracting the audio track
3. Transcribing speech using Faster-Whisper (local ASR)
4. Scoring transcript windows by speech density
5. Cutting the source video at the best segments using FFmpeg

The output is 3 playable MP4 clips optimized for social media.

### Why It Exists

Content creators need to extract engaging clips from long-form video. Manual clipping is tedious. ClipPods automates the process using heuristics that don't require LLM/AI inference — making it fast, deterministic, and free of API costs.

### Main Product Flow

```
User → Submit URL or Upload File
       → Backend creates a job (returns job_id)
       → Worker thread picks up job from queue
       → Pipeline runs: download → extract audio → transcribe → select → clip
       → Clips saved to outputs/{run_uuid}/
       → User polls GET /status/{job_id} until completed
       → User downloads clips via GET /clips/{filename}
```

---

## 2. High-Level Architecture

### System Diagram

```
┌──────────────────┐     ┌─────────────────────────────────────┐
│   Web Client /   │     │           FastAPI Backend            │
│   API Consumer   │────▶│                                     │
└──────────────────┘     │  ┌─────────┐    ┌───────────────┐  │
                         │  │ Routers │───▶│  Job Manager   │  │
┌──────────────────┐     │  │ video   │    │  (in-memory)   │  │
│ Algorithm        │     │  │ analysis│    └───────┬───────┘  │
│ Debugger         │────▶│  └─────────┘            │          │
│ (React/Vite)     │     │                         ▼          │
└──────────────────┘     │  ┌──────────────────────────────┐  │
                         │  │       Worker Pool             │  │
                         │  │  (2 threads, queue max 20)    │  │
                         │  └──────────┬───────────────────┘  │
                         │             │                      │
                         │             ▼                      │
                         │  ┌──────────────────────────────┐  │
                         │  │    Processing Pipeline        │  │
                         │  │                              │  │
                         │  │  input_processing.py         │  │
                         │  │  audio_extraction.py         │  │
                         │  │  transcription.py            │  │
                         │  │  segment_selection.py        │  │
                         │  │  clip_generation.py          │  │
                         │  │  analysis_collector.py       │  │
                         │  └──────────────────────────────┘  │
                         │                                     │
                         │  ┌──────────────────────────────┐  │
                         │  │   GC Daemon (background)     │  │
                         │  │   Cleans temp/ and outputs/   │  │
                         │  └──────────────────────────────┘  │
                         └─────────────────────────────────────┘
```

### Major Systems

| System | Technology | Location | Purpose |
|---|---|---|---|
| **Backend** | FastAPI + Uvicorn | `backend/` | API server, pipeline orchestration, job management |
| **Dashboard** | React 19 + Vite 8 | `dashboard/` | Algorithm Debugger UI for inspecting execution traces |
| **Processing Pipeline** | Python + FFmpeg + Faster-Whisper | `backend/services/` | The 5-stage video→clips transformation |
| **Worker System** | `threading` + `queue.Queue` | `backend/services/job_worker.py` + `backend/job_manager.py` | Async job execution with bounded concurrency |
| **Analysis System** | Pure Python data collector | `backend/services/analysis_collector.py` | Records every algorithm decision for the debugger |

---

## 3. Repository Structure

```
SaaS_Hackathon/
├── backend/                      # Python backend (FastAPI)
│   ├── main.py                   # App entrypoint, lifecycle hooks, GC daemon
│   ├── config.py                 # All env-var configuration, constants
│   ├── job_manager.py            # In-memory job store, state machine, cancel logic
│   ├── utils.py                  # Temp paths, cleanup, instrumentation, GC sweeper
│   ├── requirements.txt          # Python dependencies
│   ├── render-build.sh           # Render deployment build script (installs ffmpeg)
│   ├── pytest.ini                # Pytest configuration
│   ├── .env.example              # Environment variable template
│   │
│   ├── routers/                  # FastAPI route handlers
│   │   ├── video.py              # /process, /process/upload, /status, /cancel, pipeline orchestration
│   │   └── analysis.py           # /dev/analysis/* debugger endpoints
│   │
│   ├── services/                 # Core processing modules
│   │   ├── input_processing.py   # URL download (yt-dlp), file upload, validation
│   │   ├── audio_extraction.py   # FFmpeg audio → 16kHz mono WAV
│   │   ├── transcription.py      # Faster-Whisper ASR
│   │   ├── segment_selection.py  # Sliding window scoring algorithm (814 lines)
│   │   ├── clip_generation.py    # FFmpeg video cutting
│   │   ├── job_worker.py         # Thread pool + job queue
│   │   ├── analysis_collector.py # Execution trace collector
│   │   └── analysis_constants.py # Version strings
│   │
│   ├── tests/                    # Test suite
│   │   ├── test_integration.py   # Full POST→poll→complete flow
│   │   ├── test_production.py    # Upload validation, cancellation, GC, stress
│   │   ├── test_segment_selection.py
│   │   ├── test_audio_extraction.py
│   │   ├── test_clip_generation.py
│   │   ├── test_input_processing.py
│   │   ├── test_transcription.py
│   │   ├── test_analysis.py
│   │   └── test_progress.py
│   │
│   ├── temp/                     # Temporary files (downloads, audio extractions)
│   └── outputs/                  # Generated clips organized by run UUID
│
├── dashboard/                    # Algorithm Debugger React app
│   ├── src/
│   │   ├── App.jsx               # Main app, tab routing, state management
│   │   ├── App.css               # Full stylesheet
│   │   ├── api/analysis.js       # Backend API client functions
│   │   ├── utils/format.js       # Time/byte formatting utilities
│   │   └── components/
│   │       ├── Timeline.jsx      # Interactive timeline visualization
│   │       ├── Clips.jsx         # Final clips display with reasoning
│   │       ├── Candidates.jsx    # Candidate explorer + comparison view
│   │       ├── Transcript.jsx    # Full transcript inspector
│   │       ├── Stats.jsx         # Aggregate statistics (Chart.js)
│   │       ├── JobSelector.jsx   # Run selector dropdown
│   │       ├── VideoOverview.jsx # Metadata summary bar
│   │       ├── TabNav.jsx        # Tab navigation
│   │       └── common.jsx        # Shared UI components
│   ├── vite.config.js            # Builds to ../static/dev-debugger/
│   └── package.json              # React 19, Chart.js, Vite 8
│
├── static/                       # Served by FastAPI's StaticFiles mount
├── clippods_contracts.md         # Original MVP contract (superseded)
├── clippods_contract_v2.md       # Current production contract
├── vercel.json                   # Vercel serverless config
└── .gitignore
```

### Folder Responsibilities

| Folder | Responsibility |
|---|---|
| `backend/routers/` | HTTP request handling. Validates input, calls services, returns responses. No business logic. |
| `backend/services/` | Core business logic. Each service is a self-contained processing step. Services don't import routers. |
| `backend/tests/` | Pytest test suite. Uses `unittest.mock` to mock FFmpeg/Whisper. Runs against `TestClient(app)`. |
| `dashboard/src/api/` | Thin API client. Maps to `/dev/analysis/*` endpoints. |
| `dashboard/src/components/` | React components for the Algorithm Debugger. Each tab is a separate component. |

---

## 4. Request Flow Walkthrough

### User Submits a URL

```
1. Client sends POST /process with { "video_url": "https://..." }
2. routers/video.py validates non-empty URL
3. job_manager.create_job() creates job entry (status=queued)
4. worker_pool.submit_job() puts task on queue.Queue
5. Response: 202 { "job_id": "uuid" }

   --- On worker thread ---
6. _run_background_job() calls _run_pipeline() via asyncio.run()
7. Pipeline stages execute sequentially:
   a. get_video_input() → yt-dlp downloads video to temp/
   b. ffmpeg.probe() → validates duration ≤ 2 hours
   c. extract_audio() → FFmpeg converts to 16kHz WAV
   d. transcribe() → Faster-Whisper produces segments
   e. select_segments() → heuristic scoring, returns 3 segments + analysis
   f. generate_clips() → FFmpeg cuts 3 clips to outputs/{run_uuid}/
   g. analysis.json is written alongside clips
8. update_job(status="completed", clips=[...])
9. Temp files (video, audio) are cleaned up in finally block
```

### User Uploads a File

```
1. Client sends POST /process/upload with multipart file
2. save_uploaded_file() streams chunks to temp/, validating:
   - Extension (.mp4, .mov, .mkv, .webm)
   - MIME type
   - Size ≤ MAX_UPLOAD_SIZE_MB
3. job_manager.create_job() creates job
4. worker_pool.submit_job() queues task
5. Response: 202 { "job_id": "uuid" }
6. Pipeline runs same as URL flow (skips download step)
```

### User Polls Status

```
1. Client sends GET /status/{job_id}
2. UUID format validated
3. job_manager.get_job() returns a copy of job state
4. If status=queued: queue_position and estimated_wait_seconds are calculated
5. elapsed_seconds is computed live for in-progress jobs
6. start_time is stripped from response
```

### User Cancels a Job

```
1. Client sends POST /cancel/{job_id}
2. UUID format validated
3. job_manager.cancel_job():
   a. Checks job is in a cancellable state
   b. Sets status=cancelled, error="Job cancelled by user."
   c. Looks up active subprocess via _active_processes dict
   d. Calls proc.kill() if subprocess exists
4. Next time pipeline code calls is_job_cancelled(), it raises HTTPException(499)
5. finally blocks clean up temp files
```

---

## 5. Core Components

### Job Manager (`job_manager.py`)

| Property | Detail |
|---|---|
| **Purpose** | Thread-safe in-memory job store with state machine semantics |
| **Data Store** | `_jobs: Dict[str, Dict]` protected by `threading.Lock` |
| **Key Functions** | `create_job()`, `update_job()`, `get_job()`, `cancel_job()`, `is_job_cancelled()` |
| **Subprocess Tracking** | `set_active_process()` / `clear_active_process()` — stores `Popen` handles for kill-on-cancel |
| **Dependencies** | None (pure Python + threading) |
| **Failure Cases** | Race conditions between cancel and completion (guarded by sentinel checks and lock) |

### Worker Pool (`services/job_worker.py`)

| Property | Detail |
|---|---|
| **Purpose** | Bounded background thread pool for job execution |
| **Queue** | `queue.Queue(maxsize=MAX_QUEUED_JOBS)` |
| **Workers** | `MAX_CONCURRENT_JOBS` daemon threads (default 2) |
| **Auto-detection** | Sets `synchronous=True` when pytest is detected, running jobs inline |
| **Dependencies** | `config.py` for limits |
| **Failure Cases** | Queue full (returns False from `submit_job`), worker thread crash (caught and logged) |

### Input Processing (`services/input_processing.py`)

| Property | Detail |
|---|---|
| **Purpose** | Acquire video from URL or upload, validate, persist to temp/ |
| **URL Download** | yt-dlp with progress hooks, speed/ETA reporting, cancellation checks |
| **Upload** | Streaming chunk writes, extension/MIME/size validation |
| **Input Validator** | Enforces exactly-one-of URL or file |
| **Dependencies** | `yt-dlp`, `config.py`, `job_manager` (for progress and cancellation) |
| **Failure Cases** | Invalid URL, download timeout, unsupported format, oversized upload |

### Audio Extraction (`services/audio_extraction.py`)

| Property | Detail |
|---|---|
| **Purpose** | Extract 16kHz mono PCM WAV from video for ASR consumption |
| **Implementation** | `ffmpeg-python` to build command, `subprocess.Popen` for execution |
| **Subprocess Tracking** | Registers process via `set_active_process()` for cancel-kill |
| **Timeout** | `FFMPEG_TIMEOUT_SECONDS` via `proc.communicate(timeout=...)` |
| **Dependencies** | `ffmpeg-python`, `config.py`, `job_manager` |
| **Failure Cases** | No audio stream, corrupt video, FFmpeg timeout, cancelled |

### Transcription (`services/transcription.py`)

| Property | Detail |
|---|---|
| **Purpose** | Speech-to-text via Faster-Whisper |
| **Model** | `base` model, CPU, int8 quantization |
| **Lazy Loading** | Thread-safe singleton with `threading.Lock` — model loads on first call |
| **Fallback** | Returns stub segment if Faster-Whisper isn't installed |
| **Output** | `TranscriptResult { segments: [{ start: float, end: float, text: str }] }` |
| **Dependencies** | `faster-whisper`, `ctranslate2` |
| **Failure Cases** | Model load failure (falls back gracefully), ASR error on corrupt audio |

### Selection Algorithm (`services/segment_selection.py`)

| Property | Detail |
|---|---|
| **Purpose** | Find the 3 best highlight windows from transcript |
| **Algorithm** | Sliding window (step=5s) with multi-heuristic scoring (max 8 points per stopping point) |
| **Key Heuristics** | Speech density, sentence boundaries, pause detection, speaker changes |
| **Filters** | Intro skip (first 5s), energy ratio (≥ 0.6 speech), overlap prevention |
| **Fallback** | Uniform distribution across timeline if insufficient candidates |
| **Analysis Mode** | When `collect_analysis=True`, records full execution trace via `AnalysisCollector` |
| **Dependencies** | `analysis_collector.py`, `analysis_constants.py` |
| **Failure Cases** | Empty transcript (falls back to uniform), `video_duration ≤ 0` (raises 400) |

### Clip Generation (`services/clip_generation.py`)

| Property | Detail |
|---|---|
| **Purpose** | Cut source video into individual MP4 clips |
| **Encoding** | `libx264` video + `aac` audio, `preset=fast`, `movflags=faststart` |
| **Audio Filters** | Volume 0.9, fade-in 0.05s at start, fade-out 0.05s at end |
| **Output** | `outputs/{run_uuid}/{run_uuid}_clip_{index}.mp4` |
| **Subprocess Tracking** | Each clip gets its own Popen, registered for cancel-kill |
| **Dependencies** | `ffmpeg-python`, `config.py`, `job_manager` |
| **Failure Cases** | Source missing, invalid segments, FFmpeg timeout/error, empty output |

### Analysis Collector (`services/analysis_collector.py`)

| Property | Detail |
|---|---|
| **Purpose** | Record every algorithm decision for the Algorithm Debugger |
| **Zero Dependencies** | No FastAPI, no FFmpeg — pure data container |
| **Captures** | Candidates, filtered windows, stopping points, decision log, final clips, aggregate stats |
| **Output** | `analysis.json` written to `outputs/{run_uuid}/` |
| **Timing** | `perf_counter_ns` for precise processing time measurement |

### Garbage Collector (`utils.py` + `main.py`)

| Property | Detail |
|---|---|
| **Purpose** | Automatically clean up expired temp files and output directories |
| **Mechanism** | Background daemon thread started on FastAPI startup |
| **Interval** | `CLEANUP_INTERVAL_SECONDS` (default 1 hour) |
| **Temp Files** | Deleted after `TEMP_FILE_MAX_AGE_HOURS` (default 4h) |
| **Output Dirs** | Deleted after `OUTPUT_DIR_MAX_AGE_HOURS` (default 24h) |
| **Shutdown** | Stopped gracefully via `threading.Event` on app shutdown |

---

## 6. Debugging Guide

### Inspecting Jobs

Jobs live in-memory. Use the status endpoint while the server is running:

```bash
# Get job status
curl http://127.0.0.1:8000/status/<job_id>

# Cancel a job
curl -X POST http://127.0.0.1:8000/cancel/<job_id>
```

Jobs are lost on server restart. If you need to debug a completed job, use the analysis system.

### Inspecting Analysis Output

Enable the debugger in your `.env`:

```bash
ENABLE_DEBUGGER=true
KEEP_ORIGINAL_FOR_DEBUG=true  # optional: saves original video for playback
```

Then use the API or dashboard:

```bash
# List all runs with analysis data
curl http://127.0.0.1:8000/dev/analysis/jobs

# Full execution trace for a run
curl http://127.0.0.1:8000/dev/analysis/<run_uuid>

# Or use the dashboard
cd dashboard && npm run dev
# Opens at http://localhost:5173
```

The `analysis.json` in each `outputs/{run_uuid}/` directory contains the raw data. Key sections:
- `candidates` — every window that passed filters, with scoring breakdown
- `filtered_windows` — windows that were rejected (and why)
- `decision_log` — step-by-step decisions (scan, filter, dedup, rank, select, extend, clamp)
- `final_clips` — the 3 selected clips with full reasoning

### Reproducing Failures

1. Check the server logs for the error message and stack trace
2. Find the `job_id` from the error log
3. If the job produced an `analysis.json`, inspect it for algorithm-level issues
4. To reproduce a specific video:
   ```bash
   curl -X POST http://127.0.0.1:8000/process \
     -H "Content-Type: application/json" \
     -d '{"video_url": "THE_FAILING_URL"}'
   ```
5. Watch logs in the terminal running uvicorn

### Where Logs Are Generated

| Logger | Location | Content |
|---|---|---|
| `routers.video` | Pipeline orchestration | Stage transitions, timing |
| `services.*` | Each service file | Service-specific events |
| `instrumentation` | `utils.py` → `log_instrumentation()` | RSS, VM, disk per stage |
| `garbage_collector` | `utils.py` → `run_garbage_collection()` | Files/dirs deleted per sweep |
| `ClipPodsGCDaemon` | `main.py` | GC daemon lifecycle |

### Diagnosing Queue Issues

- **Job stuck in `queued`**: All worker threads are occupied. Check `MAX_CONCURRENT_JOBS`.
- **503 on submit**: Queue is full (`MAX_QUEUED_JOBS`). Either wait or increase the limit.
- **Queue position not decreasing**: A long video is processing. Check the active worker's status via logs.
- **Jobs never start**: Worker pool may not have started. Check for errors in the startup log (`Starting JobWorkerPool...`).

### Diagnosing FFmpeg Failures

- **Timeout (408)**: The FFmpeg process exceeded `FFMPEG_TIMEOUT_SECONDS`. Increase the timeout or check the video for corruption.
- **Exit code != 0**: Check the stderr output in the error message. Common issues:
  - `No such file or directory` — video was cleaned up before clip gen
  - `Invalid data found` — corrupt video container
  - `Codec not found` — FFmpeg build missing libx264/aac
- **Empty output file**: FFmpeg ran but produced nothing. Check segment boundaries — `end ≤ start` is caught, but other edge cases may not be.

---

## 7. Development Setup

### Required Software

| Software | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Backend runtime |
| FFmpeg | 6.x+ | Audio extraction and clip generation |
| Node.js | 20+ | Dashboard dev server |
| Git | Any | Version control |

FFmpeg must be on your `PATH`. On Windows, install via `winget install ffmpeg` or download from ffmpeg.org.

### Environment Variables

Copy the example and configure:

```bash
cd backend
cp .env.example .env
```

Edit `.env`:

```bash
# Required for some features
SARVAM_API_KEY=your_key_here    # Only if using Sarvam integration

# Optional overrides
APP_ENV=development
ENABLE_DEBUGGER=true            # Enable /dev/* endpoints
KEEP_ORIGINAL_FOR_DEBUG=true    # Save original video for debugger
MAX_CONCURRENT_JOBS=2
MAX_QUEUED_JOBS=20
FFMPEG_TIMEOUT_SECONDS=300
YT_DLP_TIMEOUT_SECONDS=600
```

### Installation

```bash
# Backend
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt

# Dashboard
cd ../dashboard
npm install
```

### Running Backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API is now available at `http://127.0.0.1:8000`. FastAPI auto-docs at `/docs`.

### Running Dashboard

```bash
cd dashboard
npm run dev
```

Opens at `http://localhost:5173`. The dashboard proxies API calls to `http://127.0.0.1:8000` automatically in dev mode.

To build for production (outputs to `static/dev-debugger/`):

```bash
npm run build
```

### Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

Tests auto-detect the pytest environment and run the worker pool synchronously (no background threads). FFmpeg and Faster-Whisper are mocked.

---

## 8. Coding Conventions

### Naming

| Element | Convention | Example |
|---|---|---|
| Files | `snake_case.py` | `audio_extraction.py` |
| Functions | `snake_case` | `extract_audio()`, `_helper()` |
| Classes | `PascalCase` | `JobWorkerPool`, `AnalysisCollector` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_DURATION`, `ENERGY_RATIO_THRESHOLD` |
| Route paths | `lowercase/kebab-style` | `/process/upload`, `/status/{job_id}` |
| Config env vars | `UPPER_SNAKE_CASE` | `MAX_CONCURRENT_JOBS` |

### Folder Responsibilities

- **`routers/`** — HTTP layer only. Parse request, call services, format response. Never contains business logic.
- **`services/`** — Business logic. Each file is a self-contained processing step. Services import from `config`, `utils`, `job_manager` but never from `routers/`.
- **`tests/`** — One test file per service + integration tests + production tests. Test filenames mirror service names.

### Adding a New Service

1. Create `services/my_service.py`
2. Define a function with clear inputs/outputs and docstring
3. Add instrumentation: call `log_instrumentation("my_stage")` at start/end
4. Add cancellation checks if the service runs for >1 second: `if is_job_cancelled(job_id): raise HTTPException(499, ...)`
5. Register subprocess handles via `set_active_process()` if spawning processes
6. Handle cleanup in a `finally` block
7. Create `tests/test_my_service.py`

### Adding a New Route

1. Create `routers/my_router.py` with `router = APIRouter()`
2. Import and include in `main.py`: `app.include_router(my_router)`
3. All errors must use `{ "error": "..." }` shape — never expose `detail`
4. Validate UUIDs before lookup to prevent abuse
5. Add test coverage in `tests/`

### Test Conventions

- Use `unittest.mock.patch` to mock FFmpeg, yt-dlp, and Faster-Whisper
- Use `FastAPI TestClient` for integration tests
- Use `tmp_path` fixture for temporary directories
- Helper function `_wait_for_job(job_id)` polls `/status/{job_id}` with timeout
- Worker pool runs synchronously in test mode (auto-detected)
- `monkeypatch` for config overrides in tests

---

## 9. Common Pitfalls

### Long Processing Times

Videos over 30 minutes can take 60+ seconds to process. The bottleneck is usually **transcription** (Faster-Whisper on CPU). For development, use short test videos (<2 minutes).

### Cancellation Edge Cases

- Cancel can arrive between `is_job_cancelled()` checks — there's a small window where work continues after cancel
- A cancelled job's subprocess may still write output briefly after kill
- The `update_job` function guards against updating cancelled jobs (except for final error/cleanup states)
- Always test cancellation at every pipeline stage boundary

### Temporary File Leaks

- If the server crashes mid-pipeline, temp files won't be cleaned up until the GC daemon runs
- The `finally` block in `_run_pipeline` handles normal cleanup, but `SIGKILL` skips it
- For development: manually check `backend/temp/` if disk fills up

### FFmpeg Hangs

- Some corrupted videos cause FFmpeg to hang indefinitely
- The `FFMPEG_TIMEOUT_SECONDS` guard catches this, but it means a 5-minute wait before the error surfaces
- Reduce timeout for development: `FFMPEG_TIMEOUT_SECONDS=30`

### Whisper Loading Delays

- First request after cold start triggers Faster-Whisper model download (~150MB for `base`)
- Subsequent requests use the cached model (lazy singleton)
- On serverless (Vercel), the model downloads every cold start — this is slow

### Queue Starvation

- With `MAX_CONCURRENT_JOBS=2` and a 2-minute video, both workers are blocked for ~90 seconds
- All other jobs wait in queue with `queue_position` incrementing
- Solution: Increase `MAX_CONCURRENT_JOBS` if the host has enough RAM (each worker uses ~500MB during transcription)

### Invalid Uploads

- Files with wrong extensions but correct MIME types are rejected (extension check is first)
- Files with correct extensions but wrong MIME types are also rejected
- Zero-byte files pass extension/MIME checks but fail the "empty file" check after streaming
- The `MagicMock` checks in upload code exist because `unittest.mock` objects in tests don't behave like real chunk iterators

---

## 10. Contribution Guide

### Before Making Changes

1. **Read the relevant service code end-to-end**. Each service has clear docstrings and comments explaining the why.
2. **Understand the data flow**: input → service → output. Check what upstream services produce and what downstream services expect.
3. **Check the contract** (`clippods_contract_v2.md`) for API behavior expectations.

### Making Changes Safely

1. **Modify the smallest layer possible**. If you're changing scoring logic, only touch `segment_selection.py` — don't restructure the router.
2. **Add tests for new behavior**. Follow the existing pattern in the corresponding `test_*.py` file.
3. **Verify cleanup behavior**: Run your change and check that `backend/temp/` doesn't accumulate files.
4. **Verify cancellation behavior**: Submit a job, cancel it mid-processing, and confirm:
   - Status becomes `cancelled`
   - No zombie subprocesses (check with `ps` or Task Manager)
   - Temp files are cleaned up
5. **Verify instrumentation**: If you add a new pipeline stage, call `log_instrumentation("stage_name")` at start and end.
6. **Run the full test suite** before pushing:
   ```bash
   cd backend && python -m pytest tests/ -v
   ```

### PR Checklist

- [ ] Changes are scoped to the minimum necessary files
- [ ] New functions have docstrings
- [ ] Tests added or updated
- [ ] No hardcoded paths or secrets
- [ ] Temp file cleanup verified (check `finally` blocks)
- [ ] Cancellation works at new code boundaries
- [ ] No new dependencies without discussion
- [ ] `config.py` updated if new env vars are introduced
- [ ] Contract docs updated if API shape changes

### Architecture Decisions

If your change involves:
- Adding a new endpoint
- Adding a new external dependency
- Changing the job state machine
- Modifying the pipeline stage order
- Adding persistent storage

...then write a brief Architecture Decision Record (ADR) and discuss with the team before implementing. The current architecture is intentionally simple, and complexity should be added only when justified.
