"""
services/speech_regions.py — measured speech regions (Silero VAD).

Uses the Silero model bundled with faster-whisper; no extra dependency.

These are *measurements*: unpadded intervals where the VAD judged speech to be
present. Padding for cutting belongs to the cut-point stage, not here.

Parameters are Silero's own reference defaults (threshold 0.5, 250 ms minimum
speech, 100 ms minimum silence) with padding removed. They are provisional and
recorded with every result; tuning from real data is a later, measured step (D6).
Note these differ from faster-whisper's `vad_filter` defaults (2000 ms minimum
silence, 400 ms padding), which are designed for skipping long non-speech before
decoding, not for locating pauses.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from services.transcript import SpeechRegions

SAMPLING_RATE = 16000

SPEECH_REGION_PARAMS: dict[str, Any] = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "min_silence_duration_ms": 100,
    "speech_pad_ms": 0,
}


def detect_speech_regions(audio: np.ndarray, params: dict[str, Any] | None = None,
                          sampling_rate: int = SAMPLING_RATE) -> SpeechRegions:
    from importlib.metadata import version
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    params = dict(SPEECH_REGION_PARAMS if params is None else params)
    chunks = get_speech_timestamps(audio, VadOptions(**params), sampling_rate=sampling_rate)
    duration = round(len(audio) / sampling_rate, 3)
    regions = [
        (round(c["start"] / sampling_rate, 3), round(min(c["end"] / sampling_rate, duration), 3))
        for c in chunks
    ]
    return SpeechRegions(
        method=f"silero-vad (faster-whisper {version('faster-whisper')})",
        params=params,
        regions=[r for r in regions if r[1] > r[0]],
        audio_duration=duration,
    )


def overlap_seconds(start: float, end: float, regions: list[tuple[float, float]]) -> float:
    """Seconds of [start, end] covered by sorted, non-overlapping regions."""
    total = 0.0
    for r_start, r_end in regions:
        if r_end <= start:
            continue
        if r_start >= end:
            break
        total += min(end, r_end) - max(start, r_start)
    return total


def contains(time: float, regions: list[tuple[float, float]], tolerance: float = 0.0) -> bool:
    return any(r_start - tolerance <= time <= r_end + tolerance for r_start, r_end in regions)


def silences(regions: list[tuple[float, float]], audio_duration: float) -> list[tuple[float, float]]:
    """Measured non-speech intervals: the complement of sorted speech regions within the audio."""
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for r_start, r_end in regions:
        if r_start > cursor:
            gaps.append((round(cursor, 3), round(r_start, 3)))
        cursor = max(cursor, r_end)
    if audio_duration > cursor:
        gaps.append((round(cursor, 3), round(audio_duration, 3)))
    return gaps
