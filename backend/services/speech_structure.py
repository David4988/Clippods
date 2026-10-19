"""
services/speech_structure.py — sentences, thought units and safe cut points for one run.

    transcript (trusted words) + VAD speech regions
        → silences at every word boundary   (cut_points.boundary_gaps)
        → sentences → thought units         (units)
        → cut points, units linked to them  (cut_points)

Phase 5: computed and recorded for every run (speech_structure.json, plus a
summary in analysis.json). Clip selection does not use it yet. Deterministic:
the same transcript always gives the same structure.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from services import cut_points as cp
from services import units
from services.speech_regions import silences as vad_silences
from services.transcript import Transcript

SCHEMA = "clippods-speech-structure/1"
VERSION = "structure_v1"


@dataclass
class SpeechStructure:
    schema: str
    version: str
    language: str
    timing_source: str                     # word | segment (no word timestamps)
    vad: bool                              # False → no cut points can exist
    audio_duration: float
    params: dict[str, Any]
    words: list[units.StructWord]
    sentences: list[units.Sentence]
    thoughts: list[units.Thought]
    cut_points: list[cp.CutPoint]
    stats: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> dict:
        """Compact record for analysis.json (the full structure is stored separately)."""
        return {k: getattr(self, k) for k in
                ("schema", "version", "language", "timing_source", "vad", "audio_duration", "params", "stats")}

    @classmethod
    def from_dict(cls, data: dict) -> "SpeechStructure":
        if data.get("schema") != SCHEMA:
            raise ValueError(f"unsupported speech structure schema {data.get('schema')!r}")
        return cls(
            **{k: data[k] for k in ("schema", "version", "language", "timing_source", "vad",
                                    "audio_duration", "params", "stats")},
            words=[units.StructWord(**w) for w in data["words"]],
            sentences=[units.Sentence(**{**s, "word_range": tuple(s["word_range"])})
                       for s in data["sentences"]],
            thoughts=[units.Thought(**{**t, "word_range": tuple(t["word_range"]),
                                       "sentence_range": tuple(t["sentence_range"])})
                      for t in data["thoughts"]],
            cut_points=[cp.CutPoint(**c) for c in data["cut_points"]],
        )


def build_speech_structure(transcript: Transcript, params: dict | None = None) -> SpeechStructure:
    params = {**units.UNIT_PARAMS, **cp.CUT_PARAMS, **(params or {})}
    language = transcript.language.language
    duration = float(transcript.audio_duration)
    speech = transcript.speech_regions
    silences = vad_silences(speech.regions, speech.audio_duration) if speech is not None else []

    words, edges, timing_source, counts = units.trusted_words(transcript)
    gaps = cp.boundary_gaps(words, silences, params)
    sentences = units.build_sentences(words, edges, [cp.gap_ms(g) for g in gaps.between], language, params)
    thoughts = units.build_thoughts(sentences, params)
    cuts = cp.build_cut_points(words, edges, gaps, sentences, thoughts, params)

    return SpeechStructure(
        schema=SCHEMA, version=VERSION, language=language, timing_source=timing_source,
        vad=speech is not None, audio_duration=duration,
        params={**params, "terminals": units.TERMINALS.get(language, units.ALL_TERMINALS)},
        words=words, sentences=sentences, thoughts=thoughts, cut_points=cuts,
        stats=_stats(words, sentences, thoughts, cuts, gaps, counts, language, duration),
    )


# ---------------------------------------------------------------------------
# statistics (what the Phase 5 report and analysis.json show)
# ---------------------------------------------------------------------------

def _pct(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    xs = sorted(values)

    def q(f: float) -> float:
        return round(xs[min(len(xs) - 1, int(f * (len(xs) - 1) + 0.5))], 2)
    return {"n": len(xs), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "max": round(xs[-1], 2)}


def _safe_boundaries(unit_list, cut_by_id) -> dict:
    """Boundaries *inside* trusted runs (run edges excluded): how many have a safe cut."""
    inner = [u for u in unit_list if u.boundary_reason not in ("untrusted", "edge")]
    safe = sum(1 for u in inner if u.end_cut is not None and cut_by_id[u.end_cut].cut_out is not None)
    return {"inner_boundaries": len(inner), "with_safe_cut": safe,
            "safe_share": round(safe / len(inner), 3) if inner else None}


def _stats(words, sentences, thoughts, cuts, gaps, counts, language, duration) -> dict:
    cut_by_id = {c.id: c for c in cuts}
    minutes = duration / 60 if duration else 0
    terminals = sum(1 for w in words if units.terminal_of(w.text, language))
    # A unit whose start and end resolve to the same silence sits inside that
    # silence by its word timings (mis-timed words); it can never become a clip.
    degenerate = [t for t in thoughts if t.start_cut is not None and t.start_cut == t.end_cut]
    usable_thoughts = [t for t in thoughts if t.start_cut is not None and t.end_cut is not None
                       and t.start_cut != t.end_cut
                       and cut_by_id[t.start_cut].cut_in is not None
                       and cut_by_id[t.end_cut].cut_out is not None
                       and cut_by_id[t.start_cut].cut_in < cut_by_id[t.end_cut].cut_out]
    return {
        **counts,
        "trusted_words": len(words),
        "terminals_per_100_words": round(100 * terminals / len(words), 2) if words else None,
        "sentences": {
            "count": len(sentences),
            "by_reason": dict(sorted(Counter(s.boundary_reason for s in sentences).items())),
            "duration_s": _pct([s.end - s.start for s in sentences]),
            "words": _pct([s.word_range[1] - s.word_range[0] + 1 for s in sentences]),
            "boundaries": _safe_boundaries(sentences, cut_by_id),
        },
        "thoughts": {
            "count": len(thoughts),
            "by_reason": dict(sorted(Counter(t.boundary_reason for t in thoughts).items())),
            "duration_s": _pct([t.end - t.start for t in thoughts]),
            "boundaries": _safe_boundaries(thoughts, cut_by_id),
            "with_safe_start_and_end": len(usable_thoughts),
            "start_and_end_in_same_silence": len(degenerate),
        },
        "cut_points": {
            "count": len(cuts),
            "per_minute": round(len(cuts) / minutes, 2) if minutes else None,
            "by_kind": dict(sorted(Counter(c.kind for c in cuts).items())),
            "gap_ms": _pct([c.gap_ms for c in cuts]),
        },
        "word_boundary_silence_ms": _pct([cp.gap_ms(g) for g in gaps.between if g is not None]),
        # Words whose timing midpoint falls inside a silence used for cutting: word
        # timings and VAD disagree there (mis-timed words, or speech too quiet for VAD).
        "words_inside_cut_silences": _words_inside(words, cuts),
    }


def _words_inside(words, cuts) -> int:
    spans = sorted((c.gap_start, c.gap_end) for c in cuts)
    starts = [s for s, _ in spans]
    count = 0
    for w in words:
        mid = (w.start + w.end) / 2
        i = bisect_right(starts, mid) - 1
        if i >= 0 and spans[i][0] < mid < spans[i][1]:
            count += 1
    return count
