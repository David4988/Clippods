from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

import httpx
from fastapi import HTTPException

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
# Constants
# ---------------------------------------------------------------------------

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
_REQUEST_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Utility: Trim audio to 30 seconds (MVP fix)
# ---------------------------------------------------------------------------

def _trim_audio(input_path: str) -> str:
    output_path = input_path.replace(".wav", "_short.wav")

    os.system(f'ffmpeg -i "{input_path}" -t 30 "{output_path}" -y')

    return output_path


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise_response(raw: dict) -> TranscriptResult:
    full_text: str = raw.get("transcript") or raw.get("text") or ""

    raw_segments: list[dict] = raw.get("segments") or []
    segments: list[Segment] = []

    for seg in raw_segments:
        start = seg.get("start")
        end = seg.get("end")
        seg_text = seg.get("text") or ""

        if start is None or end is None:
            continue

        segments.append(
            Segment(
                start=float(start),
                end=float(end),
                text=seg_text.strip(),
            )
        )

    if full_text and not segments:
        segments = [Segment(start=0.0, end=0.0, text=full_text)]

    return TranscriptResult(segments=segments)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def transcribe(audio_path: str) -> TranscriptResult:
    api_key = os.environ.get("SARVAM_API_KEY", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="SARVAM_API_KEY is not configured.",
        )

    src = Path(audio_path)

    if not src.exists() or src.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file not found or empty: {audio_path}",
        )

    print("Calling Sarvam API...")
    print("Original audio path:", audio_path)

    # 🔥 MVP FIX: Trim to 30 sec
    trimmed_audio = _trim_audio(audio_path)
    print("Trimmed audio path:", trimmed_audio)

    headers = {"api-subscription-key": api_key}

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            with open(trimmed_audio, "rb") as audio_file:
                response = client.post(
                    SARVAM_STT_URL,
                    headers=headers,
                    files={"file": (Path(trimmed_audio).name, audio_file, "audio/wav")},
                    data={
                        "model": "saarika:v2.5",
                        "language_code": "unknown",
                        "input_audio_codec": "pcm_s16le",
                    },
                )

                print("Response status:", response.status_code)
                print("Response text:", response.text)

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Sarvam AI STT request timed out.",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Network error reaching Sarvam AI: {exc}",
        ) from exc

    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Sarvam AI STT returned {response.status_code}: {response.text}",
        )

    raw: dict = response.json()

    return _normalise_response(raw)