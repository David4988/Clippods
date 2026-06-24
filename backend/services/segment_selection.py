from __future__ import annotations

from typing import TypedDict, Optional
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIP_DURATION = 20.0
NUM_CLIPS = 3
BUFFER = 3.0  # 🔥 small extension to avoid abrupt cuts
MAX_DURATION = 25.0
MIN_START = 5.0

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Segment(TypedDict):
    start: float
    end: float
    score: Optional[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word_density(text: str, duration: float) -> float:
    if duration <= 0:
        return 0.0
    return len(text.split()) / duration


def _clamp_window(start: float, video_duration: float) -> tuple[float, float]:
    end = start + CLIP_DURATION
    if end > video_duration:
        end = video_duration
        start = max(0.0, end - CLIP_DURATION)
    return round(start, 3), round(end, 3)


def _windows_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


# 🔥 SIMPLE + RELIABLE EXTENSION (no overengineering)
def _extend_end(seg, video_duration):
    return min(seg["start"] + CLIP_DURATION + BUFFER, video_duration)


def _align_end(ws, default_end, segments, video_duration):
    search_limit = min(default_end + 2.0, video_duration)

    best_end = default_end

    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        text = seg.get("text", "").strip()

        # only consider segments near end boundary
        if default_end <= seg_end <= search_limit:
            # 🔥 prefer sentence endings
            if text.endswith((".", "!", "?")):
                return seg_end

            # fallback: slight extension if speech continues
            best_end = seg_end

    return best_end
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def select_segments(
    timestamps: list[dict],
    video_duration: float,
) -> list[Segment]:

    if not isinstance(video_duration, (int, float)) or video_duration <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"video_duration must be positive, got {video_duration!r}",
        )

    valid_ts = [
        t for t in timestamps
        if isinstance(t.get("start"), (int, float))
        and isinstance(t.get("end"), (int, float))
        and t["end"] >= t["start"]
    ]

    # --- Sliding Window Selection ---
    candidates = []

    STEP = 5.0  # stride

    t = MIN_START

    while t + CLIP_DURATION <= video_duration:
        ws = t
        we = t + CLIP_DURATION

        speech_count = 0
        score = 0.0
        total_speech_duration = 0.0

        for seg in valid_ts:
            mid = (seg["start"] + seg["end"]) / 2.0

            if ws <= mid < we:
                duration = seg["end"] - seg["start"]
                text = seg.get("text", "").strip()

                if text:
                    speech_count += 1
                    total_speech_duration += duration
                    score += _word_density(text, duration)

        # ❌ skip empty or weak windows
        if speech_count == 0:
            t += STEP
            continue

        # 🔥 ENERGY FILTER (this fixes your low-energy issue)
        if total_speech_duration < 0.6 * CLIP_DURATION:
            t += STEP
            continue

        candidates.append((score, ws, we))

        t += STEP

    best = {}
    for score, ws, we in candidates:
        key = (ws, we)
        if score > best.get(key, -1):
            best[key] = score

    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)

    selected: list[Segment] = []

    for (ws, we), score in ranked:
        if len(selected) >= NUM_CLIPS:
            break
        if any(_windows_overlap(ws, we, s["start"], s["end"]) for s in selected):
            continue
        # Map raw word density score to a viral score between 75% and 98%
        viral_score = int(75 + min(score * 4, 23))
        selected.append(Segment(start=ws, end=we, score=viral_score))

    # --- Fallback ---
    if len(selected) < NUM_CLIPS:
        for seg in _uniform_fallback(video_duration):
            if len(selected) >= NUM_CLIPS:
                break
            if any(_windows_overlap(seg["start"], seg["end"], s["start"], s["end"]) for s in selected):
                continue
            seg["score"] = 82 - len(selected)
            selected.append(seg)

    # --- Force exactly 3 ---
    if not selected:
        selected = _uniform_fallback(video_duration)

    while len(selected) < NUM_CLIPS:
        selected.append(dict(selected[-1]))

    selected = selected[:NUM_CLIPS]

    # 🔥 APPLY CLEAN EXTENSION
    for seg in selected:
        default_end = min(
            seg["start"] + CLIP_DURATION + BUFFER,
            seg["start"] + MAX_DURATION,
            video_duration
        )

        seg["end"] = _align_end(
            seg["start"],
            default_end,
            valid_ts,
            video_duration
        )

    selected.sort(key=lambda s: s["start"])

    # Clamp extended ends so adjacent clips don't overlap
    for i in range(len(selected) - 1):
        if selected[i]["start"] != selected[i + 1]["start"] and \
           selected[i]["end"] > selected[i + 1]["start"]:
            selected[i]["end"] = selected[i + 1]["start"]

    return selected


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _uniform_fallback(video_duration: float) -> list[Segment]:
    if video_duration <= CLIP_DURATION:
        base = Segment(start=0.0, end=video_duration, score=80)
        return [base, base, base]

    zone = video_duration / NUM_CLIPS
    segments = []

    for i in range(NUM_CLIPS):
        mid = zone * i + zone / 2
        ws = max(0.0, mid - CLIP_DURATION / 2)
        ws, we = _clamp_window(ws, video_duration)
        segments.append(Segment(start=ws, end=we, score=85 - i))

    return segments