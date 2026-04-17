from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException
import whisper

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
# Whisper Model (load once)
# ---------------------------------------------------------------------------

model = whisper.load_model("base")


# ---------------------------------------------------------------------------
# Main function (REPLACEMENT)
# ---------------------------------------------------------------------------

def transcribe(audio_path: str) -> TranscriptResult:
    src = Path(audio_path)

    if not src.exists() or src.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file not found or empty: {audio_path}",
        )

    try:
        result = model.transcribe(audio_path)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Audio not clear enough",
        ) from exc

    segments: list[Segment] = []

    for seg in result.get("segments", []):
        start = seg.get("start")
        end = seg.get("end")
        text = seg.get("text") or ""

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