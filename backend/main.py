import logging
from pathlib import Path

import os
import sys

# Add the backend directory to sys.path so imports work on Vercel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="SaaS Hackathon API", version="0.1.0")


# ---------------------------------------------------------------------------
# Contract-compliant error handler for Pydantic validation failures (422).
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "No input provided"},
    )


# ── Routers ──────────────────────────────────────────────────────────────────
from routers.video import router as video_router   # noqa: E402
app.include_router(video_router, tags=["Video Processing"])


# ---------------------------------------------------------------------------
# /clips/{clip_name} — serve the most recently created clip of a given name
# from any run directory under outputs/
# ---------------------------------------------------------------------------

_OUTPUTS_DIR = Path(__file__).parent / "outputs"

@app.get("/clips/{clip_name}", tags=["Clips"])
async def serve_clip(clip_name: str):
    """Return the most recently written clip file matching clip_name."""
    import tempfile
    
    search_dirs = [_OUTPUTS_DIR]
    if os.environ.get("VERCEL"):
        search_dirs.insert(0, Path(tempfile.gettempdir()) / "clippods_outputs")
        search_dirs.insert(0, Path(tempfile.gettempdir()))

    candidates = []
    for d in search_dirs:
        if d.exists():
            candidates.extend(d.glob(f"*/{clip_name}"))
            candidates.extend(d.glob(f"{clip_name}"))

    if not candidates:
        return JSONResponse(status_code=404, content={"error": f"{clip_name} not found"})
        
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return FileResponse(str(candidates[0]), media_type="video/mp4")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static UI — must be mounted LAST so it doesn't shadow API routes
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent.parent / "static"
try:
    _STATIC_DIR.mkdir(exist_ok=True)
except OSError:
    pass

app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
