"""
services/selection/ranker.py — pick up to N clips from scored candidates.

Greedy by score, with hard rules that are never relaxed:
  * no two clips overlap in time (D9)
  * no identical spans
and rules relaxed tier by tier only when fewer than N clips qualify (master plan
§14.6 adapted to D7/D9):
  Tier 1  duration inside the D7 target, score above the quality bar,
          not a near-duplicate of an already chosen clip
  Tier 2  quality bar dropped
  Tier 3  near-duplicate rule dropped
  Tier 4  durations outside the target but inside the hard limits allowed
If still fewer than N, the shortfall is returned with a reason (D9) — no
overlapping or duplicated fill.
"""
from __future__ import annotations

import re
from typing import Optional

from services.selection.features import Candidate

TIERS = [
    (1, {"target_only": True, "quality_bar": True, "distinct_text": True}),
    (2, {"target_only": True, "quality_bar": False, "distinct_text": True}),
    (3, {"target_only": True, "quality_bar": False, "distinct_text": False}),
    (4, {"target_only": False, "quality_bar": False, "distinct_text": False}),
]


def trigrams(text: str) -> set[str]:
    norm = re.sub(r"[\W_]+", " ", text.lower()).strip()
    return {norm[i:i + 3] for i in range(len(norm) - 2)} if len(norm) >= 3 else {norm}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _overlaps(c: Candidate, chosen: list[Candidate]) -> bool:
    return any(c.start < o.end and o.start < c.end for o in chosen)


def pick(cands: list[Candidate], count: int, params: dict) -> tuple[list[tuple[Candidate, int]], list[dict]]:
    """
    Returns ([(candidate, tier)], decisions). `decisions` records, per tier, how
    many clips it added — the trace the debugger shows.
    """
    ranked = sorted(cands, key=lambda c: (-c.score, c.start, c.end))
    chosen: list[Candidate] = []
    chosen_ids: set[int] = set()
    tiers: list[tuple[Candidate, int]] = []
    grams: dict[int, set[str]] = {}
    decisions = []

    for tier, rules in TIERS:
        added = 0
        for c in ranked:
            if len(chosen) >= count:
                break
            if c.id in chosen_ids or _overlaps(c, chosen):
                continue
            if rules["target_only"] and not (params["target_min_s"] <= c.duration <= params["target_max_s"]):
                continue
            if rules["quality_bar"] and c.score < params["quality_bar"]:
                continue
            if rules["distinct_text"]:
                g = grams.setdefault(c.id, trigrams(c.text))
                if any(similarity(g, grams.setdefault(o.id, trigrams(o.text))) >= params["similarity_max"]
                       for o in chosen):
                    continue
            chosen.append(c)
            chosen_ids.add(c.id)
            tiers.append((c, tier))
            added += 1
        decisions.append({"tier": tier, "rules": rules, "added": added})
        if len(chosen) >= count:
            break
    return tiers, decisions


def shortfall_reason(picked: int, count: int, valid: int, generated: int,
                     limits: tuple[float, float]) -> Optional[str]:
    if picked >= count:
        return None
    span = f"{limits[0]:g}–{limits[1]:g} s"
    if generated == 0:
        return ("no candidate clips: the audio has no stretch of whole sentences between safe "
                f"cuts that fits the {span} limits")
    if valid == 0:
        return "every candidate clip was rejected (mostly silence/music, or mostly untrusted transcript)"
    return (f"only {picked} non-overlapping clip(s) of {span} exist among {valid} valid candidates; "
            f"returning {picked} instead of {count} rather than overlapping or duplicating clips")
