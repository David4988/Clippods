# Project Organization & Folder Structure

## Directory Layout

```
SaaS_Hackathon/
├── .git/                    # Git repository
├── .kiro/                   # Kiro AI assistant config
│   └── steering/            # AI guidance documents
├── backend/                 # Python FastAPI backend
│   ├── .venv/              # Python virtual environment (gitignored)
│   ├── __pycache__/        # Python bytecode cache
│   ├── .pytest_cache/      # Pytest cache
│   ├── routers/            # FastAPI route handlers
│   │   ├── __init__.py
│   │   └── video.py        # POST /process, POST /process/upload, GET /status/{job_id}
│   ├── services/           # Business logic layer (pipeline tasks)
│   │   ├── __init__.py
│   │   ├── input_processing.py     # Task 1: URL download / file upload
│   │   ├── audio_extraction.py     # Task 2: Extract audio from video
│   │   ├── transcription.py        # Task 3: Speech-to-text with Whisper
│   │   ├── segment_selection.py    # Task 4: Select highlight segments
│   │   └── clip_generation.py      # Task 5: Cut video into clips
│   ├── tests/              # Pytest test suite
│   │   ├── __init__.py
│   │   ├── test_input_processing.py
│   │   ├── test_audio_extraction.py
│   │   ├── test_transcription.py
│   │   ├── test_segment_selection.py
│   │   ├── test_clip_generation.py
│   │   ├── test_progress.py
│   │   └── test_integration.py
│   ├── outputs/            # Generated clips (organized by job UUID)
│   │   └── {job_uuid}/     # Each job gets unique directory
│   │       ├── {job_uuid}_clip_0.mp4
│   │       ├── {job_uuid}_clip_1.mp4
│   │       └── {job_uuid}_clip_2.mp4
│   ├── temp/               # Temporary files (downloaded videos, extracted audio)
│   ├── main.py             # FastAPI app initialization and configuration
│   ├── job_manager.py      # In-memory job tracking (thread-safe)
│   ├── utils.py            # Shared utilities (temp paths, cleanup, instrumentation)
│   ├── requirements.txt    # Python dependencies
│   ├── pytest.ini          # Pytest configuration
│   ├── render-build.sh     # Render deployment build script
│   └── .env.example        # Environment variable template
├── static/                 # Frontend static files
│   └── index.html          # Single-page application UI
├── .gitignore              # Git ignore rules
├── .vercelignore           # Vercel deployment ignore rules
├── vercel.json             # Vercel deployment configuration
└── clippods_contracts.md   # Product requirements and API contract (LOCKED)
```

## Module Organization

### Routers Layer (`backend/routers/`)
- **Purpose:** Define API endpoints and handle HTTP request/response
- **Pattern:** One router per domain (e.g., `video.py` for video processing)
- **Responsibilities:**
  - Request validation (Pydantic models)
  - Route orchestration (call service layer)
  - Background job spawning
  - Error response formatting

### Services Layer (`backend/services/`)
- **Purpose:** Implement core business logic for each pipeline task
- **Pattern:** One service per discrete task, each file exports one main function
- **Naming Convention:** `{task_name}.py` with function matching task purpose
- **Responsibilities:**
  - Pure business logic (no HTTP concerns)
  - Input validation and error handling
  - External tool integration (ffmpeg, whisper, yt-dlp)
  - Instrumentation logging

### Tests Layer (`backend/tests/`)
- **Purpose:** Automated testing for all components
- **Pattern:** `test_{module_name}.py` mirrors source structure
- **Coverage:**
  - Unit tests for each service module
  - Integration test for full pipeline
  - Progress tracking test for job updates
- **Test Data:** Uses fixtures for sample videos/audio

## File Naming Conventions

### Python Modules
- **Snake case:** `input_processing.py`, `job_manager.py`
- **Test prefix:** `test_segment_selection.py`
- **Dunder init:** `__init__.py` for package initialization

### Generated Files
- **Temp files:** `{uuid}.{extension}` in `backend/temp/`
- **Output clips:** `{job_uuid}_clip_{index}.mp4` in `backend/outputs/{job_uuid}/`
- **Examples:**
  - `a3b2c1d4e5f6.mp4` (temp video)
  - `a3b2c1d4e5f6.wav` (temp audio)
  - `57fb44867cd24746bb30ae4b26dd2e60_clip_0.mp4` (output clip)

### Configuration Files
- **Dot prefix:** `.env`, `.gitignore`, `.vercelignore`
- **Standard names:** `requirements.txt`, `pytest.ini`, `vercel.json`

## Import Patterns

### Absolute Imports (Preferred)
```python
from services.audio_extraction import extract_audio
from services.segment_selection import select_segments
from utils import get_temp_path, cleanup_file
from job_manager import create_job, update_job, get_job
```

### Relative Imports (Router-to-Router)
```python
from routers.video import router as video_router
```

### Type Hints
```python
from typing import Optional, TypedDict
from pathlib import Path
```

## Code Organization Principles

1. **Separation of Concerns:** Routers handle HTTP, services handle logic
2. **Single Responsibility:** Each service module does one thing well
3. **Dependency Direction:** Routers → Services → Utils (never reversed)
4. **Error Handling:** Services raise HTTPException, routers catch and format
5. **Resource Cleanup:** Always use try/finally for temp file deletion
6. **Thread Safety:** Job manager uses locks for concurrent access
7. **Instrumentation:** Every service logs memory/disk usage at start and end
