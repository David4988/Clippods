"""
Phase 6 tests: the boundary_v1 clip picker (services/selection/*), loudness
features (services/audio_features.py), the engine registry, pipeline wiring and
harness metrics.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from evaluation.engines import parse_engine_spec, run_engine
from evaluation.metrics import selection_metrics
from main import app
from services.audio_features import loudness_envelope
from services.selection import boundary_v1, lexicons
from services.selection.ranker import similarity, trigrams
from services.selection.registry import SelectionInput, run
from services.speech_regions import silences
from services.speech_structure import build_speech_structure
from tests.fakes import transcript_with_words

P = boundary_v1.PARAMS
SYLLABLES = ["ka", "lo", "mi", "re", "su", "ta", "ve", "no", "pa", "di", "go", "be", "zu", "fy", "qu"]


def words(rng: random.Random, n: int) -> str:
    return " ".join("".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 4))) for _ in range(n))


def talk(n: int = 40, sentence_s: float = 4.0, gap_s: float = 0.8, seed: int = 1, *, terminal=".",
         texts=None, language="en", suspect=(), extra_gap_every=0, extra_gap_s=0.0):
    """Sentences of distinct nonsense words separated by measured silences."""
    rng = random.Random(seed)
    segs, speech, t = [], [], 0.5
    for i in range(n):
        text = texts[i] if texts else words(rng, 8).capitalize() + terminal
        segs.append((round(t, 3), round(t + sentence_s, 3), text))
        speech.append((round(t, 3), round(t + sentence_s, 3)))
        t += sentence_s + gap_s + (extra_gap_s if extra_gap_every and (i + 1) % extra_gap_every == 0 else 0)
    return transcript_with_words(segs, speech=speech, duration=round(t + 0.5, 3), language=language,
                                 suspect=suspect)


def pick(transcript, count=5, audio_path=None, params=None):
    structure = build_speech_structure(transcript)
    clips, analysis = boundary_v1.select(transcript, structure, transcript.audio_duration, count,
                                         audio_path=audio_path, params=params)
    return clips, analysis, structure


# ---------------------------------------------------------------------------
# clip validity
# ---------------------------------------------------------------------------

def test_clips_start_and_end_on_sentence_boundary_cuts_inside_silence():
    t = talk()
    clips, analysis, structure = pick(t)
    assert len(clips) == 5 and analysis["shortfall_reason"] is None
    starts_at = {s.word_range[0] for s in structure.sentences}
    ends_at = {s.word_range[1] for s in structure.sentences}
    cut = {c.id: c for c in structure.cut_points}
    sil = silences(t.speech_regions.regions, t.audio_duration)
    for c in clips:
        s, e = cut[c["start_cut"]], cut[c["end_cut"]]
        assert c["start"] == s.cut_in and s.before_word in starts_at
        assert c["end"] == e.cut_out and e.after_word in ends_at
        assert all(any(a - 1e-6 <= x <= b + 1e-6 for a, b in sil) for x in (c["start"], c["end"]))
        assert P["hard_min_s"] <= c["end"] - c["start"] <= P["hard_max_s"]


def test_no_overlaps_no_duplicates_and_target_durations_when_material_allows():
    clips, analysis, _ = pick(talk())
    spans = sorted((c["start"], c["end"]) for c in clips)
    assert len(set(spans)) == len(spans)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    assert all(c["tier"] == 1 and P["target_min_s"] <= c["end"] - c["start"] <= P["target_max_s"]
               for c in clips)
    assert [c["rank"] for c in clips] == list(range(5))
    assert analysis["tiers"][0]["added"] == 5


def test_short_input_returns_fewer_clips_with_a_reason():
    clips, analysis, _ = pick(talk(n=6))                       # ~29 s of talk: room for ~3 clips
    assert 0 < len(clips) < 5
    assert "instead of 5" in analysis["shortfall_reason"]


def test_too_short_for_any_clip_says_so():
    clips, analysis, _ = pick(talk(n=1))                       # one 4 s sentence: under the hard minimum
    assert clips == [] and analysis["shortfall_reason"].startswith("no candidate clips")


def test_tiers_relax_in_order_when_the_target_cannot_be_met():
    # Candidates are ~9.4 s long here, so nothing fits an 11.0–11.5 s target.
    clips, analysis, _ = pick(talk(), params={"target_min_s": 11.0, "target_max_s": 11.5})
    tiers = [c["tier"] for c in clips]
    assert tiers == sorted(tiers) and max(tiers) == 4
    # Greedy packing on a 3-minute input may fit fewer than 5; then the shortfall is explained.
    assert len(clips) == 5 or "instead of 5" in analysis["shortfall_reason"]
    assert [d["tier"] for d in analysis["tiers"]] == sorted({d["tier"] for d in analysis["tiers"]})


def test_clip_stops_on_a_question_rather_than_running_past_it():
    rng = random.Random(3)
    # 18 short sentences (~50 s): one thought in the plain version, so only the question changes
    # structure. 2 s sentences let a clip end on the question or one sentence later (8.2 / 11 s).
    base = [words(rng, 5).capitalize() for _ in range(18)]
    plain = talk(n=18, sentence_s=2.0, texts=[b + "." for b in base])
    question = talk(n=18, sentence_s=2.0, texts=[b + ("?" if i == 12 else ".") for i, b in enumerate(base)])
    everything = {"variants_per_start": 1000, "candidates_in_analysis": 100000}
    _, a_plain, _ = pick(plain, params=everything)
    _, a_q, s_q = pick(question, params=everything)

    def by_span(analysis):
        return {(c["start"], c["end"]): c for c in analysis["candidates_top"]}
    end_of_12, end_of_13 = s_q.sentences[12].end, s_q.sentences[13].end
    plain_c, q_c = by_span(a_plain), by_span(a_q)
    on_q = [k for k in q_c if k in plain_c and abs(k[1] - end_of_12) < 0.5]
    assert on_q, "expected candidates ending on the question"
    w = boundary_v1.feat.WEIGHTS
    for k in on_q:
        # D8 (revised): the question ending earns the thought-end and question bonuses.
        assert q_c[k]["features"]["ends_on_question"] == 1.0 and q_c[k]["features"]["end_is_thought"] == 1.0
        if q_c[k]["features"]["start_is_thought"] == plain_c[k]["features"]["start_is_thought"]:
            assert q_c[k]["score"] == pytest.approx(plain_c[k]["score"] + w["ends_on_question"]
                                                    + w["end_is_thought"])
    # From the same start, stopping on the question beats one more sentence after it
    # (length aside: the two endings differ in duration, which is scored separately).
    past = {k[0]: q_c[k] for k in q_c if abs(k[1] - end_of_13) < 0.5}
    pairs = [(q_c[k], past[k[0]]) for k in on_q if k[0] in past]
    assert pairs

    def ending_score(c):
        return c["score"] - c["contributions"]["duration_fit"]
    assert all(ending_score(q) > ending_score(after) for q, after in pairs)
    # And with the default ending variants, the question ending is generated for those starts.
    _, a_default, _ = pick(question)
    assert any(abs(c["end"] - end_of_12) < 0.5 for c in a_default["candidates_top"])


def test_untrusted_and_mostly_silent_stretches_are_pruned():
    # Short untrusted spans: a clip can only straddle one that is shorter than the hard maximum.
    _, analysis, _ = pick(talk(n=40, sentence_s=2.0, suspect=(10, 25)))
    assert analysis["counts"]["pruned"].get("mostly_untrusted_transcript", 0) > 0
    _, analysis, _ = pick(talk(n=30, sentence_s=2.0, extra_gap_every=3, extra_gap_s=3.0))
    assert analysis["counts"]["pruned"].get("too_little_speech", 0) > 0


def test_near_duplicate_text_is_not_picked_twice_while_distinct_clips_exist():
    rng = random.Random(5)
    block = [words(rng, 8).capitalize() + "." for _ in range(12)]
    rest = [words(rng, 8).capitalize() + "." for _ in range(36)]
    clips, analysis, _ = pick(talk(n=60, texts=block + rest + block))   # intro montage repeated later
    texts = [fc["text"] for fc in analysis["final_clips"] if fc["tier"] <= 2]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            assert similarity(trigrams(texts[i]), trigrams(texts[j])) < 0.5


def test_opening_word_penalties_per_language():
    assert lexicons.is_filler_start("And then we left", "en")
    assert lexicons.is_context_start("That is why", "en")
    assert lexicons.is_filler_start("लेकिन फिर", "hi") and lexicons.is_context_start("वो बोले", "hi")
    assert lexicons.is_filler_start("அதனால நான்", "ta") and lexicons.is_context_start("அது சரி", "ta")
    assert not lexicons.is_filler_start("Brand new idea", "en")
    texts = ["And " + words(random.Random(i), 7) + "." for i in range(40)]
    _, analysis, _ = pick(talk(texts=texts))
    fc = analysis["final_clips"][0]
    assert fc["features"]["filler_start"] == 1.0 and fc["contributions"]["filler_start"] == -0.5


def test_selection_is_deterministic():
    t = talk()
    a, b = pick(t), pick(t)
    assert a[0] == b[0] and a[1]["final_clips"] == b[1]["final_clips"]


# ---------------------------------------------------------------------------
# loudness
# ---------------------------------------------------------------------------

def _wav(path: Path, chunks: list[tuple[float, float]], rate=16000, channels=1) -> Path:
    data = np.concatenate([amp * np.sin(np.linspace(0, 440 * 2 * np.pi * dur, int(rate * dur), endpoint=False))
                           for dur, amp in chunks])
    pcm = (data * 32767).astype(np.int16)
    if channels == 2:
        pcm = np.repeat(pcm, 2)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def test_loudness_envelope_tracks_level_and_rejects_unusable_files(tmp_path):
    env = loudness_envelope(_wav(tmp_path / "a.wav", [(1.0, 0.5), (1.0, 0.05)]))
    assert len(env.db) == 20
    assert env.db[:10].mean() - env.db[10:].mean() == pytest.approx(20.0, abs=0.5)
    assert loudness_envelope(tmp_path / "missing.wav") is None
    assert loudness_envelope(_wav(tmp_path / "s.wav", [(1.0, 0.5)], channels=2)) is None


def test_loudness_feature_uses_the_audio_and_is_neutral_without_it(tmp_path):
    t = talk(n=40)
    duration = t.audio_duration
    half = duration / 2
    audio = _wav(tmp_path / "talk.wav", [(half, 0.05), (duration - half, 0.6)])     # second half louder
    clips, analysis, _ = pick(t, count=1, audio_path=str(audio))
    assert analysis["meta"]["loudness"] == "available"
    assert clips[0]["start"] > half                              # the loud half wins
    top = analysis["candidates_top"]
    assert all(c["features"]["loudness_z"] > 0 for c in top if c["start"] > half)
    _, without, _ = pick(t)
    assert without["meta"]["loudness"] == "unavailable"
    assert all(c["features"]["loudness_z"] == 0.0 for c in without["candidates_top"])


# ---------------------------------------------------------------------------
# registry, harness metrics, config
# ---------------------------------------------------------------------------

def test_registry_runs_both_engines_and_rejects_unknown_names():
    t = talk()
    assert len(run("boundary_v1", SelectionInput(t, t.audio_duration, 5)).clips) == 5
    assert run("legacy_v2", SelectionInput(t, t.audio_duration, 3)).engine_version == "adaptive_v2"
    with pytest.raises(ValueError, match="unknown selection engine"):
        run("nope", SelectionInput(t, t.audio_duration, 5))


def test_harness_measures_boundary_quality_for_both_engines():
    t = talk()
    new = run_engine(parse_engine_spec("boundary_v1@5"), t, t.audio_duration)
    old = run_engine(parse_engine_spec("legacy_v2@5"), t, t.audio_duration)
    m_new = selection_metrics(new.clips, 5, t.audio_duration, new.analysis, transcript=t)
    m_old = selection_metrics(old.clips, 5, t.audio_duration, old.analysis, transcript=t)
    assert m_new["boundary"]["edges_inside_speech"] == 0
    assert m_new["boundary"]["starts_at_sentence_start"] == 5 and m_new["boundary"]["ends_at_sentence_end"] == 5
    assert m_new["shortfall_reason"] is None
    assert "edges_inside_speech" in m_old["boundary"]


def test_ten_second_legacy_baseline_is_evaluation_only_and_leaves_legacy_untouched():
    from services import segment_selection
    t = talk()
    short = run_engine(parse_engine_spec("legacy_v2_10s@5"), t, t.audio_duration)
    assert short.engine_version.endswith("+10s") and len(short.clips) == 5
    assert all(c["end"] - c["start"] <= 10.0 + 1e-6 for c in short.clips)
    assert segment_selection.MAX_DURATION == 20.0 and segment_selection.BUFFER == 3.0   # restored
    normal = run_engine(parse_engine_spec("legacy_v2@5"), t, t.audio_duration)
    assert max(c["end"] - c["start"] for c in normal.clips) > 10.0
    with pytest.raises(ValueError, match="unknown selection engine"):
        run("legacy_v2_10s", SelectionInput(t, t.audio_duration, 5))              # not in production


def test_selection_engine_setting_is_validated():
    env = {**os.environ, "SELECTION_ENGINE": "magic", "CLIPPODS_DISABLE_DOTENV": "1"}
    out = subprocess.run([sys.executable, "-c", "import config"], cwd=Path(__file__).resolve().parents[1],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode != 0 and "SELECTION_ENGINE must be" in out.stderr


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

client = TestClient(app)


def _run_job(tmp_path, transcript, extra_patches=()):
    import ffmpeg as ffmpeg_module

    def fake_clips(video, selected, job_id=None):
        run_dir = config.OUTPUTS_DIR / os.urandom(16).hex()
        run_dir.mkdir(parents=True)
        out = []
        for i, _ in enumerate(selected):
            p = run_dir / f"{run_dir.name}_clip_{i}.mp4"
            p.write_bytes(b"\x00" * 32)
            out.append(str(p))
        return out

    patches = [
        patch("routers.video.get_video_input", new=AsyncMock(return_value=tmp_path / "video.mp4")),
        patch.object(ffmpeg_module, "probe", return_value={"format": {"duration": str(transcript.audio_duration)}}),
        patch("routers.video.extract_audio", return_value=str(tmp_path / "audio.wav")),
        patch("routers.video.transcribe_rich", return_value=transcript),
        patch("routers.video.generate_clips", side_effect=fake_clips),
        *extra_patches,
    ]
    for p in patches:
        p.start()
    try:
        job_id = client.post("/process", json={"video_url": "https://example.com/v"}).json()["job_id"]
        deadline = time.time() + 10
        while time.time() < deadline:
            job = client.get(f"/status/{job_id}").json()
            if job["status"] in ("completed", "error", "cancelled"):
                return job
            time.sleep(0.05)
        raise TimeoutError(job_id)
    finally:
        for p in patches:
            p.stop()


def _analysis(job):
    return json.loads((config.OUTPUTS_DIR / job["run_uuid"] / "analysis.json").read_text(encoding="utf-8"))


def test_boundary_v1_in_the_pipeline_returns_five_clips_without_a_score(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELECTION_ENGINE", "boundary_v1")
    job = _run_job(tmp_path, talk())
    assert job["status"] == "completed", job
    assert len(job["clips"]) == 5 and all(c["score"] is None and c["tier"] == 1 for c in job["clips"])
    assert job.get("warnings", []) == []
    analysis = _analysis(job)
    assert analysis["meta"]["engine"] == "boundary_v1" and analysis["meta"]["job_id"]
    assert [fc["filename"] for fc in analysis["final_clips"]] == [c["filename"] for c in job["clips"]]


def test_missing_structure_falls_back_to_legacy_with_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELECTION_ENGINE", "boundary_v1")
    boom = patch("routers.video.build_speech_structure", side_effect=RuntimeError("boom"))
    job = _run_job(tmp_path, talk(), extra_patches=(boom,))
    assert job["status"] == "completed", job
    assert len(job["clips"]) == 3 and all(isinstance(c["score"], int) for c in job["clips"])
    assert any("picked with legacy_v2 instead" in w for w in job["warnings"])


def test_short_video_returns_fewer_clips_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELECTION_ENGINE", "boundary_v1")
    job = _run_job(tmp_path, talk(n=6))
    assert job["status"] == "completed", job
    assert 0 < len(job["clips"]) < 5
    assert any("instead of 5" in w for w in job["warnings"])


def test_no_clean_clip_fails_the_job_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELECTION_ENGINE", "boundary_v1")
    job = _run_job(tmp_path, talk(n=1))
    assert job["status"] == "error"
    assert job["error"].startswith("No clean clips could be found: no candidate clips")


def test_default_engine_is_still_legacy(tmp_path):
    assert config.SELECTION_ENGINE == "legacy_v2"
    job = _run_job(tmp_path, talk())
    assert job["status"] == "completed" and len(job["clips"]) == 3
