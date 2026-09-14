# 🎬 ClipPods

> **Automated video highlight clipper** — Extract the most engaging segments from any video and produce short, polished MP4 clips ready for social media.

ClipPods takes a video (YouTube URL or file upload) and automatically produces **3 short highlight clips** by analyzing speech density, without requiring any LLM/AI inference — making it fast, deterministic, and free of API costs.

---

## ✨ Features

- **YouTube URL & File Upload** — Submit a YouTube link or upload MP4, MOV, MKV, WebM files
- **Automatic Highlight Detection** — Scores transcript windows by speech density to find the best segments
- **3 Optimized Clips** — Generates 3 ready-to-share MP4 clips per video
- **Real-time Progress Tracking** — Poll job status while processing runs in the background
- **Job Cancellation** — Cancel in-progress jobs at any time
- **Algorithm Debugger Dashboard** — React-based debugger UI for heuristic tuning and analysis
- **Automatic Cleanup** — Garbage collection for temp files and expired outputs

---

## 🏗️ Architecture

```
User → Submit URL or Upload File
       → Backend creates a job (returns job_id)
       → Worker thread picks up job from queue
       → Pipeline: download → extract audio → transcribe → select → clip
       → Clips saved to outputs/{run_uuid}/
       → User polls GET /status/{job_id} until completed
       → User downloads clips via GET /clips/{filename}
```

### Tech Stack

| Component          | Technology                                |
| ------------------ | ----------------------------------------- |
| Backend Framework  | Python 3.12+, FastAPI                     |
| ASR Engine         | Faster-Whisper (base model, CPU, int8)    |
| Video Processing   | FFmpeg (libx264 + AAC) via `ffmpeg-python`|
| Video Download     | yt-dlp                                    |
| Dashboard          | React 19, Vite 8, Chart.js               |
| Deployment         | Render (VPS) + Cloudflare Tunnel          |

---

## 📁 Project Structure

```
SaaS_Hackathon/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Centralized configuration
│   ├── job_manager.py          # In-memory job tracking
│   ├── utils.py                # Shared utilities & garbage collection
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example            # Environment variable template
│   ├── routers/
│   │   ├── video.py            # Video upload & processing endpoints
│   │   └── analysis.py         # Algorithm debugger endpoints
│   ├── services/
│   │   ├── input_processing.py # URL download & file upload handling
│   │   ├── audio_extraction.py # Audio track extraction via FFmpeg
│   │   ├── transcription.py    # Speech-to-text via Faster-Whisper
│   │   ├── segment_selection.py# Speech-density scoring & selection
│   │   ├── clip_generation.py  # Final clip cutting via FFmpeg
│   │   ├── job_worker.py       # Worker pool management
│   │   └── analysis_collector.py # Debugger data collection
│   └── tests/                  # Pytest test suite
├── dashboard/                  # React + Vite algorithm debugger UI
│   ├── src/
│   │   ├── App.jsx             # Main application component
│   │   ├── components/         # UI components (TabNav, Clips, etc.)
│   │   ├── api/                # API client layer
│   │   └── utils/              # Frontend utilities
│   ├── package.json
│   └── vite.config.js
├── static/                     # Static assets
├── vercel.json                 # Vercel deployment config
└── README.md                   # ← You are here
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12 or 3.13.** Not 3.14 — the `av` dependency (pulled in by
  `faster-whisper`) has no wheels for 3.14 and fails to build from source. Without
  `faster-whisper`, every job fails at the transcription step with
  "Transcription is unavailable".
- **Node.js 18+** and **npm** (only needed for the Algorithm Debugger dashboard)
- **FFmpeg** — `ffmpeg` and `ffprobe` on `PATH`
- **cloudflared** — the tunnel is already configured in `~/.cloudflared/config.yml`
  and maps `api.theclippods.com` → `http://127.0.0.1:8000`

### 1. Clone the Repository

```bash
git clone <repo-url>
cd SaaS_Hackathon
```

### 2. Backend Setup

The virtual environment lives at the **repository root**, not inside `backend/`.
`.venv312` is the development environment: run the server, tests and the
evaluation harness with its interpreter. `backend/requirements.lock.txt` pins the
exact versions (including the ASR stack), so transcripts are reproducible.

**macOS / Linux:**

```bash
# From the repository root. Pin the interpreter — see Prerequisites.
python3.12 -m venv .venv312
source .venv312/bin/activate

pip install -r backend/requirements.txt -c backend/requirements.lock.txt
```

**Windows (PowerShell):**

```powershell
# From the repository root. Pin the interpreter — see Prerequisites.
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1

pip install -r backend\requirements.txt -c backend\requirements.lock.txt
```

> If `py -3.12` isn't found, install Python 3.12 or 3.13 from python.org
> (not the Microsoft Store version — it's often missing or aliased) and make
> sure "Add python.exe to PATH" is checked during setup.
>
> Use the `.\` prefix when running `Activate.ps1` — PowerShell treats a bare
> `.venv312\Scripts\Activate.ps1` as a module name, not a relative script path,
> and errors with "The module '.venv312' could not be loaded". If you instead
> hit "running scripts is disabled on this system", the execution policy is
> blocking it; run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
> in that terminal session and retry.

Verify that transcription is actually available before demoing — this must print
`ok`, otherwise every job fails at transcription:

```bash
# macOS/Linux
.venv312/bin/python -c "import faster_whisper; print('ok')"
```

```powershell
# Windows
.venv312\Scripts\python.exe -c "import faster_whisper; print('ok')"
```

### 3. Environment Variables

All settings have working defaults — **no `.env` file is required to run the app.**
Settings are read from real environment variables and from `backend/.env`
(real environment variables win). `SARVAM_API_KEY` in `backend/.env.example` is a
leftover: no code reads it, and transcription runs locally on Faster-Whisper.

```bash
cp backend/.env.example backend/.env   # optional
```

| Variable                   | Description                        | Default       |
| -------------------------- | ---------------------------------- | ------------- |
| `APP_ENV`                  | Application environment            | `development` |
| `ENABLE_DEBUGGER`          | Enable algorithm debugger          | `false`       |
| `MAX_CONCURRENT_JOBS`      | Worker thread pool size            | `2`           |
| `MAX_QUEUED_JOBS`          | Maximum queued jobs                | `20`          |
| `MAX_UPLOAD_SIZE_MB`       | Max upload file size (MB)          | `100`         |
| `FFMPEG_TIMEOUT_SECONDS`   | FFmpeg subprocess timeout          | `300`         |
| `YT_DLP_TIMEOUT_SECONDS`   | yt-dlp download timeout            | `600`         |
| `MAX_VIDEO_DURATION_SECONDS` | Longest accepted video (seconds) | `7200`        |
| `TEMP_FILE_MAX_AGE_HOURS`  | Temp file age before cleanup (files of running jobs are never removed) | `4` |
| `OUTPUT_DIR_MAX_AGE_HOURS` | Output run folder age before cleanup | `24`        |
| `DEBUG_RUN_MAX_AGE_HOURS`  | With `ENABLE_DEBUGGER=true`: age before runs with `analysis.json` are removed (`0` = keep) | `0` |
| `JOB_RECORD_TTL_HOURS`     | How long finished jobs stay queryable via `/status` | `24` |
| `CLIPPODS_EVAL_DIR`        | Offline evaluation data directory  | `<repo>/eval_data` |

### 4. Dashboard Setup

```bash
cd dashboard
npm install
```

---

## ▶️ Running the Project

The backend serves **both** the API and the landing/upload UI (`static/index.html`),
so the demo needs the backend and the tunnel — nothing else.

### 1. Start the Backend Server

Must be run from `backend/`, because `main.py` imports `config`, `routers`, and
`services` as top-level modules.

**macOS / Linux:**

```bash
cd backend
../.venv312/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Windows (PowerShell):**

```powershell
cd backend
..\.venv312\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- UI: `http://127.0.0.1:8000/`
- API: `http://127.0.0.1:8000/health`

Bind to `127.0.0.1`, not `0.0.0.0` — the Cloudflare Tunnel connects over loopback,
and there is no authentication on these endpoints.

> **Windows note:** if only Python 3.11 is available on the machine (no 3.12/3.13
> install), the app still runs — `faster-whisper`'s `av` dependency ships prebuilt
> wheels for 3.11 too. Just make sure the `faster_whisper` import check above
> prints `ok`; only Python 3.14 is known to break the build.

### 2. Start the Cloudflare Tunnel

In a separate terminal. `~/.cloudflared/config.yml` already pins the tunnel ID and
the ingress rule, so no arguments are needed:

```bash
cloudflared tunnel run
```

Public URL: `https://api.theclippods.com` — this serves the full app, not just the API.

> Cloudflare's free plan rejects request bodies over **100 MB** at the edge, before
> they reach the app. Keep demo uploads under that; the UI now checks the size
> client-side and says so.

### 3. Start the Dashboard (optional — Algorithm Debugger only)

The debugger is a separate developer tool and is **not** part of the demo flow. Its
endpoints return 403 unless `ENABLE_DEBUGGER=true`.

```bash
cd dashboard
npm install
npm run dev            # http://localhost:5173
```

Start the backend with `ENABLE_DEBUGGER=true` if you want it to return data.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `POST` | `/process` | Submit a video URL. JSON body `{"video_url": "..."}` → `202 {"job_id"}` |
| `POST` | `/process/upload` | Upload a video file (multipart field `file`) → `202 {"job_id"}` |
| `GET`  | `/status/{job_id}` | Job status, progress, clips, error and `warnings` |
| `POST` | `/cancel/{job_id}` | Cancel a queued or running job |
| `GET`  | `/clips/{filename}` | Download a generated clip |
| `GET`  | `/health` | Health check |
| `GET`  | `/dev/analysis/jobs` | Debugger: list runs with `analysis.json` (403 unless `ENABLE_DEBUGGER=true`) |
| `GET`  | `/dev/analysis/{run_uuid}` | Debugger: full analysis for a run (`run_uuid` is on the job record) |
| `GET`  | `/dev/analysis/{run_uuid}/summary` | Debugger: meta and stats only |
| `GET`  | `/dev/video/{run_uuid}` | Debugger: original video (requires `KEEP_ORIGINAL_FOR_DEBUG=true`) |

Errors are returned as `{"error": "..."}`. Failed and cancelled runs also write an
`analysis.json` recording the stage that stopped and why.

---

## 🧪 Running Tests

```bash
cd backend
../.venv312/bin/python -m pytest          # Windows: ..\.venv312\Scripts\python.exe -m pytest
```

Tests never write to `backend/temp` or `backend/outputs`; the run fails if they do.
Legacy clip-selection behaviour is pinned by golden files in `backend/tests/legacy/`.

## 📏 Offline Evaluation

`backend/evaluation/` runs the pipeline on local files of any size, caches the
expensive stages and writes comparable run artifacts. See
[backend/evaluation/README.md](backend/evaluation/README.md).

---

## ⚙️ Configuration

All configuration is centralized in [config.py](backend/config.py) and driven by environment variables. Key settings:

- **Worker Pool**: 2 concurrent threads, 20 max queued jobs
- **Upload Limits**: 100 MB max file size, 1 MB chunk streaming
- **Supported Formats**: `.mp4`, `.mov`, `.mkv`, `.webm`
- **Timeouts**: FFmpeg 5 min, yt-dlp 10 min
- **Cleanup**: Temp files after 4 hours, output dirs after 24 hours

---

## 📄 License

This project was built for the SaaS Hackathon.
