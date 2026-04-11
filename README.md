# ClipPods 🎙️✂️

> **AI-powered viral clip generator for Tamil, Telugu & Hindi podcasts.**
> Automatically transcribes, scores, and extracts the best moments from long-form audio/video content.

---

## Project Structure

```
ClipPods/
├── index.html              # Landing page (URL ingest + file upload)
├── style.css               # Landing page styles (glassmorphism)
├── script.js               # Landing page JS (upload, polling, display)
│
├── app.html                # App dashboard UI
├── app.css                 # Dashboard styles
├── app.js                  # Dashboard JS (upload, polling, display)
│
├── backend/
│   ├── main.py             # ⚡ FastAPI app – API endpoints + pipeline orchestration
│   ├── config.py           # Settings (API keys, storage paths, tuning params)
│   ├── models.py           # ⚠️  Shared data contract (ALL engineers must agree)
│   │
│   ├── services/
│   │   ├── transcription.py   # 🤖 ML Engineer 1 – Sarvam AI saaras:v3 transcription
│   │   ├── highlight.py       # 🤖 ML Engineer 2 – Segment scoring & highlight selection
│   │   └── clip.py            # 🤖 ML Engineer 2 – FFmpeg clip extraction
│   │
│   └── storage/
│       ├── uploads/           # Uploaded source files (gitignored at runtime)
│       └── outputs/           # Rendered MP4 clips (gitignored at runtime)
│
└── requirements.txt        # Python dependencies
```

---

## Quick Start

### 1. Install dependencies
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### 2. Set environment variables
```bash
# Windows PowerShell
$env:SARVAM_API_KEY = "your-sarvam-api-key"
```

### 3. Run the server
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open the app
- Landing page: http://localhost:8000/
- Dashboard:    http://localhost:8000/app

---

## Pipeline Stages

| Phase | Module | Description |
|-------|--------|-------------|
| 1 | `backend/main.py` | Download video & extract audio (yt-dlp + FFmpeg) |
| 1.5 | `backend/main.py` | Split audio into 5-min overlapping chunks |
| 2 | `services/transcription.py` | Transcribe chunks via Sarvam AI saaras:v3 |
| 3 | `backend/main.py` | Build word-level segments from timestamps |
| 4 | `services/highlight.py` | Score & select top highlight segments |
| 5 | `services/clip.py` | Render MP4 clips with FFmpeg |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload a video/audio file |
| `POST` | `/api/url-ingest` | Ingest a YouTube URL |
| `GET`  | `/api/status/{job_id}` | Poll job status & clips |
| `GET`  | `/api/clips/{job_id}/{filename}` | Download a rendered clip |

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Transcription**: Sarvam AI (`saaras:v3`) – Tamil, Hindi, Telugu, Kannada, Malayalam
- **Media**: yt-dlp + FFmpeg
- **Frontend**: Vanilla HTML / CSS / JS (glassmorphism design)
