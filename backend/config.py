"""
ClipPods — Configuration
"""

import os

# OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Whisper settings
WHISPER_MODEL = "whisper-1"
WHISPER_LANGUAGE = "ta"

# Audio processing
MAX_UPLOAD_SIZE_MB = 500
CHUNK_DURATION_MIN = 10          # minutes per split chunk for Whisper
WHISPER_MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

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
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "storage", "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "storage", "outputs")

# Server
HOST = "0.0.0.0"
PORT = 8000
