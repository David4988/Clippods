"""
services/selection/features.py — deterministic features and score for boundary_v1 candidates.

Every feature is measured, not judged (master plan §14.4). Rate, loudness and
confidence are z-scored across the video's own candidates, so Tamil and English
speakers, or quiet and loud podcasts, aren't compared on absolute numbers.

score = Σ weight × feature. Weights are PROPOSED starting values (no learned
model), recorded in every analysis so a ranking can always be recomputed by hand.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from statistics import fmean, pstdev
from typing import Optional

import numpy as np

from services.selection.lexicons import is_context_start, is_filler_start

WEIGHTS = {
    "speech_rate_z": 0.5,        # animated, fast delivery
    "loudness_z": 0.5,           # louder than this video's usual
    "loudness_var_z": 0.25,      # dynamic rather than monotone
    "asr_confidence_z": 0.25,    # transcript we can trust
    "start_is_thought": 0.5,     # opens at a thought boundary
    "end_is_thought": 0.5,       # closes at a thought boundary
    "question_count": 0.25,      # questions raised inside the clip (capped at 2)
    "ends_on_question": 0.0,     # D8: a question ending is allowed, not favoured
    "filler_start": -0.5,        # "and…", "so…", "um…"
    "lowercase_start": -0.5,     # Latin script starting lower-case: mid-sentence in practice
    "start_unpunctuated": -0.25, # previous sentence ended on a pause, not punctuation
    "end_unpunctuated": -0.25,   # last sentence ends on a pause, not punctuation
    "context_start": -0.5,       # "he…", "that…" — needs earlier context
    "untrusted_share": -2.0,     # share of the clip whose transcript is untrusted
    "duration_fit": 1.0,         # 1 inside the 20–45 s target, 0 at the 12/60 s limits
}
Z_FEATURES = ("speech_rate", "loudness", "loudness_var", "asr_confidence")


@dataclass
class Candidate:
    id: int
    start_cut: int
    end_cut: int
    start: float                   # cut_in of the start cut
    end: float                     # cut_out of the end cut
    first_word: int
    last_word: int
    first_sentence: int
    last_sentence: int
    text: str
    features: dict[str, Optional[float]] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    score: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


class IntervalIndex:
    """Seconds covered by sorted, non-overlapping intervals inside [a, b], in O(log n)."""

    def __init__(self, intervals: list[tuple[float, float]]):
        merged: list[list[float]] = []
        for s, e in sorted(intervals):
            if e <= s:
                continue
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        self.starts = [s for s, _ in merged]
        self.ends = [e for _, e in merged]
        self.cum = [0.0]
        for s, e in merged:
            self.cum.append(self.cum[-1] + (e - s))

    def _upto(self, t: float) -> float:
        i = bisect_right(self.starts, t)
        if i == 0:
            return 0.0
        return self.cum[i - 1] + min(t, self.ends[i - 1]) - self.starts[i - 1]

    def covered(self, a: float, b: float) -> float:
        return max(0.0, self._upto(b) - self._upto(a)) if b > a else 0.0


def duration_fit(duration: float, params: dict) -> float:
    lo, hi = params["target_min_s"], params["target_max_s"]
    hard_lo, hard_hi = params["hard_min_s"], params["hard_max_s"]
    if lo <= duration <= hi:
        return 1.0
    if duration < lo:
        return max(0.0, (duration - hard_lo) / (lo - hard_lo))
    return max(0.0, (hard_hi - duration) / (hard_hi - hi))


@dataclass
class FeatureContext:
    """Per-video lookups built once, shared by every candidate."""
    words: list                     # StructWord
    sentences: list                 # Sentence
    cut_kind: dict[int, str]
    speech: IntervalIndex
    untrusted: IntervalIndex
    language: str
    params: dict
    loudness: object = None         # LoudnessEnvelope or None
    loudness_mask: Optional[np.ndarray] = None


def measure(c: Candidate, ctx: FeatureContext) -> None:
    """Fill c.features with raw (un-normalised) values."""
    dur = c.duration
    speech_s = ctx.speech.covered(c.start, c.end)
    n_words = c.last_word - c.first_word + 1
    probs = [w.probability for w in ctx.words[c.first_word:c.last_word + 1] if w.probability is not None]
    inner = ctx.sentences[c.first_sentence:c.last_sentence]          # all but the last sentence
    last = ctx.sentences[c.last_sentence]

    loud = loud_var = None
    if ctx.loudness is not None:
        vals = ctx.loudness.values(c.start, c.end, ctx.loudness_mask)
        if len(vals):
            loud, loud_var = float(np.mean(vals)), float(np.std(vals))

    def boundary(kind: str) -> float:
        return {"thought": 1.0, "edge": 0.5}.get(kind, 0.0)

    first_text = ctx.words[c.first_word].text
    first_char = next((ch for ch in first_text if ch.isalpha()), "")
    prev = ctx.sentences[c.first_sentence - 1] if c.first_sentence > 0 else None
    start_edge = ctx.cut_kind[c.start_cut] == "edge"
    end_edge = ctx.cut_kind[c.end_cut] == "edge"
    c.features = {
        "duration": round(dur, 3),
        "speech_ratio": round(speech_s / dur, 3) if dur else 0.0,
        "speech_rate": n_words / speech_s if speech_s > 0 else None,
        "loudness": loud,
        "loudness_var": loud_var,
        "asr_confidence": fmean(probs) if probs else None,
        "start_is_thought": boundary(ctx.cut_kind[c.start_cut]),
        # D8: a question ends a thought, but earns no thought-boundary bonus for it.
        "end_is_thought": 0.0 if last.terminal == "?" else boundary(ctx.cut_kind[c.end_cut]),
        "question_count": float(min(2, sum(1 for s in inner if s.terminal == "?"))),
        "ends_on_question": 1.0 if last.terminal == "?" else 0.0,
        "filler_start": 1.0 if is_filler_start(first_text, ctx.language) else 0.0,
        "context_start": 1.0 if is_context_start(first_text, ctx.language) else 0.0,
        # Natural start/end (§14.4). Meaningful where transcripts are punctuated (en, ta);
        # near-constant for Hindi, so it barely moves Hindi rankings.
        "lowercase_start": 1.0 if first_char.isascii() and first_char.islower() else 0.0,
        "start_unpunctuated": 1.0 if prev is not None and not start_edge and prev.terminal is None else 0.0,
        "end_unpunctuated": 1.0 if not end_edge and last.terminal is None else 0.0,
        "untrusted_share": round(ctx.untrusted.covered(c.start, c.end) / dur, 3) if dur else 0.0,
        "duration_fit": round(duration_fit(dur, ctx.params), 3),
    }


def normalise_and_score(cands: list[Candidate], weights: dict | None = None) -> None:
    """Add <feature>_z across this video's candidates (missing → 0), then score."""
    w = weights or WEIGHTS
    for name in Z_FEATURES:
        values = [c.features[name] for c in cands if c.features.get(name) is not None]
        mean = fmean(values) if values else 0.0
        sd = pstdev(values) if len(values) > 1 else 0.0
        for c in cands:
            v = c.features.get(name)
            c.features[f"{name}_z"] = round((v - mean) / sd, 3) if v is not None and sd > 0 else 0.0
    for c in cands:
        c.contributions = {k: round(weight * float(c.features.get(k) or 0.0), 4) for k, weight in w.items()}
        c.score = round(sum(c.contributions.values()), 4)
