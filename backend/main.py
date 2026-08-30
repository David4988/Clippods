import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Add the backend directory to sys.path so imports work on Vercel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import ENABLE_DEBUGGER, CLEANUP_INTERVAL_SECONDS, OUTPUTS_DIR
from services.job_worker import worker_pool
from utils import run_garbage_collection

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SaaS Hackathon API", version="0.1.0")

# The API uses no cookies or auth headers, so credentials are not needed.
# allow_origins=["*"] together with allow_credentials=True is an invalid
# combination per the CORS spec and browsers reject the response.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Background Garbage Collection Thread
# ---------------------------------------------------------------------------
_gc_thread = None
_gc_stop_event = threading.Event()

def _gc_worker_loop():
    logger.info("Garbage collection background daemon started.")
    # Run once immediately on startup
    try:
        run_garbage_collection()
    except Exception as exc:
        logger.error("Error during initial garbage collection: %s", exc)

    while not _gc_stop_event.wait(CLEANUP_INTERVAL_SECONDS):
        try:
            run_garbage_collection()
        except Exception as exc:
            logger.error("Error during garbage collection sweep: %s", exc)
    logger.info("Garbage collection background daemon stopped.")

# ---------------------------------------------------------------------------
# Startup / Shutdown Lifecycles
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    global _gc_thread
    # 1. Start job worker pool
    worker_pool.start()
    
    # 2. Start GC background daemon thread
    _gc_stop_event.clear()
    _gc_thread = threading.Thread(target=_gc_worker_loop, name="ClipPodsGCDaemon", daemon=True)
    _gc_thread.start()

@app.on_event("shutdown")
async def shutdown_event():
    # 1. Stop GC background daemon
    _gc_stop_event.set()
    if _gc_thread:
        _gc_thread.join(timeout=5)
    
    # 2. Stop job worker pool
    worker_pool.stop()

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
from routers.analysis import router as analysis_router  # noqa: E402
app.include_router(video_router, tags=["Video Processing"])
app.include_router(analysis_router)

# ---------------------------------------------------------------------------
# /clips/{clip_name} — serve the most recently created clip of a given name
# from any run directory under outputs/
# ---------------------------------------------------------------------------

@app.get("/clips/{clip_name}", tags=["Clips"])
async def serve_clip(clip_name: str):
    """Return the most recently written clip file matching clip_name. Sanitizes input."""
    # Sanitize clip_name input to prevent path traversal
    if ".." in clip_name or "/" in clip_name or "\\" in clip_name:
        return JSONResponse(status_code=400, content={"error": "Invalid clip name format"})
    
    # Check that it fits typical clip name format
    # format: {run_uuid}_clip_{index}.mp4
    if not (clip_name.endswith(".mp4") and "_clip_" in clip_name):
        return JSONResponse(status_code=400, content={"error": "Invalid clip name format"})

    search_dirs = [OUTPUTS_DIR]
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
# Static UI — mounted LAST
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent.parent / "static"
try:
    _STATIC_DIR.mkdir(exist_ok=True)
except OSError:
    pass

# Mount main static client UI
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
