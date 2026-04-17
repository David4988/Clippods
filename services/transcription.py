"""
services/transcription.py — Task 3: transcribe
Sends audio to the Sarvam AI STT API and normalises the response
into a standardised internal format.
"""
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
    """Contract-defined normalised output — only shape allowed downstream."""
    segments: list[Segment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
_REQUEST_TIMEOUT = 120  # seconds — large audio files can be slow


# ---------------------------------------------------------------------------
# Sub-task 3.2: Normalisation Logic (pure function, testable independently)
# ---------------------------------------------------------------------------

def _normalise_response(raw: dict) -> TranscriptResult:
    """
    Map Sarvam AI's JSON response to the contract-defined TranscriptResult.

    Sarvam response shape:
    {
        "transcript": "full text string",   # or "text"
        "segments": [                        # optional
            {"start": 0.0, "end": 2.5, "text": "Hello"},
            ...
        ]
    }

    Returns
    -------
    TranscriptResult
        {"segments": [{"start": float, "end": float, "text": str}, ...]}
    """
    full_text: str = raw.get("transcript") or raw.get("text") or ""

    raw_segments: list[dict] = raw.get("segments") or []
    segments: list[Segment] = []

    for seg in raw_segments:
        start    = seg.get("start")
        end      = seg.get("end")
        seg_text = seg.get("text") or ""

        # Skip malformed segments missing required timing fields
        if start is None or end is None:
            continue

        segments.append(
            Segment(
                start=float(start),
                end=float(end),
                text=seg_text.strip(),
            )
        )

    # If API returned no segments, synthesise one from the full transcript text
    # so downstream consumers always receive a non-empty segments list.
    if full_text and not segments:
        segments = [Segment(start=0.0, end=0.0, text=full_text)]

    return TranscriptResult(segments=segments)


# ---------------------------------------------------------------------------
# Sub-task 3.1: API Client
# ---------------------------------------------------------------------------

def transcribe(audio_path: str) -> TranscriptResult:
    """
    Post *audio_path* (.wav) to the Sarvam AI STT endpoint and return a
    normalised TranscriptResult.

    Parameters
    ----------
    audio_path : str
        Absolute path to a 16 kHz mono .wav file (output of extract_audio).

    Returns
    -------
    TranscriptResult
        {"segments": [{"start": float, "end": float, "text": str}, ...]}

    Raises
    ------
    HTTPException(500)
        If SARVAM_API_KEY is not configured.
    HTTPException(400)
        If the audio file does not exist or is empty.
    HTTPException(502)
        If the Sarvam AI API returns a non-2xx status.
    HTTPException(504)
        If the request to Sarvam AI times out.
    """
    # --- Guard: API key --------------------------------------------------
    api_key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="SARVAM_API_KEY is not configured.",
        )
    print("Calling Sarvam API...")
    print("Audio path:", audio_path)
    # --- Guard: audio file -----------------------------------------------
    src = Path(audio_path)
    if not src.exists() or src.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file not found or empty: {audio_path}",
        )

    # --- POST multipart/form-data to Sarvam STT --------------------------
    headers = {"api-subscription-key": api_key}

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            with src.open("rb") as audio_file:
                response = client.post(
                    SARVAM_STT_URL,
                    headers=headers,
                    files={"file": (src.name, audio_file, "audio/wav")},
                    data={"model": "saarika", "language_code": "unknown", "input_audio_codec": "pcm_s16le"},
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
    
    # --- Guard: non-2xx --------------------------------------------------
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Sarvam AI STT returned {response.status_code}: {response.text}",
        )

    raw: dict = response.json()
    return _normalise_response(raw)
