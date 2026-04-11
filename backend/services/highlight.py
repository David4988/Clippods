"""
highlight.py – ML Engineer 2 (Chunking + Scoring)
Responsibilities: score Segments → select top highlights
"""

from backend.models import Segment
from backend.config import MAX_CLIP_COUNT


# ── Keyword bank (expand per domain / language) ──────────────────────────────
_HIGH_VALUE_KEYWORDS = {
    "important", "key", "crucial", "secret", "never", "always",
    "learn", "tip", "mistake", "truth", "reveal", "hack",
    # Tamil / Hindi transliterated common hook words:
    "enna", "oru", "eppadi", "kya", "kyun", "bahut",
}


def _keyword_density(text: str) -> float:
    """Returns fraction of words that are high-value keywords (0.0 – 1.0)."""
    words = text.lower().split()
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in _HIGH_VALUE_KEYWORDS)
    return hits / len(words)


def score_segments(segments: list[Segment]) -> list[Segment]:
    """
    ML Engineer 2 – Highlight Scoring
    ────────────────────────────────────
    Scores each Segment using a weighted heuristic model:
      - Length score:   ideal clip is 10-50 words                 (0 – 0.30)
      - Keyword score:  presence of high-value / hook words        (0 – 0.40)
      - Density score:  sentences-per-second pacing                (0 – 0.30)

    Args:
        segments: List of Segment objects with raw text & timestamps.

    Returns:
        Same list, sorted highest-score first, with .score populated.
    """
    for seg in segments:
        word_count = len(seg.text.split())
        duration = max(seg.end_time - seg.start_time, 0.001)

        # Length score – peak at 25 words, falls off outside 10-50 range
        if 10 <= word_count <= 50:
            length_score = 0.30 * (1.0 - abs(word_count - 25) / 25)
        else:
            length_score = 0.05

        # Keyword score
        kw_score = min(_keyword_density(seg.text) * 4.0, 1.0) * 0.40

        # Pacing score – ~1-3 sentences per 10 sec is ideal
        sps = seg.sentence_count / duration * 10
        pacing_score = 0.30 if 0.5 <= sps <= 4.0 else 0.05

        seg.score = round(length_score + kw_score + pacing_score, 3)

    return sorted(segments, key=lambda s: s.score, reverse=True)


def select_highlights(scored: list[Segment], max_count: int = MAX_CLIP_COUNT) -> list[Segment]:
    """
    Return the top-N highest scoring segments.

    Args:
        scored:    Output of score_segments() – already sorted.
        max_count: Maximum number of highlights to return.

    Returns:
        Top-N Segment objects.
    """
    return scored[:max_count]
