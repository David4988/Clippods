"""
Adaptive ASR pipeline tests: profile selection, quality gate, retry regions,
one-retry cap, fallbacks, merge safety and provenance.

Faster-Whisper is replaced by a scripted fake that decodes "full file" and
"region" audio differently; audio, VAD and probes are injected.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from main import app
from services import asr_pipeline, transcript_quality, transcription
from services.asr_pipeline import RetryRegion, build_retry_regions, merge_region, retry_profile_for, select_profile
from services.transcript import (
    LanguageInfo, LanguageProbe, SpeechRegions, SuspiciousSpan, Transcript, TranscriptSegment, Word,
)

SR = 16000
BOTH = {"base", "large-v3"}
DURATION = 60.0
SPEECH = [(1.0, 19.0), (21.0, 39.0), (41.0, 59.0)]
LOOP = "la la la la la la la la la la"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def words_for(text, start, end, prob=0.9):
    tokens = text.split()
    step = (end - start) / max(len(tokens), 1)
    return [Word(round(start + i * step, 3), round(start + (i + 1) * step, 3), " " + t, prob)
            for i, t in enumerate(tokens)]


def seg(i, start, end, text, *, flags=None, words=True, prob=0.9, attempt=1):
    s = TranscriptSegment(id=i, start=start, end=end, text=text, avg_logprob=-0.2, compression_ratio=1.3,
                          no_speech_prob=0.01, temperature=0.0, token_count=5,
                          words=words_for(text, start, end, prob) if words else None, attempt=attempt)
    if flags is not None:
        s.flags = list(flags)
    return s


def speech_regions(spans=SPEECH, duration=DURATION):
    return SpeechRegions(method="test", params={}, regions=list(spans), audio_duration=duration)


def lang_info(language="en", mode="en", probes=()):
    return LanguageInfo(mode=mode, language=language, probability=None, top=[], probes=list(probes),
                        uncertain=False, reasons=[])


def make_transcript(segments, *, language="en", mode="en", probes=(), speech=None):
    speech = speech or speech_regions()
    info = lang_info(language, mode, probes)
    transcript_quality.assess_language(info)
    transcript_quality.flag_segments(segments, language, DURATION, speech)
    return Transcript(schema="clippods-transcript/1", asr={}, audio_duration=DURATION, language=info,
                      segments=segments, speech_regions=speech,
                      quality=transcript_quality.summarise(segments, info, speech), timings={})


def raw(start, end, text, prob=0.9):
    tokens = text.split()
    step = (end - start) / max(len(tokens), 1)
    words = [SimpleNamespace(start=start + i * step, end=start + (i + 1) * step, word=" " + t, probability=prob)
             for i, t in enumerate(tokens)]
    return SimpleNamespace(start=start, end=end, text=" " + text, avg_logprob=-0.3, compression_ratio=1.4,
                           no_speech_prob=0.02, temperature=0.0, tokens=[1, 2, 3], words=words)


GOOD_FULL = [
    raw(1.0, 9.0, "alpha bravo charlie delta echo foxtrot golf hotel"),
    raw(9.5, 18.5, "india juliet kilo lima mike november oscar papa"),
]
TAIL_FULL = [
    raw(41.0, 50.0, "quebec romeo sierra tango uniform victor whiskey xray"),
    raw(50.5, 58.5, "yankee zulu one two three four five six"),
]
LOOP_FULL = GOOD_FULL + [raw(21.0, 30.0, LOOP), raw(30.0, 38.5, LOOP)] + TAIL_FULL
CLEAN_FULL = GOOD_FULL + [raw(21.0, 30.0, "seven eight nine ten eleven twelve thirteen fourteen"),
                          raw(30.0, 38.5, "fifteen sixteen seventeen eighteen nineteen twenty")] + TAIL_FULL
# Region decode output (times relative to the region start, 20.0 s in the scenarios below).
GOOD_REGION = [raw(1.0, 9.5, "seven eight nine ten eleven twelve thirteen fourteen"),
               raw(10.0, 18.5, "fifteen sixteen seventeen eighteen nineteen twenty")]
LOOP_REGION = [raw(1.0, 9.5, LOOP), raw(10.0, 18.5, LOOP)]


class ScriptedModel:
    """Fake WhisperModel: full-file audio → `full`, shorter audio → `region`."""

    def __init__(self, name, calls, full=(), region=()):
        self.name, self.calls, self.full, self.region = name, calls, list(full), list(region)

    def transcribe(self, audio, **kwargs):
        seconds = len(audio) / SR
        scope = "full" if abs(seconds - DURATION) < 0.01 else "region"
        self.calls.append({"model": self.name, "scope": scope, "seconds": round(seconds, 2), **kwargs})
        info = SimpleNamespace(language=kwargs.get("language") or "en", language_probability=0.9,
                               all_language_probs=[], duration=seconds, duration_after_vad=seconds,
                               transcription_options=None, vad_options=None)
        return iter(self.full if scope == "full" else self.region), info

    def detect_language(self, audio=None, **kwargs):
        return "en", 0.9, []


@pytest.fixture()
def audio_file(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF....WAVEfmt ")
    return str(p)


def run(monkeypatch, audio_file, *, language, models, probes=(), available=BOTH):
    """Run transcribe_adaptive with injected models, audio, VAD and probes."""
    monkeypatch.setattr(transcription, "get_model", lambda name="base", *a, **k: models.get(name))
    monkeypatch.setattr(transcription, "prepare_audio", lambda path, model, probe_count=8, job_id=None:
                        transcription.PreparedAudio(audio=np.zeros(int(DURATION * SR), dtype=np.float32),
                                                    speech=speech_regions(), probes=list(probes)))
    return asr_pipeline.transcribe_adaptive(audio_file, language=language, available=available)


def probes_of(*languages):
    return [LanguageProbe(i * 7.0, i * 7.0 + 6.0, code, 0.9) for i, code in enumerate(languages)]


# ---------------------------------------------------------------------------
# profile selection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("selection, profile, model", [
    ("en", "en_v1", "base"), ("hi", "hi_v1", "large-v3"), ("ta", "ta_v1", "large-v3"),
    ("mixed", "mixed_v1", "large-v3"),
])
def test_manual_language_selects_its_profile(selection, profile, model):
    choice = select_profile(selection, BOTH)
    assert (choice.profile.name, choice.profile.model) == (profile, model)
    # D25 (Tamil) and D30 (Hindi): attempt 1 runs previous-text OFF; en and mixed keep ON.
    assert choice.profile.condition_on_previous_text is (selection in ("en", "mixed"))
    assert choice.decode_language == (None if selection == "mixed" else selection)


def test_tamil_attempt1_is_previous_text_off_and_its_retry_flips_it_on():
    ta = transcription.PROFILES["ta_v1"]
    assert ta.condition_on_previous_text is False          # D25
    assert retry_profile_for(ta, BOTH).condition_on_previous_text is True


def test_profiles_are_named_versioned_and_rich():
    for name in ("en_v1", "hi_v1", "ta_v1", "mixed_v1"):
        p = transcription.PROFILES[name]
        assert p.name == name and p.word_timestamps and p.vad_filter and p.script_aware_compression
    assert transcription.PROFILES["mixed_v1"].temperature == (0.0, 0.2, 0.4)


@pytest.mark.parametrize("languages, target", [
    (("hi",) * 8, "hi"),
    (("ta",) * 7 + ("en",), "ta"),
    (("en",) * 8, "en"),
    (("hi", "en") * 4, "mixed"),       # Hinglish: probes split
    (("fr",) * 8, "mixed"),            # unsupported language
    ((), "mixed"),                     # no speech probed
])
def test_auto_selection_uses_probes(languages, target):
    choice = select_profile("auto", BOTH, probes_of(*languages))
    assert choice.target == target
    assert choice.profile.name == asr_pipeline.LANGUAGE_PROFILE[target]


def test_mixed_decodes_with_the_dominant_supported_probe_language():
    assert select_profile("mixed", BOTH, probes_of("hi", "hi", "en")).decode_language == "hi"
    assert select_profile("mixed", BOTH, probes_of("fr")).decode_language is None


def test_manual_selection_ignores_probes_for_profile_choice():
    choice = select_profile("hi", BOTH, probes_of(*("en",) * 8))
    assert choice.profile.name == "hi_v1" and choice.decode_language == "hi"


def test_missing_model_is_substituted_and_recorded():
    choice = select_profile("hi", {"base"})
    assert choice.profile.model == "base" and choice.profile.name == "hi_v1@base"
    assert any("large-v3 not available" in r for r in choice.reasons)


def test_unknown_selection_is_rejected():
    with pytest.raises(ValueError):
        select_profile("fr", BOTH)


def test_manual_language_is_not_silently_overridden(monkeypatch, audio_file):
    calls = []
    models = {"large-v3": ScriptedModel("large-v3", calls, full=CLEAN_FULL)}
    t = run(monkeypatch, audio_file, language="hi", models=models, probes=probes_of(*("en",) * 8))

    assert calls[0]["language"] == "hi"                       # decoder got the user's language
    assert t.language.mode == "hi" and t.language.language == "hi"
    assert t.language.uncertain                               # disagreement is surfaced …
    assert any("probes favour 'en'" in r for r in t.language.reasons)
    assert t.asr["pipeline"]["profile"] == "hi_v1"            # … but not acted on


def test_auto_selection_end_to_end_records_why(monkeypatch, audio_file):
    calls = []
    models = {"large-v3": ScriptedModel("large-v3", calls, full=CLEAN_FULL),
              "base": ScriptedModel("base", calls, full=CLEAN_FULL)}
    t = run(monkeypatch, audio_file, language="auto", models=models, probes=probes_of(*("en",) * 8))
    assert t.asr["pipeline"]["target"] == "en" and t.asr["pipeline"]["profile"] == "en_v1"
    assert t.asr["pipeline"]["probe_model"] == "large-v3"
    assert t.language.mode == "auto" and t.language.language == "en" and t.language.probability == 0.9
    assert calls[0]["model"] == "base"


# ---------------------------------------------------------------------------
# quality gate
# ---------------------------------------------------------------------------

def clean_segments():
    return [seg(0, 1.0, 9.0, "alpha bravo charlie delta echo foxtrot golf hotel"),
            seg(1, 9.5, 18.5, "india juliet kilo lima mike november oscar papa"),
            seg(2, 21.0, 30.0, "seven eight nine ten eleven twelve thirteen fourteen"),
            seg(3, 30.0, 38.5, "fifteen sixteen seventeen eighteen nineteen twenty"),
            seg(4, 41.0, 50.0, "quebec romeo sierra tango uniform victor whiskey xray"),
            seg(5, 50.5, 58.5, "yankee zulu one two three four five six")]


def test_clean_transcript_passes_the_gate():
    status, reasons, spans = transcript_quality.gate(make_transcript(clean_segments()))
    assert (status, reasons, spans) == ("ok", [], [])


def test_one_weak_signal_or_code_switching_does_not_make_a_span():
    s = clean_segments()
    s[2].flags = ["script_mismatch", "mixed_script"]          # normal Hinglish line
    assert transcript_quality.segment_suspicion(s[2]) == []
    s[3].flags = ["low_avg_logprob", "high_no_speech_prob", "temperature_fallback"]  # one family
    assert transcript_quality.segment_suspicion(s[3]) == []


def test_two_independent_weak_families_make_a_span():
    s = seg(0, 1.0, 5.0, "some words here")
    s.flags = ["script_mismatch", "low_word_probability"]
    assert transcript_quality.segment_suspicion(s) == ["weak:script", "weak:word_confidence"]


def test_repetition_loop_is_a_span_and_degrades():
    s = clean_segments()
    s[2] = seg(2, 21.0, 30.0, LOOP)
    status, _, spans = transcript_quality.gate(make_transcript(s))
    assert status == "degraded"
    assert [(sp.start, sp.end) for sp in spans] == [(21.0, 30.0)]
    assert "repeated_text" in spans[0].reasons


def test_dropped_speech_under_stretched_words_is_found():
    s = clean_segments()
    # Same text, but its words squeeze into 21–23 s and one 7 s word "covers" the rest.
    s[2].words = words_for("seven eight nine", 21.0, 23.0) + [Word(23.0, 30.0, " ten", 0.9)]
    s[3] = seg(3, 30.0, 38.5, "fifteen sixteen seventeen eighteen nineteen twenty")
    _, _, spans = transcript_quality.gate(make_transcript(s))
    assert len(spans) == 1 and spans[0].reasons[0].startswith("untranscribed_speech")
    assert 23.0 <= spans[0].start < 24.0 and 29.0 < spans[0].end <= 30.0
    assert spans[0].segment_ids == [2]


def test_mostly_untrusted_transcript_is_a_hard_fail():
    s = [seg(0, 1.0, 19.0, LOOP), seg(1, 21.0, 39.0, LOOP), seg(2, 41.0, 59.0, LOOP)]
    status, reasons, _ = transcript_quality.gate(make_transcript(s))
    assert status == "hard_fail" and any("trusted text covers" in r for r in reasons)


def test_language_disagreement_degrades_without_a_region():
    t = make_transcript(clean_segments(), language="hi", mode="hi", probes=probes_of(*("en",) * 8))
    for s in t.segments:  # Latin text under forced Hindi: script_mismatch alone
        assert transcript_quality.segment_suspicion(s) == []
    status, reasons, spans = transcript_quality.gate(t)
    assert status == "degraded" and spans == []
    assert any("language uncertain" in r for r in reasons)


# ---------------------------------------------------------------------------
# retry regions
# ---------------------------------------------------------------------------

def span(a, b, reason="repeated_text"):
    return SuspiciousSpan(a, b, [reason], [])


def test_adjacent_spans_merge_into_one_region():
    regions = build_retry_regions([span(21.0, 25.0), span(26.0, 30.0), span(45.0, 50.0)], [], SPEECH, DURATION)
    assert len(regions) == 2 and len(regions[0].spans) == 2


def test_region_snaps_outward_to_vad_gaps():
    [r] = build_retry_regions([span(25.0, 35.0)], [], SPEECH, DURATION)
    # padded to 24–36 (inside speech 21–39) → snapped into the gaps before/after that speech
    assert r.start == pytest.approx(20.75) and r.end == pytest.approx(39.25)
    assert r.notes == []


def test_boundary_too_far_from_a_gap_stays_and_is_noted():
    [r] = build_retry_regions([span(25.0, 33.0)], [], SPEECH, DURATION)
    # end padded to 34; the gap after this speech is 5.25 s away (> max_snap_s 5)
    assert r.start == pytest.approx(20.75) and r.end == pytest.approx(34.0)
    assert r.notes == ["cuts_speech_at_end"]


def test_region_has_a_minimum_size():
    [r] = build_retry_regions([span(30.0, 31.0)], [], [(0.0, 60.0)], DURATION, params={"max_snap_s": 0.0})
    assert r.end - r.start >= asr_pipeline.REGION_PARAMS["min_region_s"] - 1e-6
    assert r.notes == ["cuts_speech_at_end", "cuts_speech_at_start"]


def test_region_never_cuts_through_an_attempt1_segment():
    speech = [(1.0, 9.0), (10.0, 19.0), (21.0, 39.0), (41.0, 59.0)]
    segments = [seg(0, 12.0, 26.0, "a long segment that crosses the region start")]
    [r] = build_retry_regions([span(25.0, 35.0)], segments, speech, DURATION)
    # grew to contain the whole segment (12.0), then snapped back into the 9–10 s gap
    assert r.start == pytest.approx(9.75) and r.notes == []
    far = [seg(0, 10.0, 26.0, "starts too far from any gap")]
    [r] = build_retry_regions([span(25.0, 35.0)], far, SPEECH, DURATION)
    assert r.start == pytest.approx(10.0) and "cuts_speech_at_start" in r.notes


def test_regions_stay_inside_the_audio():
    [r] = build_retry_regions([span(0.0, 2.0)], [], SPEECH, DURATION)
    assert r.start >= 0.0 and r.end <= DURATION


# ---------------------------------------------------------------------------
# fallback profiles
# ---------------------------------------------------------------------------

def test_retry_profile_base_goes_to_large_v3_without_previous_text():
    p = retry_profile_for(transcription.PROFILES["en_v1"], BOTH)
    assert (p.model, p.condition_on_previous_text, p.name) == ("large-v3", False, "en_v1.retry")


def test_retry_profile_large_v3_flips_previous_text():
    on = transcription.PROFILES["mixed_v1"]                  # large-v3, previous-text ON
    p = retry_profile_for(on, BOTH)
    assert (p.model, p.condition_on_previous_text) == ("large-v3", False)
    off = transcription.PROFILES["hi_v1"]                    # large-v3, previous-text OFF (D30)
    assert off.condition_on_previous_text is False
    assert retry_profile_for(off, BOTH).condition_on_previous_text is True


def test_retry_profile_is_none_without_large_v3_for_base():
    assert retry_profile_for(transcription.PROFILES["en_v1"], {"base"}) is None


# ---------------------------------------------------------------------------
# CP3 policies: bounded regions (D26), retry budget (D28), acceptance (D27)
# ---------------------------------------------------------------------------

def test_oversized_region_is_refused_not_split():
    long_speech = [(1.0, 290.0)]
    segments = [seg(0, 1.0, 290.0, LOOP)]
    [r] = build_retry_regions([span(5.0, 280.0)], segments, long_speech, 300.0)
    assert r.seconds > asr_pipeline.REGION_PARAMS["max_region_s"]
    assert r.skip_reason == "too_large"

    to_retry, skipped = asr_pipeline.plan_retries([r], segments, long_speech,
                                                  speech_regions(long_speech, 300.0), 300.0)
    assert to_retry == [] and skipped == [r]


def test_retry_budget_spends_on_the_most_suspicious_regions_first():
    speech = [(0.0, 1000.0)]
    segments = [seg(0, 20.0, 100.0, LOOP), seg(1, 320.0, 400.0, "clean words here and there")]
    quiet = RetryRegion(310.0, 410.0, [span(320.0, 400.0)])
    loud = RetryRegion(10.0, 110.0, [span(20.0, 100.0)])
    speech_obj = speech_regions(speech, 1000.0)
    transcript_quality.flag_segments(segments, "en", 1000.0, speech_obj)

    # Budget is 0.30 x 1000 s = 300 s, so both 100 s regions fit.
    to_retry, skipped = asr_pipeline.plan_retries([quiet, loud], segments, speech, speech_obj, 1000.0)
    assert [r.start for r in to_retry] == [10.0, 310.0] and skipped == []

    # With a 0.15 budget (150 s) only the most suspicious region is affordable.
    quiet.skip_reason = loud.skip_reason = None
    to_retry, skipped = asr_pipeline.plan_retries([quiet, loud], segments, speech, speech_obj, 1000.0,
                                                  budget_fraction=0.15)
    assert [r.start for r in to_retry] == [10.0]
    assert [r.skip_reason for r in skipped] == ["budget_exhausted"]


def test_budget_has_a_floor_so_short_inputs_still_get_one_region():
    assert asr_pipeline.RETRY_BUDGET_MIN_S == asr_pipeline.REGION_PARAMS["max_region_s"]
    speech = [(0.0, 60.0)]
    segments = [seg(0, 10.0, 40.0, LOOP)]
    region = RetryRegion(10.0, 40.0, [span(10.0, 40.0)])
    speech_obj = speech_regions(speech, 60.0)
    to_retry, skipped = asr_pipeline.plan_retries([region], segments, speech, speech_obj, 60.0)
    assert to_retry == [region] and skipped == []          # 0.30 x 60 s = 18 s < 30 s region


def test_unretried_regions_are_recorded_and_degrade_the_transcript(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL),
              "large-v3": ScriptedModel("large-v3", calls, region=GOOD_REGION)}
    monkeypatch.setitem(asr_pipeline.REGION_PARAMS, "max_region_s", 5.0)   # force "too_large"
    t = run(monkeypatch, audio_file, language="en", models=models)

    assert len(calls) == 1                                  # nothing retried
    assert t.quality.status == "still_degraded"
    skipped = t.asr["pipeline"]["skipped_regions"]
    assert skipped and all(r["reason"] == "too_large" for r in skipped)
    assert any("not retried by policy" in r for r in t.quality.reasons)


def test_acceptance_rejects_a_retry_that_transliterates_embedded_english():
    # D27(c): Hinglish (half Latin) replaced by the same content in Devanagari.
    before = {"trusted_speech_s": 40.0, "suspect_s": 1.0, "latin_share": 0.50}
    after = {"trusted_speech_s": 42.0, "suspect_s": 0.0, "latin_share": 0.13}
    accept, why = asr_pipeline._better(before, after)
    assert accept is False and "code-switch regression" in why


def test_acceptance_allows_script_change_when_attempt1_had_little_english():
    before = {"trusted_speech_s": 10.0, "suspect_s": 20.0, "latin_share": 0.03}
    after = {"trusted_speech_s": 30.0, "suspect_s": 2.0, "latin_share": 0.0}
    accept, _ = asr_pipeline._better(before, after)
    assert accept is True


def test_acceptance_rejects_a_retry_that_adds_suspicion():
    before = {"trusted_speech_s": 10.0, "suspect_s": 5.0, "latin_share": 0.0}
    after = {"trusted_speech_s": 20.0, "suspect_s": 9.0, "latin_share": 0.0}
    accept, why = asr_pipeline._better(before, after)
    assert accept is False and "suspect seconds grew" in why


def test_acceptance_still_requires_trusted_text():
    before = {"trusted_speech_s": 10.0, "suspect_s": 20.0, "latin_share": 0.0}
    empty = {"trusted_speech_s": 0.0, "suspect_s": 0.0, "latin_share": 0.0}
    accept, why = asr_pipeline._better(before, empty)
    assert accept is False and "no gain" in why


# ---------------------------------------------------------------------------
# end to end: retry, cap, provenance
# ---------------------------------------------------------------------------

def test_base_loop_is_retried_once_with_large_v3_and_merged(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL),
              "large-v3": ScriptedModel("large-v3", calls, region=GOOD_REGION)}
    t = run(monkeypatch, audio_file, language="en", models=models)

    assert [(c["model"], c["scope"]) for c in calls] == [("base", "full"), ("large-v3", "region")]
    assert calls[1]["condition_on_previous_text"] is False and calls[1]["language"] == "en"
    assert calls[1]["seconds"] == pytest.approx(19.5)   # region 20.0–39.5 s, not the whole file
    assert t.quality.status == "ok", t.quality.reasons
    texts = [s.text for s in t.segments]
    assert LOOP not in texts
    assert "seven eight nine ten eleven twelve thirteen fourteen" in texts
    assert [s.id for s in t.segments] == list(range(len(t.segments)))


def test_large_v3_region_retry_flips_previous_text(monkeypatch, audio_file):
    calls = []
    models = {"large-v3": ScriptedModel("large-v3", calls, full=LOOP_FULL, region=GOOD_REGION)}
    t = run(monkeypatch, audio_file, language="hi", models=models, probes=probes_of(*("hi",) * 8))
    # D30: Hindi attempt 1 is OFF, so its region retry flips to ON.
    assert [c["condition_on_previous_text"] for c in calls] == [False, True]
    assert t.attempts[1].profile == "hi_v1.retry" and t.attempts[1].condition_on_previous_text is True


def test_one_retry_cap_and_still_degraded(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL),
              "large-v3": ScriptedModel("large-v3", calls, region=LOOP_REGION)}  # retry loops again
    t = run(monkeypatch, audio_file, language="en", models=models)

    assert len(calls) == 2                                   # one full decode + one region retry, nothing more
    assert [a.scope for a in t.attempts] == ["full", "region"]
    retry = t.attempts[1]
    assert retry.outcome == "rejected" and retry.quality_status == "still_suspicious"
    assert t.quality.status == "still_degraded"
    assert any("still suspicious" in r for r in t.quality.reasons)
    assert all(s.attempt == 1 for s in t.segments)           # best available (attempt 1) kept


def test_each_region_is_retried_exactly_once(monkeypatch, audio_file):
    calls = []
    full = [raw(1.0, 9.0, LOOP), raw(9.5, 18.5, "india juliet kilo lima mike november oscar papa"),
            raw(21.0, 30.0, "seven eight nine ten eleven twelve thirteen fourteen"),
            raw(30.0, 38.5, "fifteen sixteen seventeen eighteen nineteen twenty"),
            raw(41.0, 50.0, LOOP.replace("la", "na")), raw(50.5, 58.5, "yankee zulu one two three four five six")]
    models = {"base": ScriptedModel("base", calls, full=full),
              "large-v3": ScriptedModel("large-v3", calls, region=[])}
    t = run(monkeypatch, audio_file, language="en", models=models)
    regions = [a.region for a in t.attempts if a.scope == "region"]
    assert len(regions) == 2 and len(set(regions)) == 2
    assert len([c for c in calls if c["scope"] == "region"]) == 2


def test_rejected_retry_keeps_attempt1_text(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL),
              "large-v3": ScriptedModel("large-v3", calls, region=[])}  # retry drops everything
    t = run(monkeypatch, audio_file, language="en", models=models)
    assert t.attempts[1].outcome == "rejected"
    assert [s.text for s in t.segments].count(LOOP) == 2


def test_no_retry_model_marks_still_degraded(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL)}
    t = run(monkeypatch, audio_file, language="en", models=models, available={"base"})
    assert len(calls) == 1 and len(t.attempts) == 1
    assert t.quality.status == "still_degraded"
    assert "not present locally" in t.asr["pipeline"]["retry_skipped"]


def test_clean_first_attempt_is_not_retried(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=CLEAN_FULL)}
    t = run(monkeypatch, audio_file, language="en", models=models)
    assert len(calls) == 1 and t.quality.status == "ok" and len(t.attempts) == 1


def test_provenance_answers_what_produced_this_text_and_why(monkeypatch, audio_file):
    calls = []
    models = {"base": ScriptedModel("base", calls, full=LOOP_FULL),
              "large-v3": ScriptedModel("large-v3", calls, region=GOOD_REGION)}
    t = run(monkeypatch, audio_file, language="en", models=models)

    first, retry = t.attempts
    assert (first.attempt, first.scope, first.model, first.profile) == (1, "full", "base", "en_v1")
    assert first.condition_on_previous_text is True and first.quality_status == "degraded"
    assert (retry.attempt, retry.scope, retry.model, retry.profile) == (2, "region", "large-v3", "en_v1.retry")
    assert retry.region == (20.0, 39.5) and retry.retry_reasons == ["repeated_text"]
    assert retry.outcome == "accepted" and retry.quality_status == "resolved"
    assert [r["text"] for r in retry.replaced] == [LOOP, LOOP]
    assert retry.metrics["before"]["trusted_speech_s"] < retry.metrics["after"]["trusted_speech_s"]
    assert "latin_share" in retry.metrics["before"] and retry.metrics["decision"]

    produced = [s for s in t.segments if s.attempt == 2]
    assert produced and all(t.attempts[s.attempt - 1].region == (20.0, 39.5) for s in produced)
    assert t.asr["pipeline"]["retries"] == 1 and t.asr["pipeline"]["version"] == "adaptive_v1"

    again = Transcript.from_dict(json.loads(json.dumps(t.to_dict(), ensure_ascii=False)))
    assert again.attempts == t.attempts and again.segments == t.segments
    assert t.summary()["attempts"][1]["outcome"] == "accepted"


def test_old_transcripts_without_attempts_still_load():
    data = make_transcript(clean_segments()).to_dict()
    data.pop("attempts"), data.pop("suspicious_spans")
    for s in data["segments"]:
        s.pop("attempt")
    again = Transcript.from_dict(data)
    assert again.attempts == [] and all(s.attempt == 1 for s in again.segments)


# ---------------------------------------------------------------------------
# merge safety
# ---------------------------------------------------------------------------

def test_merge_trims_text_repeated_across_the_boundary():
    kept = [seg(0, 1.0, 9.0, "one two three four five"), seg(1, 41.0, 49.0, "nine ten eleven twelve")]
    region = RetryRegion(20.0, 39.0, [])
    new = [seg(0, 21.0, 26.0, "three four five six seven"),       # repeats the end of kept[0]
           seg(1, 27.0, 38.0, "eight nine ten eleven")]            # repeats the start of kept[1]
    merged, removed = merge_region(kept, region, new, attempt=2)
    texts = [s.text for s in merged]
    assert texts == ["one two three four five", "six seven", "eight", "nine ten eleven twelve"]
    assert removed == []


def test_merge_drops_a_segment_that_fully_duplicates_its_neighbour():
    kept = [seg(0, 1.0, 9.0, "one two three four five")]
    new = [seg(0, 21.0, 25.0, "three four five"), seg(1, 26.0, 30.0, "fresh words here")]
    merged, _ = merge_region(kept, RetryRegion(20.0, 39.0, []), new, attempt=2)
    assert [s.text for s in merged] == ["one two three four five", "fresh words here"]


def test_merge_keeps_timestamps_continuous_and_inside_the_region():
    base = clean_segments()
    base[2], base[3] = seg(2, 21.0, 30.0, LOOP), seg(3, 30.0, 38.5, LOOP)
    region = RetryRegion(20.0, 39.5, [])
    new = [seg(0, 19.2, 29.0, "early start words spill"),          # starts before the region
           seg(1, 28.0, 41.0, "overlapping and late words")]       # overlaps previous, ends after region
    merged, removed = merge_region(base, region, new, attempt=2)

    assert [s.text for s in removed] == [LOOP, LOOP]
    for a, b in zip(merged, merged[1:]):
        assert a.start <= b.start and a.end <= b.start + 1e-9      # ordered, no overlap
    inserted = [s for s in merged if s.attempt == 2]
    assert all(region.start <= s.start and s.end <= region.end for s in inserted)
    assert all(region.start <= w.start and w.end <= region.end for s in inserted for w in s.words)
    assert merged[1].end <= inserted[0].start and inserted[-1].end <= merged[-2].start
    assert [s.id for s in merged] == list(range(len(merged)))


def test_merge_ignores_decoded_segments_outside_the_region():
    base = clean_segments()
    new = [seg(0, 45.0, 50.0, "belongs to another region")]
    merged, removed = merge_region(base, RetryRegion(20.0, 39.5, []), new, attempt=2)
    assert "belongs to another region" not in [s.text for s in merged]
    assert len(merged) == len(base) - len(removed)


# ---------------------------------------------------------------------------
# API wiring (opt-in)
# ---------------------------------------------------------------------------

client = TestClient(app)


def test_mixed_is_only_accepted_by_the_adaptive_pipeline(monkeypatch):
    monkeypatch.setattr(config, "ASR_PROFILE", "legacy")
    resp = client.post("/process", json={"video_url": "https://example.com/v", "language": "mixed"})
    assert resp.status_code == 400 and resp.json() == {"error": "language must be one of: auto, en, hi, ta"}


def test_adaptive_profile_routes_the_pipeline_to_transcribe_adaptive(tmp_path, monkeypatch):
    import ffmpeg as ffmpeg_module
    from tests.fakes import transcript_from_segments

    captured = {}

    def fake_adaptive(path, *, job_id=None, language="auto"):
        captured["language"] = language
        return transcript_from_segments([{"start": 0.0, "end": 5.0, "text": "नमस्ते"}], language="hi")

    def fake_clips(video, selected, job_id=None):
        run_dir = config.OUTPUTS_DIR / "fedcba9876543210fedcba9876543210"
        run_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for i in range(len(selected)):
            p = run_dir / f"{run_dir.name}_clip_{i}.mp4"
            p.write_bytes(b"\x00")
            out.append(str(p))
        return out

    monkeypatch.setattr(config, "ASR_PROFILE", "adaptive_v1")
    with patch("routers.video.get_video_input", new=AsyncMock(return_value=tmp_path / "v.mp4")), \
         patch.object(ffmpeg_module, "probe", return_value={"format": {"duration": "120.0"}}), \
         patch("routers.video.extract_audio", return_value=str(tmp_path / "a.wav")), \
         patch("routers.video.transcribe_adaptive", side_effect=fake_adaptive), \
         patch("routers.video.transcribe_rich", side_effect=AssertionError("rich path must not run")), \
         patch("routers.video.generate_clips", side_effect=fake_clips):
        job_id = client.post("/process", json={"video_url": "https://example.com/v", "language": "mixed"}).json()["job_id"]
        job = client.get(f"/status/{job_id}").json()

    assert job["status"] == "completed", job
    assert captured == {"language": "mixed"}
