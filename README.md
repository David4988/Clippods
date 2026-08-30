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
  `faster-whisper`) has no wheels for 3.14 and fails to build from source. A 3.14
  environment installs *without* `faster-whisper`, and transcription then silently
  degrades to a stub transcript instead of failing.
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

```bash
# From the repository root. Pin the interpreter — see Prerequisites.
python3.12 -m venv .venv312
source .venv312/bin/activate          # Windows: .venv312\Scripts\activate

pip install -r backend/requirements.txt
```

Verify that transcription is actually available before demoing — this must print
`ok`, otherwise clips are cut from a stub transcript:

```bash
.venv312/bin/python -c "import faster_whisper; print('ok')"
```

### 3. Environment Variables

All settings have working defaults — **no `.env` file is required to run the app.**
`SARVAM_API_KEY` in `backend/.env.example` is a leftover: no code reads it, and
transcription runs locally on Faster-Whisper.

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

```bash
cd backend
../.venv312/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- UI: `http://127.0.0.1:8000/`
- API: `http://127.0.0.1:8000/health`

Bind to `127.0.0.1`, not `0.0.0.0` — the Cloudflare Tunnel connects over loopback,
and there is no authentication on these endpoints.

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

| Method   | Endpoint                 | Description                          |
| -------- | ------------------------ | ------------------------------------ |
| `POST`   | `/api/process-url`       | Submit a YouTube URL for processing  |
| `POST`   | `/api/upload`            | Upload a video file for processing   |
| `GET`    | `/api/status/{job_id}`   | Poll job status and progress         |
| `POST`   | `/api/cancel/{job_id}`   | Cancel an in-progress job            |
| `GET`    | `/api/clips/{filename}`  | Download a generated clip            |
| `GET`    | `/api/analysis/{job_id}` | Retrieve algorithm debugger data     |

---

## 🧪 Running Tests

```bash
cd backend
pytest
```

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
