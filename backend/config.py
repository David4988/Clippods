"""
config.py — Centralized configuration settings for the ClipPods Production MVP.
Loads settings from environment variables with sensible defaults for VPS deployment.
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.resolve()
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
