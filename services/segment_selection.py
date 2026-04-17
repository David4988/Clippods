"""
services/segment_selection.py — Task 4: select_segments
Picks 3 non-overlapping 20-second windows from transcript timestamps,
ranked by word density (words per second), then validated for timing.
"""
from __future__ import annotations

from typing import TypedDict

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CLIP_DURATION = 20.0   # seconds — fixed clip length
NUM_CLIPS     = 3      # number of clips to return


class Segment(TypedDict):
    start: float
    end: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _word_density(text: str, duration: float) -> float:
    """Words-per-second for a segment. Returns 0.0 for zero-duration spans."""
    if duration <= 0:
        return 0.0
    return len(text.split()) / duration


def _clamp_window(start: float, video_duration: float) -> tuple[float, float]:
    """
    Return a (start, end) pair of exactly CLIP_DURATION that fits within
    [0, video_duration].  Shifts the window left if it would overflow.
    """
    end = start + CLIP_DURATION
    if end > video_duration:
        end = video_duration
        start = max(0.0, end - CLIP_DURATION)
    return round(start, 3), round(end, 3)


def _windows_overlap(a_start: float, a_end: float,
                     b_start: float, b_end: float) -> bool:
    """True when two intervals share any time (touching endpoints are OK)."""
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Sub-task 4.1: Selection Algorithm
# Sub-task 4.2: Timing Validation
# ---------------------------------------------------------------------------

def select_segments(
    timestamps: list[dict],
    video_duration: float,
) -> list[Segment]:
    """
    Select up to NUM_CLIPS (3) non-overlapping 20-second windows ranked by
    word density.  Falls back to uniform distribution when there are no
    usable timestamp segments.

    Algorithm
    ---------
    1. For every transcript segment, centre a 20-second window on that
       segment's midpoint (clamped to video bounds).
    2. Score the window by word-density of all transcript text whose midpoint
       falls inside the window.
    3. Greedily pick the highest-scoring, non-overlapping windows.
    4. If fewer than NUM_CLIPS candidates exist, pad with uniformly-spaced
       windows (beginning / middle / end).

    Parameters
    ----------
    timestamps : list[dict]
        Each item: {"start": float, "end": float, "text": str}
        (as produced by transcription._normalise_response).
    video_duration : float
        Total length of the source video in seconds.

    Returns
    -------
    list[Segment]
        Exactly min(NUM_CLIPS, possible) segments, each {"start": float, "end": float},
        sorted by start time, all exactly CLIP_DURATION wide (or less at the tail).

    Raises
    ------
    HTTPException(400)
        If video_duration is not a positive number.
    """
    # --- Guard --------------------------------------------------------------
    if not isinstance(video_duration, (int, float)) or video_duration <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"video_duration must be a positive number, got {video_duration!r}.",
        )

    # --- Fallback: uniform distribution for videos with no usable segments --
    valid_ts = [
        t for t in timestamps
        if isinstance(t.get("start"), (int, float))
        and isinstance(t.get("end"), (int, float))
        and t["end"] >= t["start"]
    ]

    if not valid_ts:
        return _uniform_fallback(video_duration)

    # --- Build candidate windows -------------------------------------------
    # One candidate per transcript segment, centred on the segment midpoint.
    candidates: list[tuple[float, float, float]] = []  # (score, start, end)

    for seg in valid_ts:
        midpoint = (float(seg["start"]) + float(seg["end"])) / 2.0
        win_start = max(0.0, midpoint - CLIP_DURATION / 2)
        win_start, win_end = _clamp_window(win_start, video_duration)

        # Score = total word density of ALL segments whose midpoints fall in window
        score = sum(
            _word_density(t.get("text", ""), float(t["end"]) - float(t["start"]))
            for t in valid_ts
            if win_start <= (float(t["start"]) + float(t["end"])) / 2.0 < win_end
        )
        candidates.append((score, win_start, win_end))

    # De-duplicate by (start, end) keeping highest score
    best: dict[tuple[float, float], float] = {}
    for score, ws, we in candidates:
        key = (ws, we)
        if score > best.get(key, -1.0):
            best[key] = score

    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)

    # --- Greedy non-overlap selection --------------------------------------
    selected: list[Segment] = []
    for (ws, we), _ in ranked:
        if len(selected) >= NUM_CLIPS:
            break
        if any(_windows_overlap(ws, we, s["start"], s["end"]) for s in selected):
            continue
        selected.append(Segment(start=ws, end=we))

    # --- Pad with uniform windows if needed --------------------------------
    if len(selected) < NUM_CLIPS:
        for seg in _uniform_fallback(video_duration):
            if len(selected) >= NUM_CLIPS:
                break
            if any(_windows_overlap(seg["start"], seg["end"],
                                    s["start"], s["end"]) for s in selected):
                continue
            selected.append(seg)

    # --- Sort by start time ------------------------------------------------
    selected.sort(key=lambda s: s["start"])
    return selected


def _uniform_fallback(video_duration: float) -> list[Segment]:
    """
    Return up to NUM_CLIPS evenly-spaced 20-second windows.
    Used when there are no transcript timestamps to guide selection.
    """
    if video_duration <= CLIP_DURATION:
        # Video is shorter than one clip — return what we can
        return [Segment(start=0.0, end=round(min(CLIP_DURATION, video_duration), 3))]

    # Divide the video into NUM_CLIPS equal zones, pick the centre of each.
    zone = video_duration / NUM_CLIPS
    segments: list[Segment] = []
    for i in range(NUM_CLIPS):
        zone_mid = zone * i + zone / 2
        win_start = max(0.0, zone_mid - CLIP_DURATION / 2)
        ws, we = _clamp_window(win_start, video_duration)
        segments.append(Segment(start=ws, end=we))
    return segments
