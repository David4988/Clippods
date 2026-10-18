"""
config.py — Centralized configuration settings for the ClipPods Production MVP.
Loads settings from environment variables with sensible defaults for VPS deployment.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).parent.resolve()

# Load backend/.env BEFORE any setting below is read. Every module that needs a
# setting imports this file first, so loading here (rather than in main.py after
# its imports) is what makes .env values actually take effect. Real environment
# variables win over .env. CLIPPODS_ENV_FILE points at a different file;
# CLIPPODS_DISABLE_DOTENV=1 skips loading (used by the test suite for hermeticity).
if os.environ.get("CLIPPODS_DISABLE_DOTENV") != "1":
    load_dotenv(os.environ.get("CLIPPODS_ENV_FILE") or BASE_DIR / ".env", override=False)

TEMP_DIR = BASE_DIR / "temp"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Make sure base directories exist
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Debugger & Dev features
# Set to 'true' in development, 'false' in production
ENABLE_DEBUGGER = os.environ.get("ENABLE_DEBUGGER", "false").lower() == "true"

# Whether to keep the original video for debugger playback
# Force false in production unless ENABLE_DEBUGGER is active
KEEP_ORIGINAL_FOR_DEBUG = os.environ.get("KEEP_ORIGINAL_FOR_DEBUG", "false").lower() == "true" and ENABLE_DEBUGGER

# 2. Upload Validation Settings
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "100"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = int(os.environ.get("UPLOAD_CHUNK_SIZE_BYTES", str(1024 * 1024))) # default 1MB chunks

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",      # .mov
    "video/x-matroska",     # .mkv
    "video/x-msvideo",      # some browsers report .mkv/.mov as this
    "video/webm",
}

# Content-Types that carry no information about the file. Browsers send these for
# .mkv/.mov/.webm on many OS/browser combinations, so they must not be treated as
# a rejection signal — the extension whitelist above is the real gate.
GENERIC_UPLOAD_MIME_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-octet-stream",
}

# 3. Bounded Worker Queue Settings
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
MAX_QUEUED_JOBS = int(os.environ.get("MAX_QUEUED_JOBS", "20"))

# 4. Subprocess Execution Timeouts (seconds)
FFMPEG_TIMEOUT_SECONDS = int(os.environ.get("FFMPEG_TIMEOUT_SECONDS", "300"))      # 5 minutes
YT_DLP_TIMEOUT_SECONDS = int(os.environ.get("YT_DLP_TIMEOUT_SECONDS", "600"))      # 10 minutes

# 5. Garbage Collection Cleanup Settings (hours)
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "3600")) # every 1 hour
TEMP_FILE_MAX_AGE_HOURS = float(os.environ.get("TEMP_FILE_MAX_AGE_HOURS", "4.0"))   # clean temp files older than 4h
OUTPUT_DIR_MAX_AGE_HOURS = float(os.environ.get("OUTPUT_DIR_MAX_AGE_HOURS", "24.0"))# clean output dirs older than 24h

# When the debugger is enabled, run folders that contain analysis.json are debug
# evidence and follow this retention instead of OUTPUT_DIR_MAX_AGE_HOURS.
# 0 = never delete automatically. (Offline evaluation data lives outside
# backend/ entirely and is never swept.)
DEBUG_RUN_MAX_AGE_HOURS = float(os.environ.get("DEBUG_RUN_MAX_AGE_HOURS", "0"))

# Finished job records (completed/error/cancelled) are evicted from memory after
# this long. Matches the default output retention so /status stays useful while
# the clips still exist.
JOB_RECORD_TTL_HOURS = float(os.environ.get("JOB_RECORD_TTL_HOURS", "24.0"))

# 6. ASR
# "legacy" decodes exactly as the original pipeline (legacy_v2 output unchanged)
# while recording language/confidence metadata, speech regions and quality flags.
# "rich_v1" adds word timestamps + VAD filtering, which can change segments.
# "adaptive_v1" selects a per-language profile, gates quality and retries only
# suspicious regions once (services/asr_pipeline.py). Opt-in; not the default.
ASR_PROFILE = os.environ.get("ASR_PROFILE", "legacy")
# Where Faster-Whisper models are cached (a Hugging Face hub cache folder).
# Unset = the default ~/.cache/huggingface/hub.
ASR_MODEL_DIR = os.environ.get("ASR_MODEL_DIR") or None
if ASR_PROFILE not in ("legacy", "rich_v1", "adaptive_v1"):
    raise ValueError(f"ASR_PROFILE must be 'legacy', 'rich_v1' or 'adaptive_v1', got {ASR_PROFILE!r}")

# 7. Input limits
MAX_VIDEO_DURATION_SECONDS = float(os.environ.get("MAX_VIDEO_DURATION_SECONDS", str(120 * 60)))
