"""
ClipPods — Highlight Service (ML Engineer 2)
Chunking + Scoring of transcript segments.
Scoring: 0.7 * energy + 0.3 * duration_fitness
"""

import os
import numpy as np
import librosa

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Segment, Chunk, ScoredChunk
from config import (
    DEFAULT_MIN_DURATION,
    DEFAULT_MAX_DURATION,
    SCORE_WEIGHT_ENERGY,
    SCORE_WEIGHT_DURATION,
)


def chunk_transcript(
    segments: list[Segment],
    min_dur: float = DEFAULT_MIN_DURATION,
    max_dur: float = DEFAULT_MAX_DURATION,
) -> list[Chunk]:
    """
    Merge consecutive Whisper segments into 30–90 sec chunks.
    Never cuts mid-segment.
    """
    chunks = []
    current_segs = []
    current_dur = 0.0
    chunk_counter = 0

    for seg in segments:
        seg_dur = seg.end_sec - seg.start_sec
        if current_dur + seg_dur > max_dur and current_dur >= min_dur:
            chunk_counter += 1
            chunks.append(Chunk(
                chunk_id=f"chunk_{chunk_counter:03d}",
                start_sec=current_segs[0].start_sec,
                end_sec=current_segs[-1].end_sec,
                text=" ".join(s.text for s in current_segs),
                duration_sec=current_segs[-1].end_sec - current_segs[0].start_sec,
            ))
            current_segs = []
            current_dur = 0.0
        current_segs.append(seg)
        current_dur += seg_dur

    # Last chunk (only if meets min duration)
    if current_segs and current_dur >= min_dur:
        chunk_counter += 1
        chunks.append(Chunk(
            chunk_id=f"chunk_{chunk_counter:03d}",
            start_sec=current_segs[0].start_sec,
            end_sec=current_segs[-1].end_sec,
            text=" ".join(s.text for s in current_segs),
            duration_sec=current_segs[-1].end_sec - current_segs[0].start_sec,
        ))

    return chunks


def score_chunks(chunks: list[Chunk], audio_path: str) -> list[ScoredChunk]:
    """
    Score chunks by: 0.7 * audio_energy + 0.3 * duration_fitness.
    Returns list sorted by score descending.
    """
    y, sr = librosa.load(audio_path, sr=16000, mono=True)

    # Compute RMS energy per chunk
    energies = []
    for chunk in chunks:
        start_sample = int(chunk.start_sec * sr)
        end_sample = int(chunk.end_sec * sr)
        segment_audio = y[start_sample:end_sample]
        rms = float(np.sqrt(np.mean(segment_audio ** 2))) if len(segment_audio) > 0 else 0.0
        energies.append(rms)

    # Normalize energies to 0–1
    e_min, e_max = min(energies), max(energies)
    e_range = e_max - e_min if e_max > e_min else 1.0

    scored = []
    for chunk, energy in zip(chunks, energies):
        energy_score = (energy - e_min) / e_range
        duration_score = max(0.0, 1.0 - abs(chunk.duration_sec - 60.0) / 30.0)
        composite = SCORE_WEIGHT_ENERGY * energy_score + SCORE_WEIGHT_DURATION * duration_score

        scored.append(ScoredChunk(
            chunk_id=chunk.chunk_id,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            text=chunk.text,
            duration_sec=chunk.duration_sec,
            score=round(composite, 4),
            energy_score=round(energy_score, 4),
            duration_score=round(duration_score, 4),
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
