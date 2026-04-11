"""
models.py – Shared data contract
⚠️  ALL engineers (frontend, backend, ML) must agree on these schemas.
     Do NOT rename fields without coordinating across the team.
"""

from pydantic import BaseModel
from typing import List, Optional


# ── Phase 2: Transcription ────────────────────────────────────────────────────

class TranscriptWord(BaseModel):
    """Single timestamped word from Sarvam AI saaras:v3 response."""
    word: str
    start_time: float   # seconds from audio start
    end_time: float     # seconds from audio start


class TranscriptChunk(BaseModel):
    """Output of transcription.transcribe_chunk() for one audio chunk."""
    chunk_index: int
    words: List[TranscriptWord]
    merged_text: str    # full text of this chunk, words joined


# ── Phase 3-4: Segmentation & Highlight Scoring ──────────────────────────────

class Segment(BaseModel):
    """A contiguous text window ready for highlight scoring."""
    id: str
    text: str
    start_time: float
    end_time: float
    score: float = 0.0          # set by highlight.score_segments()
    sentence_count: int = 1


# ── Phase 5: Clip Output ─────────────────────────────────────────────────────

class Clip(BaseModel):
    """A rendered video clip written to backend/storage/outputs/."""
    id: str
    segment_id: str
    start_time: float
    end_time: float
    file_path: str      # absolute or relative path to .mp4
    duration: float     # end_time - start_time


# ── Job tracking ─────────────────────────────────────────────────────────────

class Job(BaseModel):
    """Top-level job record returned by /api/status/{job_id}."""
    id: str
    status: str                         # queued | chunking | transcribing | segmenting | highlighting | rendering | completed | failed
    source_url: Optional[str] = None
    created_at: str
    error: Optional[str] = None
    segments: List[Segment] = []
    clips: List[Clip] = []
