from __future__ import annotations

from typing import TypedDict
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

    # --- Selection ---
    candidates = []

    speech_count = 0
    score = 0.0

    for t in valid_ts:
        mid = (t["start"] + t["end"]) / 2.0
        
        if ws < MIN_START:
            continue
        if ws <= mid < we:
            duration = t["end"] - t["start"]
            text = t.get("text", "").strip()

            if text:
                speech_count += 1
                score += _word_density(text, duration)

        # skip windows with no speech
        if speech_count == 0:
            continue

        candidates.append((score, ws, we))

    best = {}
    for score, ws, we in candidates:
        key = (ws, we)
        if score > best.get(key, -1):
            best[key] = score

    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)

    selected: list[Segment] = []

    for (ws, we), _ in ranked:
        if len(selected) >= NUM_CLIPS:
            break
        if any(_windows_overlap(ws, we, s["start"], s["end"]) for s in selected):
            continue
        selected.append(Segment(start=ws, end=we))

    # --- Fallback ---
    if len(selected) < NUM_CLIPS:
        for seg in _uniform_fallback(video_duration):
            if len(selected) >= NUM_CLIPS:
                break
            if any(_windows_overlap(seg["start"], seg["end"], s["start"], s["end"]) for s in selected):
                continue
            selected.append(seg)

    # --- Force exactly 3 ---
    if not selected:
        selected = _uniform_fallback(video_duration)

    while len(selected) < NUM_CLIPS:
        selected.append(selected[-1])

    selected = selected[:NUM_CLIPS]

    # 🔥 APPLY CLEAN EXTENSION
    for seg in selected:
        seg["end"] = min(
            seg["start"] + CLIP_DURATION + BUFFER,
            seg["start"] + MAX_DURATION,
            video_duration
        )

    selected.sort(key=lambda s: s["start"])

    return selected


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _uniform_fallback(video_duration: float) -> list[Segment]:
    if video_duration <= CLIP_DURATION:
        base = Segment(start=0.0, end=video_duration)
        return [base, base, base]

    zone = video_duration / NUM_CLIPS
    segments = []

    for i in range(NUM_CLIPS):
        mid = zone * i + zone / 2
        ws = max(0.0, mid - CLIP_DURATION / 2)
        ws, we = _clamp_window(ws, video_duration)
        segments.append(Segment(start=ws, end=we))

    return segments