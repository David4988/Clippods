"""
tests/test_segment_selection.py — Unit tests for Task 4: select_segments

Run with: pytest tests/test_segment_selection.py -v
"""
import pytest
from fastapi import HTTPException

from services.segment_selection import (
    BUFFER,
    MIN_DURATION,
    PREF_MAX_DURATION,
    MAX_DURATION,
    MIN_START,
    DEFAULT_NUM_CLIPS,
    _clamp_window,
    _uniform_fallback,
    _windows_overlap,
    _word_density,
    select_segments,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _seg(start: float, end: float, text: str = "word " * 10) -> dict:
    return {"start": start, "end": end, "text": text.strip()}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestWordDensity:
    def test_zero_duration_returns_zero(self):
        assert _word_density("hello world", 0.0) == 0.0

    def test_negative_duration_returns_zero(self):
        assert _word_density("hello", -1.0) == 0.0

    def test_correct_density(self):
        assert _word_density("a b c d", 2.0) == pytest.approx(2.0)


class TestClampWindow:
    def test_normal_case(self):
        ws, we = _clamp_window(10.0, 120.0)
        assert we - ws == pytest.approx(PREF_MAX_DURATION)

    def test_overflow_shifts_left(self):
        ws, we = _clamp_window(110.0, 120.0)
        assert we == pytest.approx(120.0)
        assert ws == pytest.approx(100.0 + (20.0 - PREF_MAX_DURATION))
        assert we - ws == pytest.approx(PREF_MAX_DURATION)

    def test_start_zero(self):
        ws, we = _clamp_window(0.0, 60.0)
        assert ws == 0.0
        assert we == pytest.approx(PREF_MAX_DURATION)


class TestWindowsOverlap:
    def test_no_overlap(self):
        assert not _windows_overlap(0.0, 20.0, 20.0, 40.0)

    def test_overlap(self):
        assert _windows_overlap(0.0, 25.0, 20.0, 40.0)

    def test_contained(self):
        assert _windows_overlap(5.0, 15.0, 0.0, 20.0)


# ---------------------------------------------------------------------------
# Sub-task 4.1 — Selection Algorithm
# ---------------------------------------------------------------------------

class TestSelectSegments:

    def test_raises_400_on_non_positive_duration(self):
        with pytest.raises(HTTPException) as exc_info:
            select_segments([], 0.0)
        assert exc_info.value.status_code == 400

    def test_raises_400_on_negative_duration(self):
        with pytest.raises(HTTPException) as exc_info:
            select_segments([], -10.0)
        assert exc_info.value.status_code == 400

    def test_always_returns_num_clips(self):
        ts = [_seg(i * 5, i * 5 + 4) for i in range(20)]
        result = select_segments(ts, 120.0)
        assert len(result) == DEFAULT_NUM_CLIPS

    def test_returns_three_for_long_video(self):
        ts = [_seg(i * 10, i * 10 + 8) for i in range(12)]
        result = select_segments(ts, 120.0)
        assert len(result) == DEFAULT_NUM_CLIPS

    def test_segments_are_non_overlapping(self):
        ts = [_seg(i * 5, i * 5 + 4) for i in range(30)]
        result = select_segments(ts, 200.0)
        # After _align_end extension, clips may be up to MAX_DURATION wide.
        # We just check that they don't overlap each other.
        for i, a in enumerate(result):
            for j, b in enumerate(result):
                if i != j:
                    assert not _windows_overlap(a["start"], a["end"],
                                                b["start"], b["end"]), \
                        f"Overlap: {a} ↔ {b}"

    def test_segments_sorted_by_start(self):
        ts = [_seg(i * 5, i * 5 + 4) for i in range(20)]
        result = select_segments(ts, 120.0)
        starts = [s["start"] for s in result]
        assert starts == sorted(starts)

    def test_each_segment_has_start_and_end_keys(self):
        ts = [_seg(0, 5, "hello world foo bar")]
        result = select_segments(ts, 60.0)
        for seg in result:
            assert "start" in seg
            assert "end" in seg

    def test_prefers_high_density_region(self):
        """Dense cluster near start should be selected first."""
        # 15 segments of 1s each clustered at MIN_START, giving 15s of speech
        # which passes the 0.6*(we-ws) energy filter
        dense = [_seg(MIN_START + i, MIN_START + i + 1, "word " * 20) for i in range(15)]
        # Sparse region in the middle
        sparse = [_seg(80, 85, "a")]
        ts = dense + sparse
        result = select_segments(ts, 200.0)
        # The first selected clip (by start) should be near MIN_START
        result.sort(key=lambda s: s["start"])
        assert result[0]["start"] < 25.0


# ---------------------------------------------------------------------------
# Sub-task 4.2 — Timing Validation
# ---------------------------------------------------------------------------

class TestTimingValidation:

    def test_clip_duration_within_bounds(self):
        """Every selected segment must be between MIN_DURATION and MAX_DURATION + BUFFER wide."""
        ts = [_seg(i * 8, i * 8 + 7) for i in range(15)]
        result = select_segments(ts, 180.0)
        for seg in result:
            width = round(seg["end"] - seg["start"], 6)
            assert MIN_DURATION - 0.01 <= width <= MAX_DURATION + BUFFER + 0.01, \
                f"Segment width {width} not in [{MIN_DURATION}, {MAX_DURATION + BUFFER}]: {seg}"

    def test_segments_within_video_bounds(self):
        """No segment should exceed video_duration."""
        ts = [_seg(i * 5, i * 5 + 4) for i in range(20)]
        video_duration = 100.0
        result = select_segments(ts, video_duration)
        for seg in result:
            assert seg["start"] >= 0.0, f"start < 0: {seg}"
            assert seg["end"] <= video_duration + 0.001, f"end > duration: {seg}"

    def test_short_video_returns_three_clips(self):
        result = select_segments([], 15.0)
        assert len(result) == DEFAULT_NUM_CLIPS

        for seg in result:
            assert seg["start"] == 0.0
            assert seg["end"] == pytest.approx(15.0)

    def test_no_timestamps_uses_uniform_fallback(self):
        """Empty timestamps → uniform 3-window distribution."""
        result = select_segments([], 120.0)
        assert len(result) == DEFAULT_NUM_CLIPS
        for seg in result:
            width = round(seg["end"] - seg["start"], 6)
            assert PREF_MAX_DURATION - 0.01 <= width <= MAX_DURATION + BUFFER + 0.01, \
                f"Fallback width {width} not in [{PREF_MAX_DURATION}, {MAX_DURATION + BUFFER}]: {seg}"

    def test_malformed_timestamps_are_ignored(self):
        """Segments missing start/end don't crash the function."""
        bad_ts = [
            {"text": "no timing at all"},
            {"start": "not_a_number", "end": 5.0, "text": "bad type"},
            {"start": 10.0, "end": 8.0, "text": "end before start"},  # filtered
        ]
        # Should fall back to uniform without raising
        result = select_segments(bad_ts, 120.0)
        assert isinstance(result, list)
