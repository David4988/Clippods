"""
services/selection/boundary_v1.py — deterministic clip picker built on sentence
boundaries and safe cut points (master plan Phase 6, §14.3–§14.6).

    SpeechStructure (Phase 5)
      → candidates: start at a cut before a sentence, end at a cut after a sentence,
                    within the hard duration limits, up to 3 ending variants per start
      → prune: mostly untrusted transcript, mostly non-speech
      → features + score (features.py)
      → pick up to N with no overlap, tiered relaxation (ranker.py)
      → clips + an analysis that explains every choice

Every clip time is a CutPoint time — this engine never invents a time, and every
clip edge lies inside a measured VAD silence. No model is involved.
"""
from __future__ import annotations

import time
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from services.selection import features as feat
from services.selection.ranker import pick, shortfall_reason
from services.transcript_quality import segment_suspicion

ENGINE = "boundary_v1"
ENGINE_VERSION = "boundary_v1.2"

PARAMS = {
    "target_min_s": 8.0,             # D7 (owner, revised 2026-10-20 after listening: "10 s is enough")
    "target_max_s": 10.0,            # D7
    "hard_min_s": 6.0,               # D7
    "hard_max_s": 12.0,              # D7
    "variants_per_start": 3,         # master plan §14.3
    "untrusted_share_max": 0.2,      # PROPOSED
    "speech_ratio_min": 0.6,         # PROPOSED: prunes music beds and long silences
    "quality_bar": 0.0,              # PROPOSED: tier 1 needs a score above the average candidate
    "similarity_max": 0.5,           # PROPOSED: char-3-gram Jaccard for near-duplicates
    "candidates_in_analysis": 50,
}

_END_STRENGTH = {"question": 3, "thought": 2, "edge": 1, "sentence": 1}


def select(transcript, structure, video_duration: float, clip_count: int,
           audio_path: Optional[str] = None, params: dict | None = None) -> tuple[list[dict], dict]:
    """Returns (clips, analysis). Fewer than clip_count clips only with a stated reason (D9)."""
    from services.audio_features import loudness_envelope

    t0 = time.perf_counter()
    p = {**PARAMS, **(params or {})}
    speech_regions = transcript.speech_regions.regions if transcript.speech_regions else []
    untrusted = [(s.start, s.end) for s in transcript.segments if s.text and segment_suspicion(s)]

    loudness = loudness_envelope(audio_path) if audio_path else None
    ctx = feat.FeatureContext(
        words=structure.words, sentences=structure.sentences,
        cut_kind={c.id: c.kind for c in structure.cut_points},
        speech=feat.IntervalIndex(speech_regions), untrusted=feat.IntervalIndex(untrusted),
        language=structure.language, params=p, loudness=loudness,
        loudness_mask=loudness.speech_mask(speech_regions) if loudness is not None else None,
    )

    generated, counts = _generate(structure, p)
    valid = []
    pruned: Counter = Counter()
    for c in generated:
        feat.measure(c, ctx)
        if c.features["untrusted_share"] > p["untrusted_share_max"]:
            pruned["mostly_untrusted_transcript"] += 1
        elif c.features["speech_ratio"] < p["speech_ratio_min"]:
            pruned["too_little_speech"] += 1
        else:
            valid.append(c)
    feat.normalise_and_score(valid)

    picked, decisions = pick(valid, clip_count, p)
    reason = shortfall_reason(len(picked), clip_count, len(valid), len(generated),
                              (p["hard_min_s"], p["hard_max_s"]))

    clips = []
    final = []
    for rank, (c, tier) in enumerate(picked):
        clips.append({
            "start": round(c.start, 3), "end": round(c.end, 3), "score": c.score, "tier": tier,
            "rank": rank, "candidate_id": c.id, "start_cut": c.start_cut, "end_cut": c.end_cut,
            "ends_on_question": bool(c.features["ends_on_question"]),
        })
        final.append({**_candidate_record(c, ctx), "clip_index": rank, "rank": rank, "tier": tier,
                      "filename": None, "reasons": _reasons(c, tier, ctx)})

    top = sorted(valid, key=lambda c: (-c.score, c.start))[:p["candidates_in_analysis"]]
    analysis = {
        "meta": {
            "engine": ENGINE, "engine_version": ENGINE_VERSION, "params": p, "weights": feat.WEIGHTS,
            "video_duration_seconds": video_duration, "language": structure.language,
            "structure_version": structure.version, "timing_source": structure.timing_source,
            "loudness": "available" if loudness is not None else "unavailable",
            "clip_count_requested": clip_count, "timestamp": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": round((time.perf_counter() - t0) * 1000, 1),
        },
        "counts": {**counts, "generated": len(generated), "pruned": dict(sorted(pruned.items())),
                   "valid": len(valid), "picked": len(picked)},
        "tiers": decisions,
        "shortfall_reason": reason,
        "final_clips": final,
        "candidates_top": [_candidate_record(c, ctx) for c in top],
    }
    return clips, analysis


def _generate(structure, p: dict) -> tuple[list[feat.Candidate], dict]:
    sentences = structure.sentences
    sentence_of = {}
    for s in sentences:
        for i in range(s.word_range[0], s.word_range[1] + 1):
            sentence_of[i] = s.id
    starts_at = {s.word_range[0] for s in sentences}
    ends_at = {s.word_range[1] for s in sentences}

    start_cuts = sorted((c for c in structure.cut_points
                         if c.cut_in is not None and c.before_word in starts_at), key=lambda c: c.cut_in)
    end_cuts = sorted((c for c in structure.cut_points
                       if c.cut_out is not None and c.after_word in ends_at), key=lambda c: c.cut_out)
    end_times = [c.cut_out for c in end_cuts]

    def off_target(duration: float) -> float:
        return max(0.0, p["target_min_s"] - duration, duration - p["target_max_s"])

    def end_strength(e) -> int:
        # D8 (revised): when a clip can stop right on a question, prefer that to running
        # on past it — the question is the hook.
        if sentences[sentence_of[e.after_word]].terminal == "?":
            return _END_STRENGTH["question"]
        return _END_STRENGTH.get(e.kind, 0)

    cands: list[feat.Candidate] = []
    for s in start_cuts:
        lo = bisect_left(end_times, s.cut_in + p["hard_min_s"])
        hi = bisect_right(end_times, s.cut_in + p["hard_max_s"])
        options = [e for e in end_cuts[lo:hi] if e.after_word >= s.before_word]
        options.sort(key=lambda e: (-end_strength(e), off_target(e.cut_out - s.cut_in), e.cut_out))
        for e in options[:p["variants_per_start"]]:
            first, last = s.before_word, e.after_word
            cands.append(feat.Candidate(
                id=len(cands), start_cut=s.id, end_cut=e.id, start=s.cut_in, end=e.cut_out,
                first_word=first, last_word=last,
                first_sentence=sentence_of[first], last_sentence=sentence_of[last],
                text=" ".join(w.text for w in structure.words[first:last + 1]),
            ))
    return cands, {"start_cuts": len(start_cuts), "end_cuts": len(end_cuts)}


def _candidate_record(c: feat.Candidate, ctx: feat.FeatureContext) -> dict:
    return {
        "candidate_id": c.id, "start": round(c.start, 3), "end": round(c.end, 3),
        "duration": round(c.duration, 3), "start_cut": c.start_cut, "end_cut": c.end_cut,
        "start_kind": ctx.cut_kind[c.start_cut], "end_kind": ctx.cut_kind[c.end_cut],
        "score": c.score, "features": {k: (round(v, 3) if isinstance(v, float) else v)
                                      for k, v in c.features.items()},
        "contributions": c.contributions, "text": c.text[:400],
    }


def _tier_note(tier: int, p: dict) -> str:
    target = f"{p['target_min_s']:g}–{p['target_max_s']:g} s"
    return {
        1: f"tier 1: inside the {target} target, above the quality bar, distinct from the other clips",
        2: "tier 2: below the quality bar, but no better non-overlapping clip was left",
        3: "tier 3: similar in wording to another clip, but no distinct one was left",
        4: f"tier 4: outside the {target} target (still {p['hard_min_s']:g}–{p['hard_max_s']:g} s), "
           "no in-target clip was left",
    }[tier]


_KIND_PHRASE = {"thought": "a thought boundary", "sentence": "a sentence boundary",
                "edge": "the edge of a reliable stretch of transcript", "pause": "a pause"}


def _reasons(c: feat.Candidate, tier: int, ctx: feat.FeatureContext) -> list[str]:
    f = c.features
    out = [_tier_note(tier, ctx.params),
           f"starts at {_KIND_PHRASE[ctx.cut_kind[c.start_cut]]}, ends at {_KIND_PHRASE[ctx.cut_kind[c.end_cut]]}"]
    for name, up, down in (("loudness_z", "louder", "quieter"), ("speech_rate_z", "faster", "slower"),
                           ("loudness_var_z", "more dynamic", "flatter"),
                           ("asr_confidence_z", "more clearly transcribed", "less clearly transcribed")):
        z = f.get(name) or 0.0
        if abs(z) >= 0.5:
            out.append(f"{up if z > 0 else down} than this video's average candidate (z={z:+.2f})")
    if f["question_count"]:
        out.append(f"raises {int(f['question_count'])} question(s) inside the clip")
    if f["ends_on_question"]:
        out.append("ends on a question — favoured, the question is the hook (D8)")
    if f["filler_start"]:
        out.append("penalised: starts with a filler/connective word")
    if f["lowercase_start"]:
        out.append("penalised: starts with a lower-case word (likely mid-sentence)")
    if f["start_unpunctuated"]:
        out.append("penalised: the sentence before it ended on a pause, not punctuation")
    if f["end_unpunctuated"]:
        out.append("penalised: ends on a pause, not punctuation")
    if f["context_start"]:
        out.append("penalised: starts with a word that points back to earlier context")
    if f["untrusted_share"]:
        out.append(f"{f['untrusted_share']:.0%} of the clip has an untrusted transcript")
    return out
