from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Faster-Whisper model initialisation
# ---------------------------------------------------------------------------
try:
    from faster_whisper import WhisperModel
    import os
    
    # Try to set cache dir to /tmp if on serverless
    os.environ["HF_HOME"] = "/tmp/huggingface"
    
    model = WhisperModel("base", device="cpu", compute_type="int8")
except Exception as e:
    import logging
    logging.warning(f"WhisperModel initialization failed: {e}. Falling back to dummy transcription.")
    model = None

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
    src = Path(audio_path)

    if not src.exists() or src.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file not found or empty: {audio_path}",
        )

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