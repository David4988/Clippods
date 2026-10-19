"""
services/cut_points.py — the ONLY place clip cut times are created.

A cut point exists only inside a measured VAD silence (master plan §6.3): audio
owns time, words only say where a boundary is meaningful. A word boundary with
no silence of at least min_cut_gap_ms is *unsafe* and gets no cut point, however
good the sentence break looks in the text.

For each silence used:
  cut_out = min(gap_end, gap_start + post_roll_s)   — a clip may END here
  cut_in  = max(gap_start, gap_end − pre_roll_s)    — a clip may START here
Both always lie inside the silence by construction. At the edge of a trusted run
only one side is usable (cut_in before the run's first word, cut_out after its
last word), because the other side is untrusted text or the audio edge.

Parameters are provisional (D6 padding is decided at CP4) and recorded with
every result.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional

from services.units import RunEdges, Sentence, StructWord, Thought

CUT_PARAMS = {
    "word_gap_tolerance_s": 0.25,  # PROPOSED: word timings are approximate
    "min_cut_gap_ms": 150,         # PROPOSED: Silero's own minimum silence is 100 ms
    "pre_roll_s": 0.25,            # PROPOSED (D6)
    "post_roll_s": 0.35,           # PROPOSED (D6)
}

# strength = kind weight + min(gap, 2 s) / 2 s
KIND_WEIGHT = {"thought": 3.0, "sentence": 2.0, "edge": 2.0, "pause": 1.0}

Gap = tuple[float, float]


@dataclass
class CutPoint:
    id: int
    gap_start: float
    gap_end: float
    gap_ms: int
    cut_in: Optional[float]        # a clip may start here (None: text before it is not trusted)
    cut_out: Optional[float]       # a clip may end here (None: text after it is not trusted)
    after_word: Optional[int]      # last trusted word before the silence
    before_word: Optional[int]     # first trusted word after the silence
    kind: str                      # thought | sentence | pause | edge
    strength: float
    adjacent_untrusted: bool


@dataclass
class BoundaryGaps:
    between: list[Optional[Gap]]   # silence between word i and i+1 (None across runs or when absent)
    before: dict[int, Optional[Gap]]   # run's first word index → silence before it
    after: dict[int, Optional[Gap]]    # run's last word index → silence after it


def gap_ms(gap: Optional[Gap]) -> int:
    return 0 if gap is None else int(round((gap[1] - gap[0]) * 1000))


class _SilenceIndex:
    def __init__(self, silences: list[Gap]):
        self.silences = silences
        self.ends = [e for _, e in silences]

    def longest_in(self, lo: float, hi: float) -> Optional[Gap]:
        best = None
        for s, e in self.silences[bisect_right(self.ends, lo):]:
            if s >= hi:
                break
            if best is None or e - s > best[1] - best[0]:
                best = (s, e)
        return best


def boundary_gaps(words: list[StructWord], silences: list[Gap], params: dict | None = None) -> BoundaryGaps:
    """Find the measured silence at every word boundary and at the edges of trusted runs."""
    tol = {**CUT_PARAMS, **(params or {})}["word_gap_tolerance_s"]
    index = _SilenceIndex(silences)
    between: list[Optional[Gap]] = []
    before: dict[int, Optional[Gap]] = {}
    after: dict[int, Optional[Gap]] = {}
    for i, word in enumerate(words):
        if i == 0 or words[i - 1].run != word.run:
            before[i] = index.longest_in(word.start - tol, word.start + tol)
        if i == len(words) - 1 or words[i + 1].run != word.run:
            after[i] = index.longest_in(word.end - tol, word.end + tol)
            if i < len(words) - 1:
                between.append(None)
        else:
            nxt = words[i + 1]
            lo, hi = min(word.end, nxt.start), max(word.end, nxt.start)
            between.append(index.longest_in(lo - tol, hi + tol))
    _one_boundary_per_silence(words, between, tol)
    return BoundaryGaps(between=between, before=before, after=after)


def _one_boundary_per_silence(words: list[StructWord], between: list[Optional[Gap]], tol: float) -> None:
    """
    When word timings put several words inside one VAD silence, every boundary
    between them finds that same silence and the text shatters into one-word
    "sentences". A silence marks only the boundary whose word gap overlaps it
    most (earliest on ties); the others get no silence.
    """
    best: dict[Gap, tuple[float, int]] = {}
    for i, gap in enumerate(between):
        if gap is None:
            continue
        lo = min(words[i].end, words[i + 1].start) - tol
        hi = max(words[i].end, words[i + 1].start) + tol
        overlap = max(0.0, min(hi, gap[1]) - max(lo, gap[0]))
        if gap not in best or overlap > best[gap][0]:
            best[gap] = (overlap, i)
    for i, gap in enumerate(between):
        if gap is not None and best[gap][1] != i:
            between[i] = None


def build_cut_points(words: list[StructWord], edges: RunEdges, gaps: BoundaryGaps,
                     sentences: list[Sentence], thoughts: list[Thought],
                     params: dict | None = None) -> list[CutPoint]:
    """
    Create cut points in time order and attach start_cut / end_cut ids to the
    sentences and thoughts (None where the unit's boundary has no safe silence).
    """
    p = {**CUT_PARAMS, **(params or {})}
    thought_ends = {t.word_range[1] for t in thoughts}
    sentence_ends = {s.word_range[1] for s in sentences}
    cuts: list[CutPoint] = []
    by_gap: dict[Gap, int] = {}
    boundary_cut: dict[int, int] = {}      # after word i (inside a run)
    start_cut: dict[int, int] = {}         # before a run's first word
    end_cut: dict[int, int] = {}           # after a run's last word

    def place(gap: Optional[Gap], kind: str, after_word, before_word, can_in: bool, can_out: bool,
              untrusted: bool) -> Optional[int]:
        if gap is None or gap_ms(gap) < p["min_cut_gap_ms"]:
            return None
        g_start, g_end = gap
        if gap in by_gap:                  # two word boundaries resolved to one silence
            cut = cuts[by_gap[gap]]
            if KIND_WEIGHT[kind] > KIND_WEIGHT[cut.kind]:
                cut.kind = kind
                cut.strength = _strength(kind, cut.gap_ms)
            if can_in and cut.cut_in is None:
                cut.cut_in = round(max(g_start, g_end - p["pre_roll_s"]), 3)
            if can_out and cut.cut_out is None:
                cut.cut_out = round(min(g_end, g_start + p["post_roll_s"]), 3)
            cut.before_word = before_word if before_word is not None else cut.before_word
            cut.adjacent_untrusted = cut.adjacent_untrusted or untrusted
            return cut.id
        ms = gap_ms(gap)
        cut = CutPoint(
            id=len(cuts), gap_start=g_start, gap_end=g_end, gap_ms=ms,
            cut_in=round(max(g_start, g_end - p["pre_roll_s"]), 3) if can_in else None,
            cut_out=round(min(g_end, g_start + p["post_roll_s"]), 3) if can_out else None,
            after_word=after_word, before_word=before_word, kind=kind,
            strength=_strength(kind, ms), adjacent_untrusted=untrusted,
        )
        cuts.append(cut)
        by_gap[gap] = cut.id
        return cut.id

    for i, word in enumerate(words):
        if i in gaps.before:
            cid = place(gaps.before[i], "edge", None, i, can_in=True, can_out=False,
                        untrusted=word.run in edges.untrusted_before)
            if cid is not None:
                start_cut[i] = cid
        if i in gaps.after:
            cid = place(gaps.after[i], "edge", i, None, can_in=False, can_out=True,
                        untrusted=word.run in edges.untrusted_after)
            if cid is not None:
                end_cut[i] = cid
        else:
            kind = "thought" if i in thought_ends else "sentence" if i in sentence_ends else "pause"
            cid = place(gaps.between[i], kind, i, i + 1, can_in=True, can_out=True, untrusted=False)
            if cid is not None:
                boundary_cut[i] = cid

    def unit_start(i: int) -> Optional[int]:
        return start_cut.get(i) if i in gaps.before else boundary_cut.get(i - 1)

    def unit_end(j: int) -> Optional[int]:
        return end_cut.get(j) if j in gaps.after else boundary_cut.get(j)

    for unit in [*sentences, *thoughts]:
        unit.start_cut = unit_start(unit.word_range[0])
        unit.end_cut = unit_end(unit.word_range[1])
    return cuts


def _strength(kind: str, ms: int) -> float:
    return round(KIND_WEIGHT[kind] + min(ms, 2000) / 2000, 3)


def cuts_outside_silence(cuts: list[CutPoint], silences: list[Gap]) -> list[int]:
    """Ids of cut points whose cut_in/cut_out is not inside a measured silence (must be empty)."""
    index = _SilenceIndex(silences)
    bad = []
    for cut in cuts:
        for t in (cut.cut_in, cut.cut_out):
            if t is None:
                continue
            gap = index.longest_in(t - 1e-6, t + 1e-6)
            if gap is None or not (gap[0] - 1e-6 <= t <= gap[1] + 1e-6):
                bad.append(cut.id)
                break
    return bad
