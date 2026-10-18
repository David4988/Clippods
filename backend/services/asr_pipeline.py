"""
services/asr_pipeline.py — adaptive ASR with one bounded, region-scoped retry.

    audio → VAD + language probes (once)
          → profile selection (manual language is primary; auto uses the probes)
          → attempt 1 (full file)
          → quality gate (transcript_quality.gate)
          → build retry regions from suspicious spans (aligned to VAD gaps)
          → exactly ONE retry per region (base → large-v3; large-v3 → flip previous-text)
          → accept a retry only if it is better for that region, merge in place
          → re-flag + gate again → final status

Never more than two decodes of any audio: there is no loop over attempts.
Every segment carries `attempt`, pointing at Transcript.attempts, so each piece
of text can be traced to the model/config that produced it and why.

Final quality.status:
  ok              gate passes
  degraded        transcript-level doubts (e.g. language disagreement) or new
                  suspicious spans outside any retried region
  still_degraded  a retried region is still suspicious (best result kept)
  hard_fail       trusted text covers < 25 % of measured speech after the retry
"""
from __future__ import annotations

import copy
import logging
import time
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

from fastapi import HTTPException

from services import transcript_quality, transcription
from services.speech_regions import overlap_seconds
from services.transcript import (
    LANGUAGE_SELECTIONS,
    SUPPORTED_LANGUAGES,
    AsrAttempt,
    LanguageProbe,
    SuspiciousSpan,
    Transcript,
    TranscriptSegment,
)
from services.transcription import PROFILES, AsrProfile

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "adaptive_v1"
SAMPLE_RATE = 16000

LANGUAGE_PROFILE = {"en": "en_v1", "hi": "hi_v1", "ta": "ta_v1", "mixed": "mixed_v1"}
RETRY_MODEL = "large-v3"
KNOWN_MODELS = ("base", "large-v3")

# Auto selection from language probes (provisional, recorded in every transcript).
AUTO_PARAMS = {
    "single_language_min_share": 0.75,
    "single_language_min_probability": 0.6,
}

# Retry-region geometry (provisional, recorded in every transcript).
REGION_PARAMS = {
    "merge_gap_s": 2.0,        # suspicious spans closer than this become one region
    "pad_s": 1.0,              # context added on both sides before snapping
    "max_snap_s": 5.0,         # how far a boundary may move outward to reach a VAD gap
    "gap_margin_s": 0.25,      # boundary sits this far into the silence (or mid-gap if shorter)
    "min_region_s": 10.0,      # shorter regions decode with too little context
    "max_geometry_passes": 10, # expand/snap passes (geometry only, not decode attempts)
    # CP3/D26: PROPOSED (unvalidated) bound. A longer region is not retried at all —
    # it is never split into several decodes, which would spend the same compute under
    # another name. Shaped by EV-4.5: every region >= 238 s stayed suspicious, every
    # region that resolved was <= 81 s.
    "max_region_s": 120.0,
}

# CP3/D28: PROPOSED (unvalidated). Total retried audio may not exceed this fraction
# of the file, so a run costs at most ~1.3 decode passes instead of the 2.0 measured
# on the 74-minute Tamil file (EV-4.6: 98 % re-decoded, 3 h 52 min).
RETRY_BUDGET_FRACTION = 0.30
# Floor so short inputs can still afford one bounded region (D26's max_region_s).
# On a 74-minute file the fraction dominates, so the cap keeps its meaning.
RETRY_BUDGET_MIN_S = REGION_PARAMS["max_region_s"]

# CP3/D27: a retry replaces attempt 1 only when the region gains trusted speech AND
# nothing regresses. Trusted speech alone accepted a transliteration drift (EV-4.3).
ACCEPT_PARAMS = {
    "trusted_gain_min_s": 1.0,     # accept if trusted speech coverage grows by this much
    "trusted_loss_max_s": 1.0,     # or stays within this and suspect seconds shrink
    # PROPOSED (unvalidated): when attempt 1 carries at least this much Latin text,
    # the retry may not lose more than `latin_share_drop_max` of it. hi2's drift was
    # 0.50 -> 0.13 (EV-4.3).
    "code_switch_latin_min": 0.15,
    "latin_share_drop_max": 0.15,
}


# ---------------------------------------------------------------------------
# profile selection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileChoice:
    selection: str                  # what the user asked for: auto | en | hi | ta | mixed
    target: str                     # en | hi | ta | mixed (auto resolved)
    decode_language: Optional[str]  # language forced on the decoder (None = detect)
    profile: AsrProfile
    reasons: tuple[str, ...] = ()


def available_models(candidates=KNOWN_MODELS) -> set[str]:
    """Models present in the local cache. Never downloads."""
    from faster_whisper.utils import download_model
    from config import ASR_MODEL_DIR

    found = set()
    for name in candidates:
        try:
            download_model(name, local_files_only=True, cache_dir=ASR_MODEL_DIR)
            found.add(name)
        except Exception:
            pass
    return found


def resolve_auto(probes: list[LanguageProbe]) -> tuple[str, list[str]]:
    """Map language probes to en | hi | ta | mixed. Disagreement → mixed, never a guess."""
    if not probes:
        return "mixed", ["auto: no language probes (little or no speech); using mixed profile"]
    votes = Counter(p.language for p in probes)
    majority, count = votes.most_common(1)[0]
    share = count / len(probes)
    mean_p = sum(p.probability for p in probes if p.language == majority) / count
    if (majority in SUPPORTED_LANGUAGES and share >= AUTO_PARAMS["single_language_min_share"]
            and mean_p >= AUTO_PARAMS["single_language_min_probability"]):
        return majority, [f"auto: probes {dict(votes)} → {majority} (share {share:.2f}, mean p {mean_p:.2f})"]
    return "mixed", [f"auto: probes {dict(votes)} do not agree on one supported language → mixed"]


def _majority_supported(probes: list[LanguageProbe]) -> Optional[str]:
    votes = Counter(p.language for p in probes if p.language in SUPPORTED_LANGUAGES)
    return votes.most_common(1)[0][0] if votes else None


def select_profile(selection: str, available: set[str],
                   probes: list[LanguageProbe] | None = None) -> ProfileChoice:
    """
    Deterministic language + available models → decode profile.

    A manual selection is never changed by the probes; for "auto" the probes decide.
    If the profile's model is missing locally, the other known model is used and
    the substitution is recorded.
    """
    if selection not in LANGUAGE_SELECTIONS:
        raise ValueError(f"language must be one of {list(LANGUAGE_SELECTIONS)}")
    probes = probes or []
    reasons: list[str] = []
    target = selection
    if selection == "auto":
        target, why = resolve_auto(probes)
        reasons += why
    else:
        reasons.append(f"manual selection {selection!r}")

    profile = PROFILES[LANGUAGE_PROFILE[target]]
    if profile.model not in available:
        substitute = next((m for m in ("large-v3", "base") if m in available), None)
        if substitute is None:
            raise HTTPException(status_code=503, detail="Transcription is unavailable: no Faster-Whisper "
                                                        "model is present locally.")
        reasons.append(f"{profile.model} not available locally; using {substitute}")
        profile = replace(profile, name=f"{profile.name}@{substitute}", model=substitute)

    # Mixed speech has no single language; decode with the dominant supported one
    # from the probes (whole-file evidence) or let the decoder detect.
    decode_language = target if target in SUPPORTED_LANGUAGES else _majority_supported(probes)
    return ProfileChoice(selection=selection, target=target, decode_language=decode_language,
                         profile=profile, reasons=tuple(reasons))


def retry_profile_for(profile: AsrProfile, available: set[str]) -> Optional[AsrProfile]:
    """base → large-v3 (previous-text OFF); large-v3 → large-v3 with previous-text flipped."""
    if profile.model != RETRY_MODEL:
        if RETRY_MODEL not in available:
            return None
        return replace(profile, name=f"{profile.name}.retry", model=RETRY_MODEL,
                       condition_on_previous_text=False)
    return replace(profile, name=f"{profile.name}.retry",
                   condition_on_previous_text=not profile.condition_on_previous_text)


# ---------------------------------------------------------------------------
# retry regions
# ---------------------------------------------------------------------------

@dataclass
class RetryRegion:
    start: float
    end: float
    spans: list[SuspiciousSpan]
    notes: list[str] = field(default_factory=list)
    skip_reason: Optional[str] = None   # set when policy refuses to retry this region

    @property
    def seconds(self) -> float:
        return self.end - self.start


def _snap_start(t: float, regions: list[tuple[float, float]], p: dict) -> tuple[float, bool]:
    """Move *t* back to just before the speech it falls in. Returns (time, cuts_speech)."""
    prev_end = 0.0
    for r_start, r_end in regions:
        if r_start < t < r_end:
            margin = min(p["gap_margin_s"], (r_start - prev_end) / 2)
            snapped = max(0.0, r_start - margin)
            if t - snapped <= p["max_snap_s"]:
                return snapped, False
            return t, True
        if r_start >= t:
            break
        prev_end = r_end
    return t, False


def _snap_end(t: float, regions: list[tuple[float, float]], duration: float, p: dict) -> tuple[float, bool]:
    for i, (r_start, r_end) in enumerate(regions):
        if r_start < t < r_end:
            next_start = regions[i + 1][0] if i + 1 < len(regions) else duration
            margin = min(p["gap_margin_s"], (next_start - r_end) / 2)
            snapped = min(duration, r_end + margin)
            if snapped - t <= p["max_snap_s"]:
                return snapped, False
            return t, True
        if r_start >= t:
            break
    return t, False


def build_retry_regions(spans: list[SuspiciousSpan], segments: list[TranscriptSegment],
                        speech_regions: list[tuple[float, float]], duration: float,
                        params: dict | None = None) -> list[RetryRegion]:
    """
    Suspicious spans → non-overlapping retry regions that:
      * merge nearby spans, add padding, meet a minimum size;
      * fully contain every attempt-1 segment they touch (so a merge can remove
        whole segments and never leaves half a sentence to duplicate);
      * start and end in VAD gaps when one is within reach (else noted `cuts_speech`).
    """
    p = {**REGION_PARAMS, **(params or {})}
    if not spans:
        return []

    groups: list[RetryRegion] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if groups and span.start - groups[-1].end <= p["merge_gap_s"]:
            groups[-1].end = max(groups[-1].end, span.end)
            groups[-1].spans.append(span)
        else:
            groups.append(RetryRegion(span.start, span.end, [span]))

    for region in groups:
        start = max(0.0, region.start - p["pad_s"])
        end = min(duration, region.end + p["pad_s"])
        if end - start < p["min_region_s"]:
            grow = (p["min_region_s"] - (end - start)) / 2
            start, end = max(0.0, start - grow), min(duration, end + grow)
            if end - start < p["min_region_s"]:  # hit a file edge: grow the other way
                start, end = max(0.0, end - p["min_region_s"]), min(duration, start + p["min_region_s"])

        cuts = set()
        for _ in range(p["max_geometry_passes"]):
            before = (start, end)
            for seg in segments:
                if seg.start < end and seg.end > start:
                    start, end = min(start, max(0.0, seg.start)), max(end, min(duration, seg.end))
            start, cut_start = _snap_start(start, speech_regions, p)
            end, cut_end = _snap_end(end, speech_regions, duration, p)
            cuts = {side for side, cut in (("start", cut_start), ("end", cut_end)) if cut}
            if (start, end) == before:
                break
        region.start, region.end = round(start, 3), round(end, 3)
        region.notes = [f"cuts_speech_at_{side}" for side in sorted(cuts)]

    merged: list[RetryRegion] = []
    for region in sorted(groups, key=lambda r: r.start):
        if merged and region.start <= merged[-1].end:
            last = merged[-1]
            last.end = max(last.end, region.end)
            last.spans += region.spans
            last.notes = sorted(set(last.notes + region.notes))
        else:
            merged.append(region)

    # CP3/D26: oversized regions are recorded, not retried and not split.
    for region in merged:
        if region.seconds > p["max_region_s"]:
            region.skip_reason = "too_large"
    return merged


def plan_retries(regions: list[RetryRegion], segments: list[TranscriptSegment],
                 speech_regions: list[tuple[float, float]], speech, audio_duration: float,
                 budget_fraction: float = RETRY_BUDGET_FRACTION) -> tuple[list[RetryRegion], list[RetryRegion]]:
    """
    Apply the CP3 retry budget (D28): spend it on the most suspicious regions first.

    Returns (to_retry in chronological order, skipped). Regions already refused by
    D26 keep their reason; the rest are refused with `budget_exhausted`.
    """
    budget = max(budget_fraction * audio_duration, RETRY_BUDGET_MIN_S)
    candidates = [r for r in regions if r.skip_reason is None]
    ranked = sorted(
        candidates,
        key=lambda r: region_metrics(segments, speech_regions, r.start, r.end, speech)["suspect_s"],
        reverse=True,
    )
    chosen: list[RetryRegion] = []
    spent = 0.0
    for region in ranked:
        if spent + region.seconds > budget:
            region.skip_reason = "budget_exhausted"
            continue
        chosen.append(region)
        spent += region.seconds
    skipped = [r for r in regions if r.skip_reason is not None]
    return sorted(chosen, key=lambda r: r.start), skipped


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def _norm_words(text: str) -> list[str]:
    return transcript_quality._normalise(text).split()


def _word_aligned(seg: TranscriptSegment) -> bool:
    """True when each word normalises to exactly one token, so token counts index words."""
    return bool(seg.words) and all(len(_norm_words(w.text)) == 1 for w in seg.words)


def _trim_leading_overlap(seg: TranscriptSegment, previous: TranscriptSegment) -> Optional[TranscriptSegment]:
    """Drop words at the start of *seg* that repeat the end of *previous* (n >= 3)."""
    new, old = _norm_words(seg.text), _norm_words(previous.text)
    if not new:
        return None
    if new == old[-len(new):]:
        return None                                    # whole segment is a duplicate
    overlap = next((n for n in range(min(len(new), len(old)), 2, -1) if new[:n] == old[-n:]), 0)
    if not overlap:
        return seg
    if not _word_aligned(seg) or len(seg.words) <= overlap:
        return seg                                     # cannot trim safely without aligned word timings
    kept = seg.words[overlap:]
    return replace(seg, words=kept, start=kept[0].start, text="".join(w.text for w in kept).strip())


def _trim_trailing_overlap(seg: TranscriptSegment, following: TranscriptSegment) -> Optional[TranscriptSegment]:
    new, old = _norm_words(seg.text), _norm_words(following.text)
    if not new:
        return None
    if new == old[:len(new)]:
        return None
    overlap = next((n for n in range(min(len(new), len(old)), 2, -1) if new[-n:] == old[:n]), 0)
    if not overlap:
        return seg
    if not _word_aligned(seg) or len(seg.words) <= overlap:
        return seg
    kept = seg.words[:-overlap]
    return replace(seg, words=kept, end=kept[-1].end, text="".join(w.text for w in kept).strip())


def merge_region(segments: list[TranscriptSegment], region: RetryRegion,
                 new_segments: list[TranscriptSegment], attempt: int
                 ) -> tuple[list[TranscriptSegment], list[TranscriptSegment]]:
    """
    Replace the segments inside *region* with *new_segments*.

    Returns (merged, removed). New segments are clipped to the region, tagged with
    *attempt*, deduplicated against the kept neighbours and renumbered.
    """
    removed = [s for s in segments if s.start < region.end and s.end > region.start]
    removed_ids = {id(s) for s in removed}
    before = [s for s in segments if s.end <= region.start and id(s) not in removed_ids]
    after = [s for s in segments if s.start >= region.end and id(s) not in removed_ids]

    placed: list[TranscriptSegment] = []
    for seg in sorted(new_segments, key=lambda s: s.start):
        mid = (seg.start + seg.end) / 2
        if not (region.start <= mid <= region.end) or not seg.text:
            continue
        words = None
        if seg.words is not None:
            words = [replace(w, start=max(w.start, region.start), end=min(w.end, region.end))
                     for w in seg.words if region.start <= (w.start + w.end) / 2 <= region.end]
        start, end = max(seg.start, region.start), min(seg.end, region.end)
        if placed:
            start = max(start, placed[-1].end)         # keep chronological, non-overlapping
        if end <= start:
            continue
        placed.append(replace(seg, start=round(start, 3), end=round(end, 3), words=words, attempt=attempt))

    if placed and before:
        first = _trim_leading_overlap(placed[0], before[-1])
        placed = ([first] if first else []) + placed[1:]
    if placed and after:
        last = _trim_trailing_overlap(placed[-1], after[0])
        placed = placed[:-1] + ([last] if last else [])

    merged = [replace(s, id=i) for i, s in enumerate(before + placed + after)]
    return merged, removed


# ---------------------------------------------------------------------------
# region scoring
# ---------------------------------------------------------------------------

def region_metrics(segments: list[TranscriptSegment], speech_regions: list[tuple[float, float]],
                   start: float, end: float, speech) -> dict:
    inside = [s for s in segments if s.start < end and s.end > start]
    covered = transcript_quality.trusted_coverage(inside, speech)
    clipped = [(max(a, start), min(b, end)) for a, b in covered if b > start and a < end]
    trusted = sum(overlap_seconds(a, b, speech_regions) for a, b in clipped)
    region_speech = overlap_seconds(start, end, speech_regions)
    suspect = sum(max(0.0, min(s.end, end) - max(s.start, start))
                  for s in inside if transcript_quality.segment_suspicion(s))
    # Script mix of the region's text: a collapsing Latin share means embedded English
    # was transliterated into the native script rather than kept as English (D27).
    scripts = transcript_quality.script_shares(" ".join(s.text for s in inside))
    return {
        "speech_s": round(region_speech, 2),
        "trusted_speech_s": round(trusted, 2),
        "suspect_s": round(suspect, 2),
        "words": sum(len(s.words) if s.words is not None else len(s.text.split()) for s in inside),
        "latin_share": round(scripts.get("latin", 0.0), 3),
        "scripts": scripts,
    }


def _better(before: dict, after: dict) -> tuple[bool, str]:
    """
    CP3/D27 acceptance. Returns (accept, reason).

    More trusted speech wins, or less suspicious text when trusted speech survives.
    Either way the retry must not increase suspect seconds and must not transliterate
    embedded English into the native script (EV-4.3).
    """
    a = ACCEPT_PARAMS
    gain = after["trusted_speech_s"] - before["trusted_speech_s"]
    improved = gain >= a["trusted_gain_min_s"] or (
        gain >= -a["trusted_loss_max_s"] and after["suspect_s"] < before["suspect_s"]
        and after["trusted_speech_s"] > 0
    )
    if not improved:
        return False, (f"no gain (trusted {before['trusted_speech_s']}→{after['trusted_speech_s']}s, "
                       f"suspect {before['suspect_s']}→{after['suspect_s']}s)")
    if after["suspect_s"] > before["suspect_s"]:
        return False, f"suspect seconds grew ({before['suspect_s']}→{after['suspect_s']}s)"
    latin_before, latin_after = before["latin_share"], after["latin_share"]
    if (latin_before >= a["code_switch_latin_min"]
            and latin_after < latin_before - a["latin_share_drop_max"]):
        return False, (f"code-switch regression: Latin share {latin_before:.2f}→{latin_after:.2f} "
                       f"(embedded English transliterated into the native script)")
    return True, (f"trusted {before['trusted_speech_s']}→{after['trusted_speech_s']}s, "
                  f"suspect {before['suspect_s']}→{after['suspect_s']}s")


def _reflag(segments: list[TranscriptSegment], transcript: Transcript) -> list[TranscriptSegment]:
    segments = copy.deepcopy(segments)
    transcript_quality.flag_segments(segments, transcript.language.language, transcript.audio_duration,
                                     transcript.speech_regions)
    return segments


def _still_suspicious(region: RetryRegion, spans: list[SuspiciousSpan]) -> list[SuspiciousSpan]:
    return [sp for sp in spans if sp.start < region.end - 0.5 and sp.end > region.start + 0.5]


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def transcribe_adaptive(audio_path: str, *, job_id: str | None = None, language: str = "auto",
                        available: set[str] | None = None) -> Transcript:
    """
    Adaptive transcription: one full decode, then at most one retry per suspicious region.

    language: auto | en | hi | ta | mixed. A manual choice is never overridden; the
    probes only add a disagreement reason. Failures raise like transcribe_rich().
    """
    if language not in LANGUAGE_SELECTIONS:
        raise HTTPException(status_code=400, detail=f"language must be one of {list(LANGUAGE_SELECTIONS)}")
    started = time.time()
    available = available_models() if available is None else set(available)

    # 1. VAD + probes, once. Auto probes with the strongest local model (base
    #    misdetects Hinglish as English, EV-3.4); manual probes use the attempt model.
    if language == "auto":
        probe_model_name = RETRY_MODEL if RETRY_MODEL in available else "base"
        choice = None
    else:
        choice = select_profile(language, available)
        probe_model_name = choice.profile.model
    probe_model = transcription.get_model(probe_model_name)
    if probe_model is None:
        raise HTTPException(status_code=503, detail=f"Transcription is unavailable: {probe_model_name} could "
                                                    f"not be loaded ({transcription._model_load_error}).")
    t0 = time.perf_counter()
    try:
        prepared = transcription.prepare_audio(audio_path, probe_model, job_id=job_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {type(exc).__name__}: {exc}") from exc
    prepare_s = round(time.perf_counter() - t0, 3)
    if language in ("auto", "mixed"):
        # auto: probes pick the profile. mixed: the profile is fixed by the user;
        # probes only pick the dominant language to hand the decoder.
        choice = select_profile(language, available, prepared.probes)

    # 2. attempt 1 (full file)
    t0 = time.perf_counter()
    transcript = transcription.transcribe_rich(
        audio_path, job_id=job_id, profile=choice.profile,
        language_mode=choice.decode_language or "auto", prepared=prepared,
    )
    attempt1_s = round(time.perf_counter() - t0, 3)
    _apply_selection(transcript, choice)

    status1, reasons1, spans1 = transcript_quality.gate(transcript)
    attempts = [AsrAttempt(
        attempt=1, scope="full", model=choice.profile.model, profile=choice.profile.name,
        condition_on_previous_text=choice.profile.condition_on_previous_text,
        language=transcript.language.language, region=None, retry_reasons=[], trigger_spans=[],
        quality_status=status1, outcome=None, segment_count=len(transcript.segments),
        decode_s=transcript.timings.get("decode_s", attempt1_s),
        metrics={"gate_reasons": reasons1, "suspicious_spans": len(spans1)},
    )]

    # 3. one retry per region
    retry_profile = retry_profile_for(choice.profile, available)
    speech = transcript.speech_regions
    speech_list = speech.regions if speech is not None else []
    all_regions = build_retry_regions(spans1, transcript.segments, speech_list, transcript.audio_duration)
    regions, skipped_regions = plan_retries(all_regions, transcript.segments, speech_list, speech,
                                            transcript.audio_duration)
    retry_skipped = None
    retries_t0 = time.perf_counter()
    segments = transcript.segments
    region_log: list[tuple[RetryRegion, AsrAttempt]] = []

    if regions and retry_profile is None:
        retry_skipped = f"no retry model available ({RETRY_MODEL} not present locally)"
        for region in regions:
            region.skip_reason = "no_retry_model"
        skipped_regions = list(all_regions)
        regions = []
    elif regions:
        if job_id is not None:
            from job_manager import update_job
            update_job(job_id, message=f"Re-checking {len(regions)} suspicious region(s)...")
        retry_model = transcription.get_model(retry_profile.model, retry_profile.device, retry_profile.compute_type)
        if retry_model is None:
            retry_skipped = f"retry model {retry_profile.model} could not be loaded"
            for region in regions:
                region.skip_reason = "retry_model_unavailable"
            skipped_regions = list(all_regions)
        for region in regions if retry_model is not None else []:
            transcription._raise_if_cancelled(job_id)
            number = len(attempts) + 1
            record = _retry_region(region, number, retry_model, retry_profile, transcript, segments, prepared)
            if record.outcome == "accepted":
                segments = record.metrics.pop("_merged")
            else:
                record.metrics.pop("_merged", None)
            attempts.append(record)
            region_log.append((region, record))

    # 4. re-flag the merged transcript and gate again
    transcript.segments = segments
    transcript_quality.flag_segments(segments, transcript.language.language, transcript.audio_duration, speech)
    transcript.quality = transcript_quality.summarise(segments, transcript.language, speech)
    status2, reasons2, spans2 = transcript_quality.gate(transcript)

    still = []
    for region, record in region_log:
        remaining = _still_suspicious(region, spans2)
        record.quality_status = "still_suspicious" if remaining else "resolved"
        if remaining:
            still.append(record.attempt)
    unretried = [r for r in skipped_regions if _still_suspicious(r, spans2)]
    if status2 == "hard_fail":
        final = "hard_fail"
    elif still or retry_skipped or unretried:
        final = "still_degraded"
    else:
        final = status2
    if unretried:
        by_reason = Counter(r.skip_reason for r in unretried)
        reasons2.append(f"{len(unretried)} suspicious region(s) not retried by policy: {dict(by_reason)}")
    if still:
        reasons2.append(f"retried region(s) still suspicious (attempts {still}); best result kept, no further retry")
    if retry_skipped:
        reasons2.append(f"suspicious regions not retried: {retry_skipped}")
    transcript.quality.status = final
    transcript.quality.reasons = reasons2
    transcript.suspicious_spans = spans2
    transcript.attempts = attempts

    transcript.asr["pipeline"] = {
        "version": PIPELINE_VERSION,
        "selection": choice.selection,
        "target": choice.target,
        "decode_language": choice.decode_language,
        "profile": choice.profile.name,
        "selection_reasons": list(choice.reasons),
        "available_models": sorted(available),
        "probe_model": probe_model_name,
        "retry_profile": None if retry_profile is None else asdict(retry_profile),
        "retry_skipped": retry_skipped,
        "regions": len(all_regions),
        "retries": len(region_log),
        "retried_seconds": round(sum(r.seconds for r in regions), 1),
        "retry_budget_s": round(max(RETRY_BUDGET_FRACTION * transcript.audio_duration,
                                    RETRY_BUDGET_MIN_S), 1),
        "skipped_regions": [{"start": r.start, "end": r.end, "seconds": round(r.seconds, 1),
                             "reason": r.skip_reason} for r in skipped_regions],
        "region_params": dict(REGION_PARAMS),
        "retry_budget_fraction": RETRY_BUDGET_FRACTION,
        "accept_params": dict(ACCEPT_PARAMS),
        "auto_params": dict(AUTO_PARAMS),
        "gate_thresholds": dict(transcript_quality.GATE_THRESHOLDS),
    }
    transcript.timings.update({
        "prepare_s": prepare_s,
        "attempt1_s": attempt1_s,
        "retries_s": round(time.perf_counter() - retries_t0, 3),
        "pipeline_total_s": round(time.time() - started, 3),
    })
    return transcript


def _apply_selection(transcript: Transcript, choice: ProfileChoice) -> None:
    """Record what the user selected; probes may add doubt but never change the language."""
    info = transcript.language
    info.mode = choice.selection
    if choice.selection == "auto" and info.probes:
        votes = Counter(p.language for p in info.probes)
        chosen = [p.probability for p in info.probes if p.language == info.language]
        info.probability = round(sum(chosen) / len(chosen), 4) if chosen else None
        info.top = [(code, round(n / len(info.probes), 4)) for code, n in votes.most_common(5)]
    transcript_quality.assess_language(info)
    transcript.quality = transcript_quality.summarise(transcript.segments, info, transcript.speech_regions)


def _retry_region(region: RetryRegion, number: int, model, profile: AsrProfile, transcript: Transcript,
                  segments: list[TranscriptSegment], prepared) -> AsrAttempt:
    """Decode one region once, keep it only if it is better. Never re-invoked on its own output."""
    speech = transcript.speech_regions
    speech_list = speech.regions if speech is not None else []
    language = transcript.language.language
    # Keep "weak:<family>" intact; drop only the per-span seconds of untranscribed_speech.
    reasons = sorted({r.split(":")[0] if r.startswith("untranscribed_speech") else r
                      for sp in region.spans for r in sp.reasons})
    before = region_metrics(segments, speech_list, region.start, region.end, speech)

    t0 = time.perf_counter()
    audio = prepared.audio[int(region.start * SAMPLE_RATE):int(region.end * SAMPLE_RATE)]
    record = AsrAttempt(
        attempt=number, scope="region", model=profile.model, profile=profile.name,
        condition_on_previous_text=profile.condition_on_previous_text, language=language,
        region=(region.start, region.end), retry_reasons=reasons, trigger_spans=list(region.spans),
        quality_status="pending", outcome=None, segment_count=0, decode_s=0.0,
        metrics={"before": before, "region_notes": region.notes, "retry_of": 1},
    )
    try:
        new_segments, _ = transcription._decode(
            model, audio, profile, language, transcription.decode_options_for(profile, language),
            job_id=None, offset=region.start,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Region retry %.1f-%.1fs failed: %s", region.start, region.end, exc)
        record.outcome = "failed"
        record.metrics["error"] = f"{type(exc).__name__}: {exc}"
        record.decode_s = round(time.perf_counter() - t0, 3)
        return record
    record.decode_s = round(time.perf_counter() - t0, 3)
    record.segment_count = len(new_segments)

    candidate, removed = merge_region(segments, region, new_segments, number)
    candidate = _reflag(candidate, transcript)
    after = region_metrics(candidate, speech_list, region.start, region.end, speech)
    record.metrics["after"] = after
    accept, why = _better(before, after)
    record.metrics["decision"] = why
    if accept:
        record.outcome = "accepted"
        record.replaced = [{"id": s.id, "attempt": s.attempt, "start": s.start, "end": s.end,
                            "text": s.text[:200], "flags": list(s.flags)} for s in removed]
        record.metrics["_merged"] = candidate
    else:
        record.outcome = "rejected"
        record.metrics["rejected_text"] = " ".join(s.text for s in new_segments)[:400]
    return record
