"""
ClipPods — Transcription Service (ML Engineer 1)
Converts audio → timestamped Tamil transcript segments via Whisper API.
"""

import os
import math
import time
import tempfile
from openai import OpenAI
from pydub import AudioSegment

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Segment
from config import (
    WHISPER_MODEL,
    WHISPER_LANGUAGE,
    WHISPER_MAX_FILE_BYTES,
    CHUNK_DURATION_MIN,
)

client = OpenAI()

MAX_RETRIES = 3
CHUNK_DURATION_MS = CHUNK_DURATION_MIN * 60 * 1000


def transcribe(audio_path: str) -> list[Segment]:
    """
    Transcribe audio file to list of timestamped Segments.
    Handles files > 25MB by splitting into chunks.
    """
    file_size = os.path.getsize(audio_path)

    if file_size <= WHISPER_MAX_FILE_BYTES:
        raw_segments = _call_whisper_with_retry(audio_path)
        return _parse_segments(raw_segments, offset=0.0)
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            chunks = _split_audio(audio_path, temp_dir)
            all_segments = []
            for chunk_info in chunks:
                raw = _call_whisper_with_retry(chunk_info["path"])
                segs = _parse_segments(raw, offset=chunk_info["offset_sec"])
                all_segments.extend(segs)
            return all_segments


def _call_whisper_with_retry(file_path: str) -> list:
    """Call Whisper API with retry on failure."""
    for attempt in range(MAX_RETRIES):
        try:
            with open(file_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=f,
                    language=WHISPER_LANGUAGE,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            return response.segments
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Whisper API failed after {MAX_RETRIES} attempts: {e}")
            time.sleep(5 * (attempt + 1))


def _parse_segments(whisper_segments: list, offset: float) -> list[Segment]:
    """Convert Whisper output to list[Segment] with timestamp offset."""
    return [
        Segment(
            start_sec=round(seg.start + offset, 2),
            end_sec=round(seg.end + offset, 2),
            text=seg.text.strip(),
        )
        for seg in whisper_segments
        if seg.text.strip()
    ]


def _split_audio(audio_path: str, temp_dir: str) -> list[dict]:
    """Split large audio into ≤10-minute chunks for Whisper API."""
    audio = AudioSegment.from_file(audio_path)
    total_ms = len(audio)
    num_chunks = math.ceil(total_ms / CHUNK_DURATION_MS)

    chunks = []
    for i in range(num_chunks):
        start_ms = i * CHUNK_DURATION_MS
        end_ms = min((i + 1) * CHUNK_DURATION_MS, total_ms)
        chunk = audio[start_ms:end_ms]
        chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
        chunk.export(chunk_path, format="mp3", bitrate="64k")
        chunks.append({"path": chunk_path, "offset_sec": start_ms / 1000.0})
    return chunks
