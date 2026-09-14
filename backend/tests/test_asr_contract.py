"""
ASR rich-contract tests: transcript contract, speech regions, quality flags,
language handling, transcribe_rich behaviour and the API language option.

Faster-Whisper decoding is mocked; Silero VAD runs for real on synthetic audio.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import config
import job_manager
from main import app
from services import speech_regions, transcript_quality, transcription
from services.transcript import (
    SCHEMA, LanguageInfo, LanguageProbe, SpeechRegions, Transcript, TranscriptSegment, Word,
)
from tests.fakes import transcript_from_segments

client = TestClient(app)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def seg(i, start, end, text, *, logprob=-0.2, no_speech=0.01, cr=1.3, temp=0.0, words=None):
    return TranscriptSegment(id=i, start=start, end=end, text=text, avg_logprob=logprob,
                             compression_ratio=cr, no_speech_prob=no_speech, temperature=temp,
                             token_count=10, words=words)


def regions(*spans, duration=60.0):
    return SpeechRegions(method="test", params={}, regions=list(spans), audio_duration=duration)


def lang(language="en", mode="auto", probability=0.99, probes=()):
    return LanguageInfo(mode=mode, language=language, probability=probability, top=[(language, probability)],
                        probes=list(probes), uncertain=False, reasons=[])


def flags_of(segment_list, language="en", duration=60.0, speech=None):
    transcript_quality.flag_segments(segment_list, language, duration, speech)
    return [s.flags for s in segment_list]


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------

def test_transcript_round_trips_through_json():
    words = [Word(0.5, 0.9, " नमस्ते", 0.93), Word(1.0, 1.4, " दोस्तों", 0.88)]
    segments = [seg(0, 0.4, 1.5, "नमस्ते दोस्तों।", words=words)]
    speech = regions((0.4, 1.5), duration=2.0)
    info = lang("hi", probes=[LanguageProbe(0.4, 1.5, "hi", 0.97)])
    transcript_quality.flag_segments(segments, "hi", 2.0, speech)
    t = Transcript(schema=SCHEMA, asr={"profile": "rich_v1"}, audio_duration=2.0, language=info,
                   segments=segments, speech_regions=speech,
                   quality=transcript_quality.summarise(segments, info, speech), timings={"decode_s": 1.0})

    payload = json.loads(json.dumps(t.to_dict(), ensure_ascii=False))
    again = Transcript.from_dict(payload)
    assert again == t
    assert again.legacy_segments() == [{"start": 0.4, "end": 1.5, "text": "नमस्ते दोस्तों।"}]
    assert again.summary()["speech_regions"]["count"] == 1


def test_unknown_schema_is_rejected():
    with pytest.raises(ValueError, match="unsupported transcript schema"):
        Transcript.from_dict({"schema": "clippods-transcript/0"})


# ---------------------------------------------------------------------------
# speech regions (real Silero VAD)
# ---------------------------------------------------------------------------

def test_silence_has_no_speech_regions():
    result = speech_regions.detect_speech_regions(np.zeros(16000 * 3, dtype=np.float32))
    assert result.regions == [] and result.audio_duration == 3.0
    assert result.params == speech_regions.SPEECH_REGION_PARAMS
    assert result.params["speech_pad_ms"] == 0  # measurements are unpadded


def test_overlap_and_contains_helpers():
    spans = [(1.0, 2.0), (3.0, 5.0)]
    assert speech_regions.overlap_seconds(0.0, 10.0, spans) == pytest.approx(3.0)
    assert speech_regions.overlap_seconds(1.5, 3.5, spans) == pytest.approx(1.0)
    assert speech_regions.contains(2.1, spans, tolerance=0.2) and not speech_regions.contains(2.5, spans)


# ---------------------------------------------------------------------------
# quality flags
# ---------------------------------------------------------------------------

def test_clean_segment_has_no_flags():
    speech = regions((0.0, 5.0))
    [flags] = flags_of([seg(0, 0.2, 4.8, "A perfectly ordinary sentence.")], speech=speech)
    assert flags == []


def test_repetition_loops_are_hallucination_suspects():
    segments = [seg(0, 0, 2, "Thank you for watching."), seg(1, 5, 7, "Thank you for watching."),
                seg(2, 9, 20, "go go go go go go go go go go go go")]
    speech = regions((0, 20))
    flags_of(segments, speech=speech)
    assert "repeated_text" in segments[1].flags and segments[1].hallucination_suspect
    assert "repeated_text" in segments[2].flags
    assert not segments[1].usable


def test_timing_problems_do_not_discard_real_text():
    """EV-2.1: correct text with an end timestamp past the audio is a timing suspect only."""
    s = seg(0, 118.56, 127.92, "Distribution beats product, almost every time.")
    flags_of([s], duration=122.5, speech=regions((118.6, 121.2), duration=122.5))
    assert {"timestamp_beyond_audio", "outside_speech"} <= set(s.flags)
    assert s.timing_suspect and not s.hallucination_suspect and s.usable


def test_text_over_measured_silence_is_a_hallucination_suspect():
    s = seg(0, 10.0, 14.0, "Subscribe to my channel.")
    flags_of([s], speech=regions((0.0, 2.0), (30.0, 40.0)))
    assert "no_speech_under_text" in s.flags and s.hallucination_suspect


def test_words_outside_speech_are_marked_individually():
    words = [Word(0.1, 0.4, "in", 0.9), Word(3.0, 3.3, "out", 0.9), Word(4.0, 4.3, "out", 0.9)]
    s = seg(0, 0.1, 4.3, "in out out", words=words)
    flags_of([s], speech=regions((0.0, 1.0)))
    assert [w.in_speech for w in words] == [True, False, False]
    assert "words_outside_speech" in s.flags


def test_whisper_silence_rule_and_low_confidence_flags():
    s = seg(0, 0, 3, "hmm", logprob=-1.4, no_speech=0.8, temp=0.6,
            words=[Word(0, 1, "hmm", 0.2)])
    flags_of([s])
    assert {"likely_no_speech", "high_no_speech_prob", "low_avg_logprob",
            "temperature_fallback", "low_word_probability"} <= set(s.flags)
    assert s.hallucination_suspect and s.low_confidence


def test_script_mismatch_detects_romanised_and_urdu_output_for_hindi():
    """EV-2.3: base emitted Hindi as Latin transliteration and as Urdu script."""
    romanised = seg(0, 0, 3, "Ustad Bismillah Khan, Bharatiya Sangeet")
    urdu = seg(1, 3, 6, "استاد بسمل لاخان بھارتیہ سنگیت ہی نہیں")
    devanagari = seg(2, 6, 9, "उस्ताद बिस्मिल्लाह खान, भारतीय संगीत")
    flags_of([romanised, urdu, devanagari], language="hi")
    assert "script_mismatch" in romanised.flags and "script_mismatch" in urdu.flags
    assert "script_mismatch" not in devanagari.flags
    assert urdu.scripts == {"arabic": 1.0}


def test_mixed_script_is_informational():
    s = seg(0, 0, 3, "ஆனால் இந்த product launch நல்லா போச்சு")
    flags_of([s], language="ta")
    assert "mixed_script" in s.flags and not s.hallucination_suspect


def test_compression_ratio_flag_ignores_non_latin_scripts():
    """EV-2.4: clean Tamil text scores > 2.4 on Whisper's byte-level ratio."""
    tamil = seg(0, 0, 5, "அதற்குத் தகுந்தபடி, ஏதாவது கொஞ்சம் பேசி", cr=2.9)
    english = seg(1, 5, 9, "the same words the same words the", cr=2.9)
    flags_of([tamil, english], language="ta")
    assert "high_compression_ratio" not in tamil.flags and not tamil.hallucination_suspect
    assert "high_compression_ratio" in english.flags


# ---------------------------------------------------------------------------
# language assessment & transcript status
# ---------------------------------------------------------------------------

def test_probe_disagreement_makes_language_uncertain_without_overriding_it():
    info = lang("hi", probes=[LanguageProbe(0, 30, "hi", 0.8), LanguageProbe(40, 57, "ta", 0.87)])
    transcript_quality.assess_language(info)
    assert info.uncertain and info.language == "hi"
    assert "disagree" in info.reasons[0]


@pytest.mark.parametrize("info, fragment", [
    (lang("hi", probability=0.55), "detection probability 0.55"),
    (lang("ur", probability=0.9), "not one of"),
    (lang("en", probes=[LanguageProbe(0, 30, "ta", 0.9), LanguageProbe(30, 60, "ta", 0.9)]), "favour 'ta'"),
    (lang("ta", mode="ta", probability=None, probes=[LanguageProbe(0, 30, "hi", 0.9)]), "forced to 'ta'"),
])
def test_language_uncertainty_reasons(info, fragment):
    transcript_quality.assess_language(info)
    assert info.uncertain and any(fragment in r for r in info.reasons)


def test_confident_consistent_language_is_certain():
    info = lang("ta", probability=0.93, probes=[LanguageProbe(0, 30, "ta", 0.9)] * 3)
    transcript_quality.assess_language(info)
    assert not info.uncertain and info.reasons == []


def test_status_degrades_on_low_coverage_and_suspects():
    speech = regions((0, 40))
    segments = [seg(0, 0, 5, "Real speech here."), seg(1, 5, 7, "Real speech here.")]
    info = lang()
    transcript_quality.flag_segments(segments, "en", 60.0, speech)
    quality = transcript_quality.summarise(segments, info, speech)
    assert quality.status == "degraded"
    assert quality.hallucination_suspect_segments == 1
    assert quality.speech_coverage == pytest.approx(5 / 40, abs=1e-3)
    assert any("cover" in r for r in quality.reasons) and any("hallucination" in r for r in quality.reasons)


def test_measured_speech_without_text_is_degraded_not_failed():
    quality = transcript_quality.summarise([], lang(), regions((0, 30)))
    assert quality.status == "degraded" and "no text was transcribed" in quality.reasons[-1]


# ---------------------------------------------------------------------------
# transcribe_rich
# ---------------------------------------------------------------------------

class FakeModel:
    """Records decode kwargs; yields faster-whisper-shaped segments."""

    def __init__(self, raw_segments, info_language="hi", probe_language="hi"):
        self.raw_segments = raw_segments
        self.info_language = info_language
        self.probe_language = probe_language
        self.transcribe_calls = []
        self.probe_calls = 0

    def transcribe(self, audio, **kwargs):
        self.transcribe_calls.append((audio, kwargs))
        info = SimpleNamespace(language=kwargs.get("language") or self.info_language, language_probability=0.91,
                               all_language_probs=[(self.info_language, 0.91), ("ur", 0.05)], duration=20.0,
                               duration_after_vad=15.0, transcription_options=None, vad_options=None)
        return iter(self.raw_segments), info

    def detect_language(self, audio=None, **kwargs):
        self.probe_calls += 1
        return self.probe_language, 0.88, []


def raw(start, end, text, words=None):
    return SimpleNamespace(start=start, end=end, text=text, avg_logprob=-0.3, compression_ratio=1.5,
                           no_speech_prob=0.02, temperature=0.0, tokens=[1, 2, 3], words=words)


@pytest.fixture()
def audio_file(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF....WAVEfmt ")
    return str(p)


@pytest.fixture()
def fake_audio(monkeypatch):
    """Decoded audio: 20 s of silence; VAD mocked to a known region."""
    import faster_whisper
    monkeypatch.setattr(faster_whisper, "decode_audio", lambda *a, **k: np.zeros(16000 * 20, dtype=np.float32))
    monkeypatch.setattr(speech_regions, "detect_speech_regions",
                        lambda audio, params=None: regions((1.0, 9.0), (11.0, 19.0), duration=20.0))


def test_rich_profile_keeps_words_metadata_and_measurements(audio_file, fake_audio, monkeypatch):
    words = [SimpleNamespace(start=1.2, end=1.6, word=" नमस्ते", probability=0.9),
             SimpleNamespace(start=9.5, end=10.2, word=" दोस्तों", probability=0.4)]
    model = FakeModel([raw(1.1, 10.3, " नमस्ते दोस्तों।", words), raw(None, 12.0, "dropped")])
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)

    t = transcription.transcribe_rich(audio_file, profile="rich_v1", language_mode="auto")

    _, kwargs = model.transcribe_calls[0]
    # rich_v1 resolves the language before decoding (script-aware fallback).
    assert kwargs["task"] == "transcribe" and kwargs["language"] == "hi"
    assert kwargs["word_timestamps"] is True and kwargs["vad_filter"] is True
    assert t.language.language == "hi" and t.language.probability == 0.88
    assert t.asr["language_detection"] == "pre-decode detect_language on decoder input"
    assert model.probe_calls >= 2  # probes + pre-decode detection
    [s] = t.segments
    assert (s.avg_logprob, s.compression_ratio, s.no_speech_prob, s.token_count) == (-0.3, 1.5, 0.02, 3)
    assert [w.text for w in s.words] == [" नमस्ते", " दोस्तों"]
    assert [w.in_speech for w in s.words] == [True, False]
    assert t.speech_regions.regions == [(1.0, 9.0), (11.0, 19.0)]
    assert t.asr["profile"] == "rich_v1" and t.asr["task"] == "transcribe"
    assert set(t.timings) >= {"decode_audio_s", "speech_regions_s", "language_probes_s", "decode_s", "total_s"}


def test_forced_language_is_passed_to_the_decoder(audio_file, fake_audio, monkeypatch):
    model = FakeModel([raw(1.0, 5.0, " வணக்கம்")], info_language="ta", probe_language="ta")
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    t = transcription.transcribe_rich(audio_file, profile="legacy", language_mode="ta")
    _, kwargs = model.transcribe_calls[0]
    assert kwargs["language"] == "ta" and kwargs["word_timestamps"] is False
    assert t.language.mode == "ta" and t.language.probability is None and t.language.top == []
    assert t.segments[0].words is None


def test_invalid_language_and_profile_are_rejected(audio_file):
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe_rich(audio_file, language_mode="fr")
    assert exc.value.status_code == 400
    with pytest.raises(ValueError, match="unknown ASR profile"):
        transcription.get_profile("large_everything")


def test_legacy_wrapper_decodes_the_path_exactly_as_before(audio_file, monkeypatch):
    import faster_whisper

    def must_not_decode(*a, **k):
        raise AssertionError("legacy transcribe() must not decode audio itself")

    monkeypatch.setattr(faster_whisper, "decode_audio", must_not_decode)
    model = FakeModel([raw(0.0, 1.5, " Hello "), raw(1.5, 3.0, "world")], info_language="en")
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)

    result = transcription.transcribe(audio_file)
    audio_arg, kwargs = model.transcribe_calls[0]
    assert audio_arg == audio_file
    assert kwargs == {"task": "transcribe", "language": None, "beam_size": 5, "word_timestamps": False,
                      "vad_filter": False, "vad_parameters": None, "condition_on_previous_text": True,
                      "language_detection_segments": 1}
    assert result == {"segments": [{"start": 0.0, "end": 1.5, "text": "Hello"},
                                   {"start": 1.5, "end": 3.0, "text": "world"}]}


def test_cancellation_before_decoding(audio_file, fake_audio, monkeypatch):
    model = FakeModel([raw(0, 1, "x")])
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="transcribing")
    job_manager.cancel_job(job_id)
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe_rich(audio_file, job_id=job_id, profile="rich_v1")
    assert exc.value.status_code == 499 and model.transcribe_calls == []


def test_undecodable_audio_is_a_real_failure(audio_file, monkeypatch):
    import faster_whisper
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: FakeModel([]))
    monkeypatch.setattr(faster_whisper, "decode_audio", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad wav")))
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe_rich(audio_file, profile="rich_v1")
    assert exc.value.status_code == 502 and "bad wav" in exc.value.detail


# ---------------------------------------------------------------------------
# pipeline & API
# ---------------------------------------------------------------------------

def test_api_rejects_unknown_language_with_a_clear_error():
    resp = client.post("/process", json={"video_url": "https://example.com/v", "language": "french"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "language must be one of: auto, en, hi, ta"}
    upload = client.post("/process/upload", files={"file": ("v.mp4", b"\x00" * 64, "video/mp4")},
                         data={"language": "xx"})
    assert upload.status_code == 400


def test_pipeline_passes_language_and_profile_and_saves_transcript(tmp_path, monkeypatch):
    import ffmpeg as ffmpeg_module
    captured = {}
    fake = transcript_from_segments([{"start": 0.0, "end": 5.0, "text": "வணக்கம்"}], language="ta")

    def fake_transcribe(path, *, job_id=None, profile="legacy", language_mode="auto"):
        captured.update(profile=profile, language_mode=language_mode)
        return fake

    def fake_clips(video, selected, job_id=None):
        run_dir = config.OUTPUTS_DIR / "abcdef0123456789abcdef0123456789"
        run_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for i in range(len(selected)):
            p = run_dir / f"{run_dir.name}_clip_{i}.mp4"
            p.write_bytes(b"\x00")
            out.append(str(p))
        return out

    monkeypatch.setattr(config, "ASR_PROFILE", "rich_v1")
    with patch("routers.video.get_video_input", new=AsyncMock(return_value=tmp_path / "v.mp4")), \
         patch.object(ffmpeg_module, "probe", return_value={"format": {"duration": "120.0"}}), \
         patch("routers.video.extract_audio", return_value=str(tmp_path / "a.wav")), \
         patch("routers.video.transcribe_rich", side_effect=fake_transcribe), \
         patch("routers.video.generate_clips", side_effect=fake_clips):
        job_id = client.post("/process", json={"video_url": "https://example.com/v", "language": "ta"}).json()["job_id"]
        job = client.get(f"/status/{job_id}").json()

    assert job["status"] == "completed", job
    assert captured == {"profile": "rich_v1", "language_mode": "ta"}
    run_dir = config.OUTPUTS_DIR / job["run_uuid"]
    analysis = json.loads((run_dir / "analysis.json").read_text(encoding="utf-8"))
    saved = Transcript.from_dict(json.loads((run_dir / "transcript.json").read_text(encoding="utf-8")))
    assert analysis["asr"]["language"]["language"] == "ta"
    assert saved.legacy_segments() == [{"start": 0.0, "end": 5.0, "text": "வணக்கம்"}]


def test_asr_profile_setting_is_validated(tmp_path):
    import os
    import subprocess
    import sys
    env = {**os.environ, "ASR_PROFILE": "huge", "CLIPPODS_DISABLE_DOTENV": "1"}
    out = subprocess.run([sys.executable, "-c", "import config"], cwd=Path(__file__).resolve().parents[1],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode != 0 and "ASR_PROFILE must be" in out.stderr


def test_only_non_default_fallback_settings_reach_the_decoder(audio_file, fake_audio, monkeypatch):
    from dataclasses import replace
    model = FakeModel([raw(1.0, 5.0, " வணக்கம்")], info_language="ta")
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    transcription.transcribe_rich(audio_file, profile="rich_v1", language_mode="ta")
    assert "temperature" not in model.transcribe_calls[-1][1]

    no_fallback = replace(transcription.PROFILES["rich_v1"], name="t", temperature=(0.0,),
                          compression_ratio_threshold=None)
    t = transcription.transcribe_rich(audio_file, profile=no_fallback, language_mode="ta")
    kwargs = model.transcribe_calls[-1][1]
    assert kwargs["temperature"] == [0.0] and kwargs["compression_ratio_threshold"] is None
    assert t.asr["settings"]["temperature"] == (0.0,)



# ---------------------------------------------------------------------------
# script-aware compression-ratio fallback (rich_v1 only)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("detected, expect_override", [("ta", True), ("hi", True), ("en", False)])
def test_rich_v1_disables_compression_trigger_only_for_non_latin_script_languages(
        audio_file, fake_audio, monkeypatch, detected, expect_override):
    model = FakeModel([raw(1.0, 5.0, " text")], info_language=detected, probe_language=detected)
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    t = transcription.transcribe_rich(audio_file, profile="rich_v1", language_mode="auto")
    kwargs = model.transcribe_calls[-1][1]
    assert kwargs["language"] == detected
    if expect_override:
        assert "compression_ratio_threshold" in kwargs and kwargs["compression_ratio_threshold"] is None
        assert t.asr["decode_overrides"] == {"compression_ratio_threshold": None}
    else:
        assert "compression_ratio_threshold" not in kwargs and t.asr["decode_overrides"] == {}
    assert "temperature" not in kwargs  # the log-probability fallback path stays at defaults


def test_rich_v1_forced_tamil_overrides_without_extra_detection(audio_file, fake_audio, monkeypatch):
    model = FakeModel([raw(1.0, 5.0, " வணக்கம்")], info_language="ta", probe_language="ta")
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    probes_only = replace_profile(language_probes=0)
    t = transcription.transcribe_rich(audio_file, profile=probes_only, language_mode="ta")
    kwargs = model.transcribe_calls[-1][1]
    assert kwargs["language"] == "ta" and kwargs["compression_ratio_threshold"] is None
    assert model.probe_calls == 0 and t.asr["language_detection"] == "forced"


def test_legacy_profile_keeps_whisper_thresholds_for_tamil(audio_file, fake_audio, monkeypatch):
    model = FakeModel([raw(1.0, 5.0, " வணக்கம்")], info_language="ta", probe_language="ta")
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: model)
    for mode in ("auto", "ta"):
        transcription.transcribe_rich(audio_file, profile="legacy", language_mode=mode)
        kwargs = model.transcribe_calls[-1][1]
        assert "compression_ratio_threshold" not in kwargs
        assert kwargs["language"] == (None if mode == "auto" else "ta")
    assert transcription.PROFILES["legacy"].script_aware_compression is False


def replace_profile(**changes):
    from dataclasses import replace
    return replace(transcription.PROFILES["rich_v1"], name="test", **changes)
