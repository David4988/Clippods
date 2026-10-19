"""
Phase 5 tests: sentences, thought units and safe cut points (services/units.py,
services/cut_points.py, services/speech_structure.py) and their pipeline record.
"""
from __future__ import annotations

import json
import os
import random
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from services.cut_points import cuts_outside_silence
from services.speech_regions import silences
from services.speech_structure import SpeechStructure, build_speech_structure
from tests.fakes import transcript_with_words


def build(segments, **kw):
    params = kw.pop("params", None)
    return build_speech_structure(transcript_with_words(segments, **kw), params)


def reasons(units):
    return [u.boundary_reason for u in units]


# ---------------------------------------------------------------------------
# sentences
# ---------------------------------------------------------------------------

def test_english_punctuation_splits_sentences():
    s = build([(0.0, 2.0, "Hello there."), (2.0, 4.0, "How are you?"), (4.0, 6.0, "I am fine")],
              speech=[(0.0, 6.0)])
    assert [x.text for x in s.sentences] == ["Hello there.", "How are you?", "I am fine"]
    assert reasons(s.sentences) == ["punct", "punct", "edge"]
    assert [x.terminal for x in s.sentences] == [".", "?", None]


def test_closing_quote_after_terminal_still_ends_a_sentence():
    s = build([(0.0, 2.0, 'He said "really?"'), (2.0, 3.0, "Yes")], speech=[(0.0, 3.0)])
    assert reasons(s.sentences) == ["punct", "edge"] and s.sentences[0].terminal == "?"


def test_hindi_danda_and_double_danda():
    s = build([(0.0, 3.0, "नमस्ते दोस्तों। आज हम बात करेंगे॥ ठीक है")], language="hi", speech=[(0.0, 3.0)])
    assert [x.text for x in s.sentences] == ["नमस्ते दोस्तों।", "आज हम बात करेंगे॥", "ठीक है"]
    assert [x.terminal for x in s.sentences] == ["।", "॥", None]


def test_tamil_uses_latin_punctuation():
    s = build([(0.0, 3.0, "வணக்கம் நண்பர்களே. இன்று பேசலாம்")], language="ta", speech=[(0.0, 3.0)])
    assert [x.text for x in s.sentences] == ["வணக்கம் நண்பர்களே.", "இன்று பேசலாம்"]


def test_long_vad_silence_ends_a_sentence_without_punctuation():
    segs = [(0.0, 3.0, "one two three"), (3.9, 6.0, "four five six")]
    s = build(segs, speech=[(0.0, 3.0), (3.9, 6.0)])          # 900 ms measured silence
    assert reasons(s.sentences) == ["pause", "edge"]
    assert s.sentences[0].gap_after_ms == 900


def test_word_timing_gap_without_vad_silence_is_not_a_pause():
    segs = [(0.0, 3.0, "one two three"), (3.9, 6.0, "four five six")]
    s = build(segs, speech=[(0.0, 6.0)])                      # VAD hears continuous speech
    assert reasons(s.sentences) == ["edge"]


def test_short_silence_is_not_a_sentence_boundary():
    segs = [(0.0, 3.0, "one two three"), (3.4, 6.0, "four five six")]
    s = build(segs, speech=[(0.0, 3.0), (3.4, 6.0)])          # 400 ms < 700 ms
    assert reasons(s.sentences) == ["edge"]


def test_words_timed_inside_one_silence_do_not_shatter_into_fragments():
    # One trusted segment, 1 s per word. VAD hears silence 2.2-4.8 s, but the
    # decoder timed "so", "um", "yes" into it. Every boundary in there finds the
    # same silence; only the best-overlapping one may use it.
    s = build([(0.0, 8.0, "Hello there so um yes we continue here")], speech=[(0.0, 2.2), (4.8, 8.0)])
    assert [x.text for x in s.sentences] == ["Hello there so", "um yes we continue here"]
    assert s.stats["words_inside_cut_silences"] == 3
    assert [c.kind for c in s.cut_points] == ["thought"]


def test_untrusted_segments_are_excluded_and_break_units():
    segs = [(0.0, 3.0, "Real words here"), (3.0, 9.0, "la la la la la la la la la"), (9.0, 12.0, "More real words")]
    s = build(segs, speech=[(0.0, 12.0)], suspect=(1,))
    assert "la" not in [w.text for w in s.words]
    assert reasons(s.sentences) == ["untrusted", "edge"]
    assert s.stats["excluded_segments"] == 1 and s.stats["excluded_words"] == 9
    assert all(t.end <= 3.0 or t.start >= 9.0 for t in s.thoughts)   # nothing spans the loop


# ---------------------------------------------------------------------------
# thought units
# ---------------------------------------------------------------------------

def test_thoughts_merge_short_gaps_and_split_on_long_gaps_and_questions():
    segs = [(0.0, 2.0, "First point."), (2.3, 4.0, "Same thought."),      # 300 ms → merge
            (5.5, 7.0, "New thought?"),                                    # 1500 ms → split before
            (7.1, 9.0, "An answer.")]                                      # after a question → split
    s = build(segs, speech=[(0.0, 2.0), (2.3, 4.0), (5.5, 7.0), (7.1, 9.0)])
    assert [t.text for t in s.thoughts] == ["First point. Same thought.", "New thought?", "An answer."]
    assert reasons(s.thoughts) == ["pause", "question", "edge"]


def test_long_thought_splits_at_its_largest_internal_silence():
    segs = [(0.0, 4.0, "One."), (4.3, 8.0, "Two."), (9.0, 13.0, "Three."), (13.5, 17.0, "Four.")]
    speech = [(0.0, 4.0), (4.3, 8.0), (9.0, 13.0), (13.5, 17.0)]           # gaps 300, 1000, 500 ms
    s = build(segs, speech=speech, params={"thought_max_s": 10.0})
    assert [t.text for t in s.thoughts] == ["One. Two.", "Three. Four."]
    assert reasons(s.thoughts) == ["max_length", "edge"]


# ---------------------------------------------------------------------------
# cut points
# ---------------------------------------------------------------------------

def test_cut_point_sits_inside_the_silence_with_pre_and_post_roll():
    s = build([(0.0, 2.0, "Hello there."), (2.8, 5.0, "Next one.")], speech=[(0.0, 2.0), (2.8, 5.0)])
    [cut] = [c for c in s.cut_points if c.kind != "edge"]
    assert (cut.gap_start, cut.gap_end, cut.gap_ms) == (2.0, 2.8, 800)
    assert cut.cut_out == pytest.approx(2.35) and cut.cut_in == pytest.approx(2.55)
    assert cut.kind == "sentence" and cut.after_word == 1 and cut.before_word == 2
    assert s.sentences[0].end_cut == cut.id and s.sentences[1].start_cut == cut.id


def test_sentence_end_in_continuous_speech_is_unsafe():
    s = build([(0.0, 2.0, "Hello there."), (2.0, 4.0, "Next one.")], speech=[(0.0, 4.0)])
    assert s.sentences[0].end_cut is None                     # punctuation, but no silence
    assert s.stats["sentences"]["boundaries"] == {"inner_boundaries": 1, "with_safe_cut": 0, "safe_share": 0.0}


def test_silence_below_the_minimum_gives_no_cut():
    s = build([(0.0, 2.0, "Hello there."), (2.1, 4.0, "Next one.")], speech=[(0.0, 2.0), (2.1, 4.0)])
    assert [c for c in s.cut_points if c.kind != "edge"] == []


def test_run_edges_next_to_untrusted_text_allow_one_side_only():
    segs = [(0.0, 3.0, "Real words here"), (4.0, 9.0, "la la la la la la la la la"), (10.0, 13.0, "More real words")]
    s = build(segs, speech=[(0.0, 3.0), (4.0, 9.0), (10.0, 13.0)], suspect=(1,))
    after_first = next(c for c in s.cut_points if c.after_word == 2)
    before_second = next(c for c in s.cut_points if c.before_word == 3)
    assert after_first.cut_out is not None and after_first.cut_in is None and after_first.adjacent_untrusted
    assert before_second.cut_in is not None and before_second.cut_out is None and before_second.adjacent_untrusted


def test_random_transcripts_never_put_a_cut_outside_measured_silence():
    rng = random.Random(7)
    vocab = ["word", "talk.", "why?", "yes!", "so", "and"]
    for _ in range(60):
        t, segs, speech = 0.0, [], []
        for _ in range(rng.randint(3, 15)):
            t += rng.choice([0.0, 0.05, 0.2, 0.5, 0.9, 1.6])
            length = rng.uniform(0.5, 6.0)
            segs.append((round(t, 3), round(t + length, 3),
                         " ".join(rng.choice(vocab) for _ in range(rng.randint(1, 8)))))
            speech.append((round(t, 3), round(t + length, 3)))
            t += length
        suspect = tuple(i for i in range(len(segs)) if rng.random() < 0.15)
        s = build(segs, speech=speech, suspect=suspect, params={"thought_max_s": rng.choice([5.0, 90.0])})
        assert cuts_outside_silence(s.cut_points, silences(speech, segs[-1][1])) == []
        for units in (s.sentences, s.thoughts):
            assert all(a.end <= b.start for a, b in zip(units, units[1:]))
            assert all(a.word_range[1] + 1 == b.word_range[0] for a, b in zip(units, units[1:]))
        times = [c.gap_start for c in s.cut_points]
        assert times == sorted(times)


# ---------------------------------------------------------------------------
# fallbacks, determinism, round trip
# ---------------------------------------------------------------------------

def test_segment_only_transcripts_use_segments_as_pieces():
    s = build([(0.0, 2.0, "Hello there."), (2.8, 5.0, "Next one")], speech=[(0.0, 2.0), (2.8, 5.0)],
              with_words=False)
    assert s.timing_source == "segment"
    assert [x.text for x in s.sentences] == ["Hello there.", "Next one"]
    assert any(c.kind == "sentence" for c in s.cut_points)


def test_without_vad_there_are_no_cut_points_or_pause_boundaries():
    s = build([(0.0, 3.0, "one two three"), (3.9, 6.0, "four five six")], speech=None)
    assert s.vad is False and s.cut_points == [] and reasons(s.sentences) == ["edge"]


def test_structure_is_deterministic_and_round_trips():
    segs = [(0.0, 2.0, "Hello there."), (2.8, 5.0, "How are you?"), (5.2, 7.0, "Fine")]
    t = transcript_with_words(segs, speech=[(0.0, 2.0), (2.8, 5.0), (5.2, 7.0)])
    first, second = build_speech_structure(t), build_speech_structure(t)
    assert first.to_dict() == second.to_dict()
    again = SpeechStructure.from_dict(json.loads(json.dumps(first.to_dict(), ensure_ascii=False)))
    assert again == first
    assert set(first.summary()) == {"schema", "version", "language", "timing_source", "vad",
                                     "audio_duration", "params", "stats"}


def test_unknown_schema_is_rejected():
    with pytest.raises(ValueError, match="unsupported speech structure schema"):
        SpeechStructure.from_dict({"schema": "nope"})


# ---------------------------------------------------------------------------
# pipeline record (clip selection unchanged)
# ---------------------------------------------------------------------------

client = TestClient(app)


def _run_job(tmp_path, transcript, extra_patches=()):
    import ffmpeg as ffmpeg_module

    def fake_clips(video, selected, job_id=None):
        run_dir = config.OUTPUTS_DIR / os.urandom(16).hex()
        run_dir.mkdir(parents=True)
        paths = []
        for i, _ in enumerate(selected):
            p = run_dir / f"{run_dir.name}_clip_{i}.mp4"
            p.write_bytes(b"\x00" * 32)
            paths.append(str(p))
        return paths

    patches = [
        patch("routers.video.get_video_input", new=AsyncMock(return_value=tmp_path / "video.mp4")),
        patch.object(ffmpeg_module, "probe", return_value={"format": {"duration": "120.0"}}),
        patch("routers.video.extract_audio", return_value=str(tmp_path / "audio.wav")),
        patch("routers.video.transcribe_rich", return_value=transcript),
        patch("routers.video.generate_clips", side_effect=fake_clips),
        *extra_patches,
    ]
    for p in patches:
        p.start()
    try:
        job_id = client.post("/process", json={"video_url": "https://example.com/v"}).json()["job_id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            job = client.get(f"/status/{job_id}").json()
            if job["status"] in ("completed", "error", "cancelled"):
                return job
            time.sleep(0.05)
        raise TimeoutError(job_id)
    finally:
        for p in patches:
            p.stop()


def _segments(n=12):
    return [(i * 10.0, i * 10.0 + 9.0, f"This is sentence number {i} in the talk.") for i in range(n)]


def test_pipeline_saves_speech_structure_and_summary(tmp_path):
    segs = _segments()
    transcript = transcript_with_words(segs, speech=[(a, b) for a, b, _ in segs], duration=120.0)
    job = _run_job(tmp_path, transcript)

    assert job["status"] == "completed", job
    assert job.get("warnings", []) == []
    run_dir = config.OUTPUTS_DIR / job["run_uuid"]
    analysis = json.loads((run_dir / "analysis.json").read_text(encoding="utf-8"))
    saved = SpeechStructure.from_dict(json.loads((run_dir / "speech_structure.json").read_text(encoding="utf-8")))
    assert analysis["speech_structure"] == json.loads(json.dumps(saved.summary()))
    assert saved.stats["sentences"]["count"] == 12 and saved.cut_points
    stages = [s["stage"] for s in analysis["pipeline"]["stages"]]
    assert stages.index("transcribe") < stages.index("speech_structure") < stages.index("select_segments")


def test_structure_failure_warns_but_the_job_still_completes(tmp_path):
    segs = _segments()
    transcript = transcript_with_words(segs, speech=[(a, b) for a, b, _ in segs], duration=120.0)
    boom = patch("routers.video.build_speech_structure", side_effect=RuntimeError("boom"))
    job = _run_job(tmp_path, transcript, extra_patches=(boom,))

    assert job["status"] == "completed", job
    assert any("Speech structure was not computed: RuntimeError: boom" in w for w in job["warnings"])
    run_dir = config.OUTPUTS_DIR / job["run_uuid"]
    analysis = json.loads((run_dir / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["speech_structure"] == {"error": "RuntimeError: boom"}
    assert analysis["pipeline"]["failed_stage"] is None
    assert not (run_dir / "speech_structure.json").exists()
