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
    chunk_counter = 0

    for seg in segments:
        if seg.end_sec - seg.start_sec > max_dur:
            seg.end_sec = seg.start_sec + max_dur

        if current_segs:
            prev_seg = current_segs[-1]
            gap = seg.start_sec - prev_seg.end_sec
            proposed_dur = seg.end_sec - current_segs[0].start_sec
            
            if proposed_dur > max_dur or gap > 5.0:
                actual_dur = current_segs[-1].end_sec - current_segs[0].start_sec
                if actual_dur >= min_dur:
                    chunk_counter += 1
                    chunks.append(Chunk(
                        chunk_id=f"chunk_{chunk_counter:03d}",
                        start_sec=current_segs[0].start_sec,
                        end_sec=current_segs[-1].end_sec,
                        text=" ".join(s.text for s in current_segs),
                        duration_sec=actual_dur,
                        segments=list(current_segs)
                    ))
                current_segs = []

        current_segs.append(seg)

    # Last chunk 
    if current_segs:
        actual_dur = current_segs[-1].end_sec - current_segs[0].start_sec
        if actual_dur >= min_dur:
            chunk_counter += 1
            chunks.append(Chunk(
                chunk_id=f"chunk_{chunk_counter:03d}",
                start_sec=current_segs[0].start_sec,
                end_sec=current_segs[-1].end_sec,
                text=" ".join(s.text for s in current_segs),
                duration_sec=actual_dur,
                segments=list(current_segs)
            ))

    return chunks


def score_chunks(chunks: list[Chunk], audio_path: str = None) -> list[ScoredChunk]:
    """
    Score chunks using deterministic MVP logic:
    0.4 * duration + 0.4 * density + 0.2 * text_proxy.
    audio_path is ignored but kept for signature compatibility.
    """
    # Pre-calculate metrics for normalization
    densities = [min(len(c.text) / c.duration_sec if c.duration_sec > 0 else 0.0, 20.0) for c in chunks]
    max_density = max(densities) if densities and max(densities) > 0 else 1.0

    proxy_keywords = ["!", "?", "முக்கியமான", "உண்மை", "கவனிக்க", "அதிசயம்"]
    proxies = []
    for c in chunks:
        count = sum(c.text.count(kw) for kw in proxy_keywords)
        proxies.append(float(count))
    max_proxy = max(proxies) if proxies and max(proxies) > 0 else 1.0

    scored = []
    for chunk, density, proxy in zip(chunks, densities, proxies):
        # 3.1: Duration Fitness
        duration_score = max(0.0, 1.0 - abs(chunk.duration_sec - 60.0) / 30.0)
        
        # 3.2: Speech Density
        density_score = density / max_density
        
        # 3.3: Text-Based Energy Proxy
        proxy_score = proxy / max_proxy
        
        # 3.4: Final Score Calculation
        composite = (duration_score * 0.4) + (density_score * 0.4) + (proxy_score * 0.2)

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
