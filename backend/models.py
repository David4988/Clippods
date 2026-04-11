"""
ClipPods — Shared Data Models
⚠️ FROZEN after Day 2. Any change requires all-hands agreement.
Used by: ML engineers, Backend, Frontend (via API JSON serialization)
"""

from dataclasses import dataclass


@dataclass
class Segment:
    """Single Whisper transcript segment."""
    start_sec: float
    end_sec: float
    text: str


@dataclass
class Chunk:
    """Group of consecutive segments forming a 30–90 sec candidate."""
    chunk_id: str
    start_sec: float
    end_sec: float
    text: str
    duration_sec: float


@dataclass
class ScoredChunk:
    """Chunk with highlight score."""
    chunk_id: str
    start_sec: float
    end_sec: float
    text: str
    duration_sec: float
    score: float            # 0.0–1.0 composite
    energy_score: float     # 0.0–1.0 normalized RMS
    duration_score: float   # 0.0–1.0 fitness to 60s sweet spot
