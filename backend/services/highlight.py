"""
highlight.py – ML Engineer 2 (Chunking + Scoring)
Responsibilities: score Segments → select top highlights
"""

import re
from models import Segment
from config import MAX_CLIP_COUNT


# ── Keyword bank (expand per domain / language) ──────────────────────────────
_HIGH_VALUE_KEYWORDS = {
    # English high-signal words
    "important", "key", "crucial", "secret", "never", "always",
    "learn", "tip", "mistake", "truth", "reveal", "hack",
    "amazing", "powerful", "strategy", "warning", "advice",
    "shocking", "lesson", "proven", "biggest", "worst",
    # Tamil transliterated
    "enna", "oru", "eppadi", "mukiyam", "ragasiyam", "theriyuma",
    "katradhu", "thavaru", "unmai", "vazhikatti",
    # Hindi transliterated
    "kya", "kyun", "bahut", "zaroori", "galti", "sach",
    "seekho", "raaz", "sabse", "dhyan",
    # Telugu transliterated
    "emiti", "chaala", "mukhyam", "rahasyam", "nijam", "nerchukondi",
}


def _clean_words(text: str):
    """Extract clean words (handles punctuation properly)."""
    return re.findall(r"\b\w+\b", text.lower())


def _keyword_density(text: str) -> float:
    """Returns fraction of words that are high-value keywords (0.0 – 1.0)."""
    words = _clean_words(text)
    if not words:
        return 0.0

    hits = sum(1 for w in words if w in _HIGH_VALUE_KEYWORDS)
    return hits / len(words)


def score_segments(segments: list[Segment]) -> list[Segment]:
    """
    ML Engineer 2 – Highlight Scoring
    Scores each Segment using weighted heuristics:
      - Length score   (0 – 0.30)
      - Keyword score  (0 – 0.40)
      - Pacing score   (0 – 0.30)
      - Emotion boost  (+0.05 optional)

    Returns:
        Segments sorted by score (descending)
    """
    for seg in segments:
        words = _clean_words(seg.text)
        word_count = len(words)
        duration = max(seg.end_time - seg.start_time, 0.001)

        # ── Length score (ideal: 10–50 words, peak at 25) ──
        if 10 <= word_count <= 50:
            length_score = 0.30 * (1.0 - abs(word_count - 25) / 25)
        else:
            length_score = 0.05

        # ── Keyword score ──
        kw_density = _keyword_density(seg.text)
        kw_score = min(kw_density * 4.0, 1.0) * 0.40

        # ── Pacing score (sentences per 10 seconds) ──
        sps = seg.sentence_count / duration * 10
        pacing_score = 0.30 if 0.5 <= sps <= 4.0 else 0.05

        # ── Emotion boost ──
        emotion_bonus = 0.05 if "!" in seg.text else 0.0

        # ── Final score ──
        seg.score = round(length_score + kw_score + pacing_score + emotion_bonus, 3)

    return sorted(segments, key=lambda s: s.score, reverse=True)


def select_highlights(
    scored: list[Segment],
    max_count: int = MAX_CLIP_COUNT,
    min_score: float = 0.4,
) -> list[Segment]:
    """
    Select top-N highlights with minimum quality threshold.

    Args:
        scored:    Output of score_segments()
        max_count: Maximum clips
        min_score: Minimum score threshold

    Returns:
        Filtered top segments
    """
    # Filter low-quality segments
    filtered = [s for s in scored if s.score >= min_score]

    # Return top-N
    return filtered[:max_count]