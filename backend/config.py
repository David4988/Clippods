"""
ClipPods — Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Sarvam API
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

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
# Use /tmp for writable storage on Vercel
if os.getenv("VERCEL"):
    UPLOAD_DIR = "/tmp/uploads"
    OUTPUT_DIR = "/tmp/outputs"
else:
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "storage", "uploads")
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "storage", "outputs")

# Server
HOST = "0.0.0.0"
PORT = 8000
