"""
services/units.py — sentences and thought units built from trusted transcript words.

Words are the semantic index; time comes from VAD. A boundary between two words
is a *pause* only when a measured VAD silence lies there (the silence length is
passed in by the caller from cut_points.boundary_gaps), never from word timings
alone, because word timestamps are approximate.

Trusted words: words of segments the quality gate does not distrust
(transcript_quality.segment_suspicion). An untrusted segment is a hard break —
no sentence or thought ever spans it.

Sentence boundary after a word when:
  * it ends with terminal punctuation for the decode language, or
  * the VAD silence after it is >= sentence_pause_ms (Hindi transcripts are
    almost unpunctuated, so this rule carries Hindi), or
  * untrusted text / the end of the audio follows.
Thought units merge consecutive sentences unless the silence between them is
>= thought_break_ms, the previous sentence is a question (question→answer turn),
or an untrusted span intervenes; thoughts longer than thought_max_s are split at
their largest internal silence. No discourse-marker lists in V1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from services.transcript import Transcript
from services.transcript_quality import segment_suspicion

TERMINALS = {"en": ".?!…", "hi": "।॥?!.", "ta": ".?!…"}
ALL_TERMINALS = "".join(sorted(set("".join(TERMINALS.values()))))
# Closing quotes/brackets that may follow a terminal: "Really?" → terminal '?'.
_TRAILING = "\"'”’)]»"

UNIT_PARAMS = {
    "sentence_pause_ms": 700,     # master plan §14.1 proposal; measured in Phase 5
    "thought_break_ms": 1200,     # PROPOSED; measured in Phase 5
    "thought_max_s": 90.0,        # D7 proposal (hard max)
}


@dataclass
class StructWord:
    index: int
    start: float
    end: float
    text: str
    segment_id: int
    run: int                       # trusted run: consecutive words with no untrusted text between
    probability: Optional[float] = None   # decoder word probability (None for segment pieces)


@dataclass
class Sentence:
    id: int
    word_range: tuple[int, int]    # inclusive indices into SpeechStructure.words
    start: float
    end: float
    text: str
    terminal: Optional[str]
    boundary_reason: str           # punct | pause | untrusted | edge
    gap_after_ms: int              # measured VAD silence after the sentence (0 = none)
    start_cut: Optional[int] = None
    end_cut: Optional[int] = None


@dataclass
class Thought:
    id: int
    sentence_range: tuple[int, int]
    word_range: tuple[int, int]
    start: float
    end: float
    text: str
    boundary_reason: str           # pause | question | untrusted | edge | max_length
    gap_after_ms: int
    start_cut: Optional[int] = None
    end_cut: Optional[int] = None


@dataclass
class RunEdges:
    """Runs bordered by untrusted text (otherwise a run edge is the start/end of the audio)."""
    untrusted_before: set[int] = field(default_factory=set)
    untrusted_after: set[int] = field(default_factory=set)


def trusted_words(transcript: Transcript) -> tuple[list[StructWord], RunEdges, str, dict]:
    """
    Flatten trusted words in order, numbering runs. Returns (words, edges,
    timing_source, counts). Without word timestamps each trusted segment
    becomes one piece and timing_source is "segment".
    """
    words: list[StructWord] = []
    edges = RunEdges()
    run = 0
    pending_break = False          # untrusted text seen since the last trusted word
    has_words = any(s.words for s in transcript.segments)
    counts = {"segments": len(transcript.segments), "excluded_segments": 0,
              "excluded_words": 0, "excluded_seconds": 0.0}

    for seg in transcript.segments:
        if not seg.text:
            continue
        if segment_suspicion(seg):
            counts["excluded_segments"] += 1
            counts["excluded_words"] += len(seg.words) if seg.words else len(seg.text.split())
            counts["excluded_seconds"] += max(0.0, seg.end - seg.start)
            pending_break = True
            continue
        if has_words:
            pieces = [(w.start, w.end, w.text, w.probability) for w in (seg.words or [])]
        else:
            pieces = [(seg.start, seg.end, seg.text, None)]
        for start, end, text, probability in pieces:
            if not text.strip():
                continue
            if pending_break:
                if words:
                    edges.untrusted_after.add(run)
                    run += 1
                edges.untrusted_before.add(run)
                pending_break = False
            words.append(StructWord(index=len(words), start=float(start), end=float(end),
                                    text=text.strip(), segment_id=seg.id, run=run,
                                    probability=probability))
    if pending_break and words:
        edges.untrusted_after.add(run)
    counts["excluded_seconds"] = round(counts["excluded_seconds"], 3)
    return words, edges, ("word" if has_words else "segment"), counts


def terminal_of(text: str, language: str) -> Optional[str]:
    """Sentence-ending punctuation at the end of a word, or None."""
    stripped = text.rstrip().rstrip(_TRAILING)
    if not stripped:
        return None
    last = stripped[-1]
    return last if last in TERMINALS.get(language, ALL_TERMINALS) else None


def build_sentences(words: list[StructWord], edges: RunEdges, gap_ms: list[int], language: str,
                    params: dict | None = None) -> list[Sentence]:
    """gap_ms[i] = measured VAD silence (ms) between words i and i+1; 0 when none."""
    p = {**UNIT_PARAMS, **(params or {})}
    sentences: list[Sentence] = []
    first = 0
    for i, word in enumerate(words):
        last_word = i == len(words) - 1
        run_ends = last_word or words[i + 1].run != word.run
        terminal = terminal_of(word.text, language)
        gap = 0 if last_word else gap_ms[i]
        if run_ends:
            reason = "untrusted" if word.run in edges.untrusted_after else "edge"
        elif terminal:
            reason = "punct"
        elif gap >= p["sentence_pause_ms"]:
            reason = "pause"
        else:
            continue
        sentences.append(Sentence(
            id=len(sentences), word_range=(first, i), start=words[first].start, end=word.end,
            text=" ".join(w.text for w in words[first:i + 1]), terminal=terminal,
            boundary_reason=reason, gap_after_ms=gap,
        ))
        first = i + 1
    return sentences


def build_thoughts(sentences: list[Sentence], params: dict | None = None) -> list[Thought]:
    p = {**UNIT_PARAMS, **(params or {})}
    groups: list[list[Sentence]] = []
    current: list[Sentence] = []
    for s in sentences:
        current.append(s)
        if (s.boundary_reason in ("untrusted", "edge")
                or s.gap_after_ms >= p["thought_break_ms"] or s.terminal == "?"):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    thoughts: list[Thought] = []
    for group in groups:
        pieces = _split_long(group, p["thought_max_s"])
        for n, piece in enumerate(pieces):
            reason = _thought_reason(piece[-1]) if n == len(pieces) - 1 else "max_length"
            first, last = piece[0], piece[-1]
            thoughts.append(Thought(
                id=len(thoughts), sentence_range=(first.id, last.id),
                word_range=(first.word_range[0], last.word_range[1]), start=first.start,
                end=last.end, text=" ".join(s.text for s in piece),
                boundary_reason=reason, gap_after_ms=last.gap_after_ms,
            ))
    return thoughts


def _thought_reason(last: Sentence) -> str:
    if last.boundary_reason in ("untrusted", "edge"):
        return last.boundary_reason
    if last.terminal == "?":
        return "question"
    return "pause"


def _split_long(group: list[Sentence], max_s: float) -> list[list[Sentence]]:
    """Split at the largest internal silence until every piece fits (or is one sentence)."""
    if len(group) == 1 or group[-1].end - group[0].start <= max_s:
        return [group]
    # Largest silence wins; among equal silences, the one nearest the middle, so a
    # run of equal pauses splits into balanced halves rather than peeling sentences.
    middle = (group[0].start + group[-1].end) / 2
    k = max(range(len(group) - 1), key=lambda i: (group[i].gap_after_ms, -abs(group[i].end - middle), -i))
    return _split_long(group[:k + 1], max_s) + _split_long(group[k + 1:], max_s)
