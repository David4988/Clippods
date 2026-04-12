"""
ClipPods — Configuration
"""

import os
from dotenv import load_dotenv

# Load .env from project root (parent of backend/) regardless of cwd
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

# Sarvam API
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# FFmpeg setup (Windows fail-safe)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# Audio processing
MAX_UPLOAD_SIZE_MB = 500
CHUNK_DURATION_MIN = 55          # minutes per split chunk for Sarvam

# Clip settings
DEFAULT_MAX_CLIPS = 5
DEFAULT_MIN_DURATION = 30        # seconds
DEFAULT_MAX_DURATION = 90        # seconds
CLIP_FADE_MS = 500               # 0.5s fade in/out
CLIP_BITRATE = "128k"

# Scoring weights
SCORE_WEIGHT_ENERGY = 0.7
SCORE_WEIGHT_DURATION = 0.3

# Storage paths
if os.getenv("VERCEL"):
    # Use /tmp for writable storage on Vercel
    UPLOAD_DIR = "/tmp/uploads"
    OUTPUT_DIR = "/tmp/outputs"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_DIR = os.path.join(BASE_DIR, "storage", "uploads")
    OUTPUT_DIR = os.path.join(BASE_DIR, "storage", "outputs")

# Server
HOST = "0.0.0.0"
PORT = 8000
