import os
import sys

# ── Sarvam AI ────────────────────────────────────────────────────────────────
SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
if not SARVAM_API_KEY:
    # ⚠️  For production: swap the print below for sys.exit(1)
    print("⚠️  WARNING: SARVAM_API_KEY not set – live transcription will fail at runtime.")
    SARVAM_API_KEY = "mock-sarvam-key"

# ── Storage paths (relative to project root) ─────────────────────────────────
STORAGE_ROOT: str = "./backend/storage"

# ── Pipeline tuning ──────────────────────────────────────────────────────────
MAX_CLIP_COUNT: int = 10
CHUNK_DURATION_SECONDS: int = 300   # 5-minute audio chunks
CHUNK_OVERLAP_SECONDS: int = 10     # 10-second overlap between chunks

# ── Supported transcription languages ────────────────────────────────────────
SUPPORTED_LANGUAGES: list[str] = ["hi-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"]
DEFAULT_LANGUAGE: str = "hi-IN"
