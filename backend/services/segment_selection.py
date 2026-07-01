from __future__ import annotations

from typing import TypedDict, Optional
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_DURATION = 8.0
PREF_MIN_DURATION = 12.0
PREF_MAX_DURATION = 15.0
MAX_DURATION = 20.0
PAUSE_THRESHOLD = 0.8
DEFAULT_NUM_CLIPS = 3
BUFFER = 3.0  # 🔥 small extension to avoid abrupt cuts
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
    end = start + PREF_MAX_DURATION
    if end > video_duration:
        end = video_duration
        start = max(0.0, end - PREF_MAX_DURATION)
    return round(start, 3), round(end, 3)


def _windows_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


# 🔥 SIMPLE + RELIABLE EXTENSION (no overengineering)
def _extend_end(seg, video_duration):
    return min(seg["start"] + PREF_MAX_DURATION + BUFFER, video_duration)


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

def _score_stopping_point(seg: dict, next_seg: Optional[dict], duration: float) -> int:
    score = 0
    text = seg.get("text", "").strip()
    
    # +2 sentence completion / punctuation
    if text.endswith((".", "!", "?")):
        score += 2
        
    if next_seg:
        # +2 pause above threshold
        pause = next_seg["start"] - seg["end"]
        if pause >= PAUSE_THRESHOLD:
            score += 2
            
        # +2 speaker change
        if seg.get("speaker") and next_seg.get("speaker") and seg["speaker"] != next_seg["speaker"]:
            score += 2

    # +1 duration >= preferred duration
    if duration >= PREF_MIN_DURATION:
        score += 1
        
    # +1 transcript segment boundary
    score += 1
    
    return score
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def select_segments(
    timestamps: list[dict],
    video_duration: float,
    max_clips: int = DEFAULT_NUM_CLIPS,
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

    while t + MIN_DURATION <= video_duration:
        ws = t
        
        current_speech_count = 0
        current_total_speech_duration = 0.0
        current_word_density_score = 0.0
        
        best_end = None
        best_stop_score = -1
        best_speech_count = 0
        best_speech_duration = 0.0
        best_word_density_score = 0.0

        for i, seg in enumerate(valid_ts):
            mid = (seg["start"] + seg["end"]) / 2.0

            if mid >= ws and mid <= ws + MAX_DURATION:
                duration = seg["end"] - seg["start"]
                text = seg.get("text", "").strip()

                if text:
                    current_speech_count += 1
                    current_total_speech_duration += duration
                    current_word_density_score += _word_density(text, duration)
                    
                clip_duration = seg["end"] - ws
                
                if clip_duration >= MIN_DURATION and clip_duration <= MAX_DURATION:
                    next_seg = valid_ts[i + 1] if i + 1 < len(valid_ts) else None
                    stop_score = _score_stopping_point(seg, next_seg, clip_duration)
                    
                    if stop_score > best_stop_score:
                        best_stop_score = stop_score
                        best_end = seg["end"]
                        best_speech_count = current_speech_count
                        best_speech_duration = current_total_speech_duration
                        best_word_density_score = current_word_density_score
            elif mid > ws + MAX_DURATION:
                break
                
        if best_end is None:
            t += STEP
            continue
            
        we = best_end
        speech_count = best_speech_count
        total_speech_duration = best_speech_duration
        score = best_word_density_score

        # ❌ skip empty or weak windows
        if speech_count == 0:
            t += STEP
            continue

        # 🔥 ENERGY FILTER (this fixes your low-energy issue)
        clip_duration = we - ws
        if total_speech_duration < 0.6 * clip_duration:
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
        if len(selected) >= max_clips:
            break
        if any(_windows_overlap(ws, we, s["start"], s["end"]) for s in selected):
            continue
        # Map raw word density score to a viral score between 75% and 98%
        viral_score = int(75 + min(score * 4, 23))
        selected.append(Segment(start=ws, end=we, score=viral_score))

    # --- Fallback ---
    if len(selected) < max_clips:
        for seg in _uniform_fallback(video_duration, max_clips):
            if len(selected) >= max_clips:
                break
            if any(_windows_overlap(seg["start"], seg["end"], s["start"], s["end"]) for s in selected):
                continue
            seg["score"] = 82 - len(selected)
            selected.append(seg)

    # Ensure we have at least max_clips clips
    if not selected:
        selected = _uniform_fallback(video_duration, max_clips)

    while len(selected) < max_clips:
        selected.append(dict(selected[-1]))

    selected = selected[:max_clips]

    # 🔥 APPLY CLEAN EXTENSION
    for seg in selected:
        default_end = min(
            seg["start"] + PREF_MAX_DURATION + BUFFER,
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

def _uniform_fallback(video_duration: float, max_clips: int) -> list[Segment]:
    if video_duration <= PREF_MAX_DURATION:
        base = Segment(start=0.0, end=video_duration, score=80)
        return [base] * max_clips

    zone = video_duration / max_clips
    segments = []

    for i in range(max_clips):
        mid = zone * i + zone / 2
        ws = max(0.0, mid - PREF_MAX_DURATION / 2)
        ws, we = _clamp_window(ws, video_duration)
        segments.append(Segment(start=ws, end=we, score=85 - i))

    return segments