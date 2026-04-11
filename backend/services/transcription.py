"""
transcription.py – ML Engineer 1
Responsibilities: chunk audio → Sarvam AI saaras:v3 → TranscriptChunk
"""

import asyncio
import os
from models import TranscriptChunk, TranscriptWord
from config import SARVAM_API_KEY, DEFAULT_LANGUAGE

# Production initialisation (uncomment when API key is available):
# from sarvamai import SarvamAIClient
# _client = SarvamAIClient(api_key=SARVAM_API_KEY)


async def transcribe_chunk(chunk_path: str, language: str = DEFAULT_LANGUAGE) -> TranscriptChunk:
    """
    ML Engineer 1 – Transcription Node
    ────────────────────────────────────
    Sends a single audio chunk to Sarvam AI and returns a TranscriptChunk
    with per-word timestamps.

    Args:
        chunk_path: Absolute or relative path to a .wav / .mp3 chunk file.
        language:   BCP-47 language code (e.g. "hi-IN", "ta-IN", "te-IN").

    Returns:
        TranscriptChunk with chunk_index, words[], and merged_text.
    """
    print(f"[ML-ENG-1] Transcribing {os.path.basename(chunk_path)} | lang={language}")
    await asyncio.sleep(2)  # ← replace with real API call below

    # ── Production implementation ────────────────────────────────────────────
    # response = await _client.speech_to_text.transcribe_async(
    #     file=chunk_path,
    #     model="saaras:v3",
    #     language_code=language,
    #     with_timestamps=True,
    # )
    # words = [
    #     TranscriptWord(
    #         word=w.word,
    #         start_time=w.start_time,
    #         end_time=w.end_time,
    #     )
    #     for w in response.words
    # ]
    # return TranscriptChunk(
    #     chunk_index=0,
    #     words=words,
    #     merged_text=response.transcript,
    # )
    # ────────────────────────────────────────────────────────────────────────

    # Mock response for local development / testing
    mock_words = [
        TranscriptWord(word="Hello",     start_time=0.0, end_time=0.5),
        TranscriptWord(word="Podcast",   start_time=0.5, end_time=1.0),
        TranscriptWord(word="community", start_time=1.0, end_time=1.5),
        TranscriptWord(word="building",  start_time=1.5, end_time=1.9),
        TranscriptWord(word="great",     start_time=1.9, end_time=2.2),
        TranscriptWord(word="apps",      start_time=2.2, end_time=2.7),
    ]

    return TranscriptChunk(
        chunk_index=0,
        words=mock_words,
        merged_text=" ".join(w.word for w in mock_words),
    )
