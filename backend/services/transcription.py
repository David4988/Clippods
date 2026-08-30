from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Faster-Whisper model initialisation (Lazy Loaded)
# ---------------------------------------------------------------------------
import logging
import os
import threading

logger = logging.getLogger(__name__)

# On serverless the only writable location is /tmp. On a normal machine leave the
# default (~/.cache/huggingface) alone — pinning it to /tmp means the ~150MB model
# is re-downloaded after every reboot, which is not something you want happening
# in the middle of a live demo.
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ.setdefault("HF_HOME", "/tmp/huggingface")

_model = None
_model_init_failed = False
_model_lock = threading.Lock()

def get_model():
    global _model, _model_init_failed
    if _model is not None or _model_init_failed:
        return _model
        
    with _model_lock:
        if _model is not None or _model_init_failed:
            return _model
            
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("Faster-Whisper 'base' model loaded (cpu/int8).")
        except Exception as e:
            # This is a silent quality failure: the pipeline still produces three
            # clips, but they are cut from a stub transcript rather than real
            # speech. Log it loudly so it is caught before a demo, not during one.
            logger.error(
                "Faster-Whisper is unavailable (%s). Clips will be cut from a STUB "
                "transcript and highlight selection will be meaningless. Install it "
                "with: pip install -r backend/requirements.txt (requires Python 3.12 "
                "or 3.13 — the 'av' dependency has no wheels for 3.14).",
                e,
            )
            _model_init_failed = True
            
    return _model

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Segment(TypedDict):
    start: float
    end: float
    text: str


class TranscriptResult(TypedDict):
    segments: list[Segment]


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def transcribe(audio_path: str) -> TranscriptResult:
    import time
    from utils import log_instrumentation

    start_time = time.time()
    log_instrumentation("transcription")

    try:
        src = Path(audio_path)

        if not src.exists() or src.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file not found or empty: {audio_path}",
            )

        model = get_model()

        if model is None:
            # Return stub data when faster-whisper is not available
            return TranscriptResult(
                segments=[
                    Segment(start=0.0, end=30.0, text="[Transcription unavailable - faster-whisper not installed]"),
                ]
            )

        try:
            segments_generator, _info = model.transcribe(audio_path, beam_size=5)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Audio not clear enough",
            ) from exc

        segments: list[Segment] = []

        for seg in segments_generator:
            start = seg.start
            end = seg.end
            text = seg.text or ""

            if start is None or end is None:
                continue

            segments.append(
                Segment(
                    start=float(start),
                    end=float(end),
                    text=text.strip(),
                )
            )

        return TranscriptResult(segments=segments)
    finally:
        elapsed = time.time() - start_time
        log_instrumentation("transcription", elapsed)