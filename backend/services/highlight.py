"""
ClipPods — Highlight Service
Chunking + Scoring of transcript segments.
Scoring: 0.7 * energy + 0.3 * duration_fitness

Fixed: empty chunks guard, flexible min_duration, safe min/max on energies.
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
    Merge consecutive segments into chunked candidates.
    Handles edge cases:
    - Very short audio (< min_dur): returns entire audio as one chunk
    - Large segments (> max_dur): each becomes its own chunk
    - Normal segments: merged into 30-90s candidates
    """
    if not segments:
        return []

    chunks = []
    current_segs: list[Segment] = []
    current_dur = 0.0
    chunk_counter = 0

    for seg in segments:
        seg_dur = seg.end_sec - seg.start_sec
        if seg_dur <= 0:
            continue

        # If adding this segment exceeds max and we have enough, flush
        if current_dur + seg_dur > max_dur and current_segs:
            chunk_counter += 1
            chunks.append(_make_chunk(chunk_counter, current_segs))
            current_segs = []
            current_dur = 0.0

        current_segs.append(seg)
        current_dur += seg_dur

    # Flush remaining segments — ALWAYS include them (no min_dur gate here)
    if current_segs:
        chunk_counter += 1
        chunks.append(_make_chunk(chunk_counter, current_segs))

    # If we still have 0 chunks (shouldn't happen), create one from all segments
    if not chunks and segments:
        chunks.append(_make_chunk(1, segments))

    print(f"INFO Created {len(chunks)} chunk(s) from {len(segments)} segment(s)")
    return chunks


def _make_chunk(counter: int, segs: list[Segment]) -> Chunk:
    """Helper to build a Chunk from a list of segments."""
    return Chunk(
        chunk_id=f"chunk_{counter:03d}",
        start_sec=segs[0].start_sec,
        end_sec=segs[-1].end_sec,
        text=" ".join(s.text for s in segs),
        duration_sec=segs[-1].end_sec - segs[0].start_sec,
    )


def score_chunks(chunks: list[Chunk], audio_path: str) -> list[ScoredChunk]:
    """
    Score chunks by: 0.7 * audio_energy + 0.3 * duration_fitness.
    Returns list sorted by score descending.
    
    Fixed: handles empty chunks list and single-chunk edge cases.
    """
    if not chunks:
        print("WARNING No chunks to score, returning empty list")
        return []

    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
    except Exception as e:
        print(f"WARNING Could not load audio for scoring: {e}")
        # Return chunks with default scores
        return _default_scored_chunks(chunks)

    total_samples = len(y)

    # Compute RMS energy per chunk
    energies = []
    for chunk in chunks:
        start_sample = int(chunk.start_sec * sr)
        end_sample = int(chunk.end_sec * sr)
        # Clamp to valid range
        start_sample = max(0, min(start_sample, total_samples))
        end_sample = max(start_sample, min(end_sample, total_samples))
        segment_audio = y[start_sample:end_sample]
        if len(segment_audio) > 0:
            rms = float(np.sqrt(np.mean(segment_audio ** 2)))
        else:
            rms = 0.0
        energies.append(rms)

    # Normalize energies to 0–1 (safe for single element or all-same values)
    if len(energies) == 0:
        return _default_scored_chunks(chunks)

    e_min = min(energies)
    e_max = max(energies)
    e_range = e_max - e_min if e_max > e_min else 1.0

    scored = []
    for chunk, energy in zip(chunks, energies):
        energy_score = (energy - e_min) / e_range
        # Duration fitness: peaks at 60s, drops off linearly
        duration_score = max(0.0, 1.0 - abs(chunk.duration_sec - 60.0) / 60.0)
        composite = SCORE_WEIGHT_ENERGY * energy_score + SCORE_WEIGHT_DURATION * duration_score

        scored.append(ScoredChunk(
            chunk_id=chunk.chunk_id,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            text=chunk.text,
            duration_sec=chunk.duration_sec,
            segments=chunk.segments,
            score=round(composite, 4),
            duration_score=round(duration_score, 4),
            density_score=round(density_score, 4),
            proxy_score=round(proxy_score, 4),
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    print(f"INFO Scored {len(scored)} chunk(s), top score: {scored[0].score if scored else 'N/A'}")
    return scored


def extract_highlights_smolvlm2(video_path: str) -> list[tuple[float, float]]:
    """
    Mock integration for SmolVLM2-2.2B-Instruct.
    This function processes frames + transcript to return highlight time ranges.
    
    For now, it returns empty list (meaning fallback to transcribe -> chunk -> score pipeline).
    To implement:
      1. Load HuggingFaceTB/SmolVLM2-2.2B-Instruct using transformers.
      2. Extract 1 frame per second.
      3. Prompt: 'Extract the most dramatic/action-rich/important segments...'
      4. Parse output into [(start1, end1), (start2, end2), ...]
    """
    print(f"INFO extract_highlights_smolvlm2: VLM Highlight extraction placeholder for {video_path}")
    return []

def _default_scored_chunks(chunks: list[Chunk]) -> list[ScoredChunk]:
    """Fallback: assign uniform scores when audio analysis is not possible."""
    scored = []
    for i, chunk in enumerate(chunks):
        scored.append(ScoredChunk(
            chunk_id=chunk.chunk_id,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            text=chunk.text,
            duration_sec=chunk.duration_sec,
            score=round(1.0 / (i + 1), 4),
            energy_score=0.5,
            duration_score=0.5,
        ))
    return scored


def select_highlights(scored_chunks: list[ScoredChunk], top_n: int = 5) -> list[ScoredChunk]:
    """
    Select diverse highlights using temporal bucketing.
    """
    if not scored_chunks:
        return []

    # Task 4.1: Sort descending by score
    scored_chunks.sort(key=lambda x: x.score, reverse=True)

    # Task 4.2: Temporal Diversity
    total_length = max(c.end_sec for c in scored_chunks)
    if total_length <= 0:
        return scored_chunks[:top_n]

    bucket_size = total_length / top_n
    buckets = [[] for _ in range(top_n)]

    for chunk in scored_chunks:
        b_idx = min(int(chunk.start_sec / bucket_size), top_n - 1)
        buckets[b_idx].append(chunk)

    selected = []
    # Pick highest scoring chunk from each bucket (already sorted globally)
    for b in buckets:
        if b:
            selected.append(b[0])

    # Fill empty buckets from the global pool
    if len(selected) < top_n:
        for chunk in scored_chunks:
            if chunk not in selected:
                selected.append(chunk)
            if len(selected) == top_n:
                break

    # Sort sequentially for final presentation
    selected.sort(key=lambda x: x.start_sec)
    return selected


def format_highlights_for_json(selected_chunks: list[ScoredChunk]) -> list[dict]:
    """
    Map selected chunks to the final API-ready JSON format.
    """
    output = []
    for chunk in selected_chunks:
        preview = chunk.text[:100] + ("..." if len(chunk.text) > 100 else "")
        output.append({
            "chunk_id": chunk.chunk_id,
            "start_sec": round(chunk.start_sec, 2),
            "end_sec": round(chunk.end_sec, 2),
            "duration_sec": round(chunk.duration_sec, 2),
            "transcript_preview": preview,
            "score": round(chunk.score, 2),
            "details": {
                "duration_score": round(chunk.duration_score, 2),
                "density_score": round(chunk.density_score, 2),
                "proxy_score": round(chunk.proxy_score, 2)
            }
        })
    return output


def generate_highlights(segments: list[Segment], top_n: int = 5) -> list[dict]:
    """
    Orchestrate the entire ML2 pipeline from chunking to final API mapping.
    """
    chunks = chunk_transcript(segments)
    scored = score_chunks(chunks)
    selected = select_highlights(scored, top_n)
    return format_highlights_for_json(selected)
