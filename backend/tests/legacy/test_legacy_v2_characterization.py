"""
Explicit characterization of legacy_v2 behaviours that the master plan identified
as defects (§3.1). Each test names the defect it pins. They exist so the baseline
engine is documented and cannot drift silently. They are NOT requirements for any
new engine, and must not be "fixed" in the legacy engine (decision D19).
"""
from __future__ import annotations

import copy
import json

import pytest

from services.segment_selection import MAX_DURATION, MIN_START, STEP, select_segments
from tests.legacy.test_legacy_v2_golden import load_fixture

SPEECH_FIXTURES = ["english_podcast_10min", "hindi_danda_5min", "tamil_5min",
                   "music_gap_hallucination_6min", "long_podcast_90min"]


def _run(name: str, max_clips: int):
    fx = load_fixture(name)
    selected, analysis = select_segments(copy.deepcopy(fx["segments"]), fx["video_duration"],
                                         max_clips=max_clips, collect_analysis=True)
    return fx, selected, analysis


@pytest.mark.parametrize("name", SPEECH_FIXTURES)
def test_issue1_ranked_clip_starts_sit_on_the_5s_grid(name):
    _, selected, analysis = _run(name, 5)
    ranked = [c for c in analysis["final_clips"] if not c["from_fallback"]]
    assert ranked, "fixture should produce ranked clips"
    for clip in ranked:
        offset = (clip["start"] - MIN_START) / STEP
        assert clip["start"] >= MIN_START and offset == int(offset), clip["start"]


@pytest.mark.parametrize("name", SPEECH_FIXTURES)
def test_issue3_4_final_end_is_start_plus_18_or_a_segment_end_up_to_20s(name):
    fx, selected, _ = _run(name, 5)
    seg_ends = {round(s["end"], 3) for s in fx["segments"]}
    starts = sorted(s["start"] for s in selected)
    for clip in selected:
        width = round(clip["end"] - clip["start"], 3)
        clamped_to_next = any(abs(clip["end"] - s) < 1e-6 for s in starts if s > clip["start"])
        assert (
            abs(width - 18.0) < 1e-6
            or (18.0 <= width <= MAX_DURATION and round(clip["end"], 3) in seg_ends)
            or clamped_to_next
        ), clip


def test_issue12_short_video_returns_identical_duplicate_clips():
    _, selected, analysis = _run("short_12s", 5)
    assert len({(c["start"], c["end"]) for c in selected}) == 1
    assert len(selected) == 5
    # ...and the debugger does not report them as duplicated.
    assert all(fc["duplicated"] is False for fc in analysis["final_clips"])
    assert analysis["stats"]["duplicated"] == 0


def test_issue12_empty_transcript_still_yields_full_clip_count_from_fallback():
    _, selected, analysis = _run("empty_120s", 5)
    assert len(selected) == 5
    assert analysis["stats"]["from_fallback"] == 5


def test_issue9_hindi_danda_is_not_a_sentence_end():
    fx, _, analysis = _run("hindi_danda_5min", 5)
    danda_ends = {round(s["end"], 3) for s in fx["segments"] if s["text"].endswith("।")}
    assert danda_ends
    checked = 0
    for cand in analysis["candidates"]:
        for sp in cand["stopping_points"]:
            if sp["timestamp"] in danda_ends:
                sentence = next(b for b in sp["score_breakdown"] if b["heuristic"] == "sentence_end")
                assert sentence["passed"] is False
                checked += 1
    assert checked > 0


def test_issue13_speaker_change_can_never_score():
    _, _, analysis = _run("english_podcast_10min", 5)
    for cand in analysis["candidates"]:
        for sp in cand["stopping_points"]:
            speaker = [b for b in sp["score_breakdown"] if b["heuristic"] == "speaker_change"]
            assert all(b["points"] == 0 for b in speaker)
            assert sp["total_score"] <= 6  # the dashboard displays these out of 8


def test_issue10_viral_score_is_a_mapping_of_word_density():
    _, selected, analysis = _run("english_podcast_10min", 5)
    for clip in analysis["final_clips"]:
        if not clip["from_fallback"]:
            assert clip["viral_score"] == int(75 + min(clip["raw_score"] * 4, 23))


def test_issue18_analysis_payload_is_not_encodable_in_windows_cp1252():
    """Why analysis.json ends up 0 bytes on this Windows machine (P-OBS-1)."""
    _, _, analysis = _run("english_podcast_10min", 3)
    payload = json.dumps(analysis, indent=2, ensure_ascii=False)
    with pytest.raises(UnicodeEncodeError):
        payload.encode("cp1252")


def test_malformed_segments_crash_analysis_mode():
    fx = load_fixture("malformed_entries_120s")
    with pytest.raises(TypeError):
        select_segments(copy.deepcopy(fx["segments"]), fx["video_duration"], collect_analysis=True)
