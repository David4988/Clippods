"""
services/transcript_quality.py — visible quality flags for ASR output.

Flags make problems visible; they never rewrite or drop text. Every threshold is
provisional and recorded in the transcript so a later tuning change is traceable.

Segment flags
  hallucination class — the text may not have been spoken (segment.hallucination_suspect):
    high_compression_ratio   compression_ratio > 2.4 (Whisper's own repetition guard), only for
                             Latin-script text: the ratio is gzip over UTF-8 bytes, and clean
                             Tamil text already scores 2.5–3.1 over a ~30 s window (EV-2.4).
                             Repetition in other scripts is caught by repeated_text instead.
    likely_no_speech         no_speech_prob > 0.6 and avg_logprob < -1.0 (Whisper's silence rule)
    repeated_text            same normalised text as one of the previous 2 segments,
                             or a 3-word phrase repeated 3+ times inside the segment
    words_outside_speech     > 50 % of word midpoints lie outside VAD speech regions
    no_speech_under_text     < 10 % of the segment lies inside VAD speech regions
  timing class — the text may be real, its timestamps are not trustworthy (segment.timing_suspect):
    outside_speech           < 30 % of the segment lies inside VAD speech regions
    timestamp_beyond_audio   segment ends after the decoded audio ends
    (EV-2.1: a correctly transcribed final sentence carried an end time 5 s past
    the audio; its text was real, only its timing was wrong.)
  low-confidence class (segment.low_confidence = True; the logprob/no-speech/
  temperature fields are decode-window level, so these flags are coarse):
    low_avg_logprob          avg_logprob < -1.0
    high_no_speech_prob      no_speech_prob > 0.6
    temperature_fallback     decoded at temperature > 0 (greedy/beam result was rejected)
    low_word_probability     mean word probability < 0.5
    script_mismatch          < 50 % of letters in the script expected for the decoding language
  informational:
    mixed_script             2+ scripts each ≥ 20 % of letters (possible code-switching)
    empty_text               no text

Transcript status is "degraded" (never silently "ok") when the language is
uncertain, > 20 % of segments are hallucination suspects, or usable segments
cover < 50 % of measured speech.

Quality gate (adaptive pipeline, `gate()`): turns the flags above into a decision
(ok | degraded | hard_fail) and a list of suspicious spans worth one regional retry.
A span is suspicious only on genuinely strong evidence:
  * a segment with any hallucination-class flag, or
  * a segment with weak signals from 2+ independent families (window confidence,
    word confidence, script, timing). One weak signal never counts; mixed_script
    never counts, so ordinary code-switching is not punished.
  * untranscribed speech: >= 4 s of VAD speech not covered by any trusted word
    (normal-length words from non-suspicious segments). This catches dropped
    speech hidden inside segments whose start/end stretch over it (EV-3.12).
Language disagreement is a transcript-level reason (degraded), never a region:
re-decoding a region cannot fix a wrong language selection.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from services.speech_regions import contains, overlap_seconds
from services.transcript import (
    SUPPORTED_LANGUAGES,
    LanguageInfo,
    SpeechRegions,
    SuspiciousSpan,
    Transcript,
    TranscriptQuality,
    TranscriptSegment,
)

THRESHOLDS = {
    "compression_ratio_max": 2.4,
    "avg_logprob_min": -1.0,
    "no_speech_prob_max": 0.6,
    "speech_overlap_min": 0.3,
    "no_speech_under_text_max": 0.1,
    "words_outside_speech_max": 0.5,
    "word_in_speech_tolerance_s": 0.2,
    "word_probability_min": 0.5,
    "expected_script_min": 0.5,
    "mixed_script_min_share": 0.2,
    "language_probability_min": 0.7,
    "suspect_segment_ratio_max": 0.2,
    "speech_coverage_min": 0.5,
}

HALLUCINATION_FLAGS = {"high_compression_ratio", "likely_no_speech", "repeated_text",
                       "words_outside_speech", "no_speech_under_text"}
TIMING_FLAGS = {"outside_speech", "timestamp_beyond_audio"}
LOW_CONFIDENCE_FLAGS = {"low_avg_logprob", "high_no_speech_prob", "temperature_fallback",
                        "low_word_probability", "script_mismatch"}

EXPECTED_SCRIPT = {"en": "latin", "hi": "devanagari", "ta": "tamil"}


# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------

def script_shares(text: str) -> dict[str, float]:
    """Share of letters per script: latin, devanagari, tamil, arabic, other."""
    counts: Counter[str] = Counter()
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            counts["devanagari"] += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            counts["tamil"] += 1
        elif not unicodedata.category(ch).startswith(("L", "M")):
            continue  # digits, punctuation, spaces
        elif cp < 0x0250:
            counts["latin"] += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
            counts["arabic"] += 1
        else:
            counts["other"] += 1
    total = sum(counts.values())
    return {k: round(v / total, 3) for k, v in sorted(counts.items())} if total else {}


def _normalise(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def _has_internal_repetition(text: str) -> bool:
    tokens = _normalise(text).split()
    if len(tokens) < 9:
        return False
    grams = Counter(tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2))
    return grams.most_common(1)[0][1] >= 3


# ---------------------------------------------------------------------------
# segment flags
# ---------------------------------------------------------------------------

def flag_segments(segments: list[TranscriptSegment], language: str, audio_duration: float,
                  speech: SpeechRegions | None) -> None:
    """Annotate segments in place (words.in_speech, speech_overlap, scripts, flags)."""
    t = THRESHOLDS
    regions = speech.regions if speech is not None else None
    recent: list[str] = []

    for seg in segments:
        flags: list[str] = []
        norm = _normalise(seg.text)

        if not seg.text:
            flags.append("empty_text")
        seg.scripts = script_shares(seg.text)
        latin_text = seg.scripts.get("latin", 0.0) >= t["expected_script_min"]
        if latin_text and seg.compression_ratio is not None and seg.compression_ratio > t["compression_ratio_max"]:
            flags.append("high_compression_ratio")
        if seg.avg_logprob is not None and seg.avg_logprob < t["avg_logprob_min"]:
            flags.append("low_avg_logprob")
        if seg.no_speech_prob is not None and seg.no_speech_prob > t["no_speech_prob_max"]:
            flags.append("high_no_speech_prob")
            if seg.avg_logprob is not None and seg.avg_logprob < t["avg_logprob_min"]:
                flags.append("likely_no_speech")
        if seg.temperature:
            flags.append("temperature_fallback")
        if (norm and norm in recent) or _has_internal_repetition(seg.text):
            flags.append("repeated_text")
        if seg.end > audio_duration + 0.05:
            flags.append("timestamp_beyond_audio")

        if regions is not None:
            length = max(seg.end - seg.start, 1e-6)
            seg.speech_overlap = round(overlap_seconds(seg.start, seg.end, regions) / length, 3)
            if seg.speech_overlap < t["speech_overlap_min"]:
                flags.append("outside_speech")
            if seg.text and seg.speech_overlap < t["no_speech_under_text_max"]:
                flags.append("no_speech_under_text")
            if seg.words:
                for w in seg.words:
                    w.in_speech = contains((w.start + w.end) / 2, regions, t["word_in_speech_tolerance_s"])
                outside = sum(1 for w in seg.words if not w.in_speech) / len(seg.words)
                if outside > t["words_outside_speech_max"]:
                    flags.append("words_outside_speech")

        if seg.words:
            probs = [w.probability for w in seg.words if w.probability is not None]
            if probs and sum(probs) / len(probs) < t["word_probability_min"]:
                flags.append("low_word_probability")

        expected = EXPECTED_SCRIPT.get(language)
        if seg.scripts and sum(1 for c in seg.text if c.isalpha()) >= 3:
            if expected and seg.scripts.get(expected, 0.0) < t["expected_script_min"]:
                flags.append("script_mismatch")
            if sum(1 for share in seg.scripts.values() if share >= t["mixed_script_min_share"]) >= 2:
                flags.append("mixed_script")

        seg.flags = flags
        seg.hallucination_suspect = any(f in HALLUCINATION_FLAGS for f in flags)
        seg.timing_suspect = any(f in TIMING_FLAGS for f in flags)
        seg.low_confidence = any(f in LOW_CONFIDENCE_FLAGS for f in flags)
        if norm:
            recent = (recent + [norm])[-2:]


# ---------------------------------------------------------------------------
# language uncertainty
# ---------------------------------------------------------------------------

def assess_language(info: LanguageInfo) -> None:
    """Fill info.uncertain / info.reasons. Records doubt; never overrides the language."""
    reasons: list[str] = []
    if info.language not in SUPPORTED_LANGUAGES:
        reasons.append(f"decoded language {info.language!r} is not one of {list(SUPPORTED_LANGUAGES)}")
    if info.mode == "auto":
        if info.probability is not None and info.probability < THRESHOLDS["language_probability_min"]:
            reasons.append(f"detection probability {info.probability:.2f} < {THRESHOLDS['language_probability_min']}")
        if info.probes:
            votes = Counter(p.language for p in info.probes)
            majority, count = votes.most_common(1)[0]
            if majority != info.language:
                reasons.append(f"language probes across the file favour {majority!r} "
                               f"({count}/{len(info.probes)}), decoder used {info.language!r}")
            elif len(votes) > 1:
                others = {k: v for k, v in votes.items() if k != majority}
                reasons.append(f"language probes disagree across the file: {dict(votes)} "
                               f"(possible code-switching or misdetection; other: {others})")
    elif info.mode == "mixed":
        pass  # code-switched speech: probes are expected to disagree
    elif info.probes:
        votes = Counter(p.language for p in info.probes)
        majority, count = votes.most_common(1)[0]
        if majority != info.mode:
            reasons.append(f"language forced to {info.mode!r} but probes favour {majority!r} "
                           f"({count}/{len(info.probes)})")
    info.reasons = reasons
    info.uncertain = bool(reasons)


# ---------------------------------------------------------------------------
# transcript quality
# ---------------------------------------------------------------------------

def summarise(segments: list[TranscriptSegment], language: LanguageInfo,
              speech: SpeechRegions | None) -> TranscriptQuality:
    t = THRESHOLDS
    flag_counts = Counter(f for seg in segments for f in seg.flags)
    suspects = sum(1 for s in segments if s.hallucination_suspect)
    timing_suspects = sum(1 for s in segments if s.timing_suspect)
    low_conf = sum(1 for s in segments if s.low_confidence)
    word_count = sum(len(s.words) if s.words is not None else len(s.text.split()) for s in segments)

    speech_seconds = transcribed = coverage = outside = None
    if speech is not None:
        speech_seconds = speech.speech_seconds
        usable = _merge([(s.start, s.end) for s in segments if s.usable])
        transcribed = round(sum(overlap_seconds(a, b, speech.regions) for a, b in usable), 3)
        coverage = round(transcribed / speech_seconds, 3) if speech_seconds else None
        if any(s.words for s in segments):
            spans = [(w.start, min(w.end, speech.audio_duration)) for s in segments for w in (s.words or [])]
        else:
            spans = [(s.start, min(s.end, speech.audio_duration)) for s in segments if s.text]
        all_text = _merge(spans)
        outside = round(sum((b - a) - overlap_seconds(a, b, speech.regions) for a, b in all_text), 3)

    reasons: list[str] = []
    if language.uncertain:
        reasons.append("language uncertain: " + "; ".join(language.reasons))
    if segments and suspects / len(segments) > t["suspect_segment_ratio_max"]:
        reasons.append(f"{suspects}/{len(segments)} segments are hallucination suspects")
    if coverage is not None and speech_seconds and speech_seconds > 5 and coverage < t["speech_coverage_min"]:
        reasons.append(f"usable segments cover {coverage:.0%} of measured speech")
    if speech_seconds is not None and speech_seconds > 5 and not segments:
        reasons.append("speech was measured but no text was transcribed")

    return TranscriptQuality(
        status="degraded" if reasons else "ok",
        reasons=reasons,
        thresholds=dict(t),
        segment_count=len(segments),
        word_count=word_count,
        flag_counts=dict(sorted(flag_counts.items())),
        hallucination_suspect_segments=suspects,
        timing_suspect_segments=timing_suspects,
        low_confidence_segments=low_conf,
        speech_seconds=speech_seconds,
        transcribed_speech_seconds=transcribed,
        speech_coverage=coverage,
        text_outside_speech_seconds=outside,
        mixed_script_segments=flag_counts.get("mixed_script", 0),
    )


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for a, b in sorted(spans):
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


# ---------------------------------------------------------------------------
# quality gate (adaptive pipeline)
# ---------------------------------------------------------------------------

GATE_THRESHOLDS = {
    "weak_families_min": 2,
    "untranscribed_speech_min_s": 4.0,
    "untranscribed_join_gap_s": 1.0,
    "trusted_word_max_duration_s": 2.0,
    "trusted_word_pad_s": 0.5,
    "hard_fail_trusted_coverage_max": 0.25,
    "min_speech_s": 5.0,
}

# Weak-signal families. Window-level fields (logprob, no-speech, temperature) are
# copied onto every segment of a ~30 s decode window, so they count as ONE family.
WEAK_FAMILIES = {
    "window_confidence": {"low_avg_logprob", "high_no_speech_prob", "temperature_fallback"},
    "word_confidence": {"low_word_probability"},
    "script": {"script_mismatch"},
    "timing": set(TIMING_FLAGS),
}


def segment_suspicion(seg: TranscriptSegment) -> list[str]:
    """Reasons the gate distrusts this segment's text; [] when it is trusted."""
    strong = [f for f in seg.flags if f in HALLUCINATION_FLAGS]
    if strong:
        return strong
    families = sorted(name for name, members in WEAK_FAMILIES.items() if members & set(seg.flags))
    if len(families) >= GATE_THRESHOLDS["weak_families_min"]:
        return [f"weak:{name}" for name in families]
    return []


def trusted_coverage(segments: list[TranscriptSegment], speech: SpeechRegions) -> list[tuple[float, float]]:
    """Time spans backed by trusted text (padded words, or segment spans without words)."""
    g = GATE_THRESHOLDS
    spans = []
    for seg in segments:
        if not seg.text or segment_suspicion(seg):
            continue
        if seg.words is None:
            spans.append((seg.start, seg.end))
            continue
        for w in seg.words:
            # Abnormally long words are alignment artefacts stretched over audio
            # the decoder skipped (EV-3.9/3.12); they are not evidence of coverage.
            if 0 < w.end - w.start <= g["trusted_word_max_duration_s"]:
                spans.append((w.start - g["trusted_word_pad_s"], w.end + g["trusted_word_pad_s"]))
    return _merge(spans)


def untranscribed_speech(segments: list[TranscriptSegment], speech: SpeechRegions) -> list[tuple[float, float, float]]:
    """(start, end, speech_seconds) for runs of measured speech with no trusted text."""
    g = GATE_THRESHOLDS
    covered = trusted_coverage(segments, speech)
    gaps: list[list[float]] = []
    for r_start, r_end in speech.regions:
        cursor = r_start
        for c_start, c_end in covered:
            if c_end <= cursor or c_start >= r_end:
                continue
            if c_start > cursor:
                gaps.append([cursor, c_start])
            cursor = max(cursor, c_end)
        if cursor < r_end:
            gaps.append([cursor, r_end])

    runs: list[list[float]] = []
    for a, b in gaps:
        if runs and a - runs[-1][1] <= g["untranscribed_join_gap_s"]:
            runs[-1][1] = b
            runs[-1][2] += b - a
        else:
            runs.append([a, b, b - a])
    return [(round(a, 3), round(b, 3), round(sec, 3)) for a, b, sec in runs
            if sec >= g["untranscribed_speech_min_s"]]


def suspicious_spans(segments: list[TranscriptSegment], speech: SpeechRegions | None) -> list[SuspiciousSpan]:
    spans: list[SuspiciousSpan] = []
    for seg in segments:
        reasons = segment_suspicion(seg)
        if reasons:
            spans.append(SuspiciousSpan(start=seg.start, end=seg.end, reasons=reasons, segment_ids=[seg.id]))
    if speech is not None:
        suspect = _merge([(sp.start, sp.end) for sp in spans])
        for start, end, seconds in untranscribed_speech(segments, speech):
            # Speech under an already-suspicious segment is explained by that segment.
            unexplained = seconds - sum(
                overlap_seconds(max(a, start), min(b, end), speech.regions)
                for a, b in suspect if b > start and a < end)
            if unexplained < GATE_THRESHOLDS["untranscribed_speech_min_s"]:
                continue
            ids = [s.id for s in segments if s.start < end and s.end > start]
            spans.append(SuspiciousSpan(start=start, end=end,
                                        reasons=[f"untranscribed_speech:{seconds:.1f}s"], segment_ids=ids))
    return sorted(spans, key=lambda sp: (sp.start, sp.end))


def gate(transcript: Transcript) -> tuple[str, list[str], list[SuspiciousSpan]]:
    """
    Decide ok | degraded | hard_fail and list suspicious spans.

    hard_fail: measured speech exists but trusted text covers < 25 % of it.
    degraded:  any suspicious span, or a transcript-level reason from summarise()
               (language disagreement, suspect ratio, low coverage).
    """
    g = GATE_THRESHOLDS
    speech = transcript.speech_regions
    spans = suspicious_spans(transcript.segments, speech)
    reasons = list(transcript.quality.reasons)
    if spans:
        reasons.append(f"{len(spans)} suspicious span(s)")

    if speech is not None and speech.speech_seconds >= g["min_speech_s"]:
        covered = trusted_coverage(transcript.segments, speech)
        trusted = sum(overlap_seconds(a, b, speech.regions) for a, b in covered)
        share = trusted / speech.speech_seconds
        if share < g["hard_fail_trusted_coverage_max"]:
            return "hard_fail", reasons + [f"trusted text covers {share:.0%} of measured speech"], spans
    return ("degraded" if reasons else "ok"), reasons, spans
