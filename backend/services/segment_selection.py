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
ENERGY_RATIO_THRESHOLD = 0.6
STEP = 5.0  # stride

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
# Analysis helpers (only used when collect_analysis=True)
# ---------------------------------------------------------------------------

def _score_stopping_point_detailed(
    seg: dict, next_seg: Optional[dict], duration: float
) -> dict:
    """Returns score + full heuristic breakdown with actual-vs-threshold."""
    breakdown = []
    score = 0
    text = seg.get("text", "").strip()

    # +2 sentence completion / punctuation
    is_sent = text.endswith((".", "!", "?"))
    pts = 2 if is_sent else 0
    score += pts
    last_char = text[-1] if text else ""
    breakdown.append({
        "heuristic": "sentence_end",
        "points": pts,
        "max_points": 2,
        "passed": is_sent,
        "actual": f"Text ends with '{last_char}'" if text else "Empty text",
        "threshold": "Ends with . ! or ?",
        "detail": f"+{pts} {'sentence completion' if is_sent else 'no sentence-ending punctuation'}",
    })

    if next_seg:
        # +2 pause above threshold
        pause = round(next_seg["start"] - seg["end"], 3)
        passed = pause >= PAUSE_THRESHOLD
        pts = 2 if passed else 0
        score += pts
        breakdown.append({
            "heuristic": "pause_after",
            "points": pts,
            "max_points": 2,
            "passed": passed,
            "actual_seconds": pause,
            "threshold_seconds": PAUSE_THRESHOLD,
            "detail": f"+{pts} pause after ({pause:.2f}s {'≥' if passed else '<'} {PAUSE_THRESHOLD}s threshold)",
        })

        # +2 speaker change
        cur_spk = seg.get("speaker")
        nxt_spk = next_seg.get("speaker")
        is_change = bool(cur_spk and nxt_spk and cur_spk != nxt_spk)
        pts = 2 if is_change else 0
        score += pts
        if cur_spk and nxt_spk:
            actual = f"{cur_spk} → {nxt_spk}"
        elif cur_spk or nxt_spk:
            actual = f"Only one speaker identified ({cur_spk or nxt_spk})"
        else:
            actual = "No speaker data"
        breakdown.append({
            "heuristic": "speaker_change",
            "points": pts,
            "max_points": 2,
            "passed": is_change,
            "actual": actual,
            "detail": f"+{pts} {'speaker change detected' if is_change else 'no speaker change'}",
        })
    else:
        # No next segment — record zeros
        breakdown.append({
            "heuristic": "pause_after",
            "points": 0, "max_points": 2, "passed": False,
            "actual": "No next segment", "detail": "+0 no next segment for pause check",
        })
        breakdown.append({
            "heuristic": "speaker_change",
            "points": 0, "max_points": 2, "passed": False,
            "actual": "No next segment", "detail": "+0 no next segment for speaker check",
        })

    # +1 duration >= preferred duration
    passed = duration >= PREF_MIN_DURATION
    pts = 1 if passed else 0
    score += pts
    breakdown.append({
        "heuristic": "preferred_duration",
        "points": pts,
        "max_points": 1,
        "passed": passed,
        "actual_seconds": round(duration, 3),
        "threshold_seconds": PREF_MIN_DURATION,
        "detail": f"+{pts} duration {duration:.1f}s {'≥' if passed else '<'} preferred minimum {PREF_MIN_DURATION}s",
    })

    # +1 transcript segment boundary
    score += 1
    breakdown.append({
        "heuristic": "segment_boundary",
        "points": 1,
        "max_points": 1,
        "passed": True,
        "detail": "+1 transcript segment boundary",
    })

    return {
        "timestamp": round(seg["end"], 3),
        "clip_duration_at_point": round(duration, 3),
        "total_score": score,
        "selected": False,  # marked later
        "score_breakdown": breakdown,
    }


def _analyze_start(ws: float, valid_ts: list[dict]) -> dict:
    """Analyze why a clip starts at this timestamp."""
    seg = None
    prev = None
    for s in valid_ts:
        if s["end"] <= ws:
            prev = s
        if s["start"] >= ws and seg is None:
            seg = s
        if seg is not None and prev is not None:
            break
    # If no segment starts after ws, pick the one containing ws
    if seg is None:
        for s in valid_ts:
            if s["start"] <= ws <= s["end"]:
                seg = s
                break

    checks = []

    # Sentence boundary
    if prev:
        prev_text = prev.get("text", "").strip()
        is_boundary = prev_text.endswith((".", "!", "?"))
        last_char = prev_text[-1] if prev_text else ""
        checks.append({
            "name": "sentence_boundary",
            "passed": is_boundary,
            "actual": f"Previous segment ends with '{last_char}'" if prev_text else "No previous text",
            "detail": "Clean sentence start" if is_boundary else "Starts after incomplete sentence",
        })

    # Pause before
    if prev:
        pause = round(ws - prev["end"], 3)
        checks.append({
            "name": "pause_before",
            "passed": pause >= PAUSE_THRESHOLD,
            "actual_seconds": pause,
            "threshold_seconds": PAUSE_THRESHOLD,
            "detail": f"{pause:.1f}s pause before → {'natural break point' if pause >= PAUSE_THRESHOLD else 'tight transition'}",
        })

    # Mid-sentence start
    if seg:
        is_mid = ws > seg["start"] + 0.5  # more than 0.5s into a segment
        checks.append({
            "name": "mid_sentence_start",
            "passed": not is_mid,
            "actual": f"Window start ({ws:.1f}s) vs segment start ({seg['start']:.1f}s)",
            "detail": "Not cutting mid-sentence" if not is_mid else f"Starts {ws - seg['start']:.1f}s into segment",
        })

    # Filler word
    if seg:
        first_word = ""
        text = seg.get("text", "").strip()
        if text:
            first_word = text.split()[0].lower()
        is_filler = first_word in ("um", "uh", "like", "so", "well", "yeah", "ok", "okay")
        checks.append({
            "name": "filler_word",
            "passed": not is_filler,
            "actual": f"First word: '{first_word}'" if first_word else "No text",
            "detail": f"{'Filler detected' if is_filler else 'No filler detected'}",
        })

    # Transcript preview
    preview = ""
    if seg:
        preview = seg.get("text", "").strip()[:100]

    return {
        "timestamp": ws,
        "transcript_segment_index": next(
            (i for i, s in enumerate(valid_ts) if s is seg), None
        ) if seg else None,
        "transcript_preview": preview,
        "speaker": seg.get("speaker") if seg else None,
        "checks": checks,
    }


def _get_config_dict(max_clips: int) -> dict:
    """Return current heuristic configuration as a dict."""
    return {
        "min_duration": MIN_DURATION,
        "pref_min_duration": PREF_MIN_DURATION,
        "pref_max_duration": PREF_MAX_DURATION,
        "max_duration": MAX_DURATION,
        "pause_threshold": PAUSE_THRESHOLD,
        "buffer": BUFFER,
        "min_start": MIN_START,
        "step": STEP,
        "energy_ratio_threshold": ENERGY_RATIO_THRESHOLD,
        "max_clips": max_clips,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def select_segments(
    timestamps: list[dict],
    video_duration: float,
    max_clips: int = DEFAULT_NUM_CLIPS,
    collect_analysis: bool = False,
) -> list[Segment] | tuple[list[Segment], dict]:
    """
    Select the best clip segments from transcript timestamps.

    When collect_analysis=True, returns (segments, analysis_dict) instead of
    just segments. The analysis_dict contains the full execution trace for
    the Algorithm Debugger.
    """

    if not isinstance(video_duration, (int, float)) or video_duration <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"video_duration must be positive, got {video_duration!r}",
        )

    # --- Optional: set up analysis collector ---
    collector = None
    if collect_analysis:
        from services.analysis_collector import AnalysisCollector
        from services.analysis_constants import ALGORITHM_VERSION, ANALYSIS_SCHEMA_VERSION

        collector = AnalysisCollector(
            video_duration=video_duration,
            config=_get_config_dict(max_clips),
            transcript=timestamps,
            algorithm_version=ALGORITHM_VERSION,
            schema_version=ANALYSIS_SCHEMA_VERSION,
        )
        collector.start_timer()

    valid_ts = [
        t for t in timestamps
        if isinstance(t.get("start"), (int, float))
        and isinstance(t.get("end"), (int, float))
        and t["end"] >= t["start"]
    ]

    # --- Sliding Window Selection ---
    candidates = []
    # Track analysis-enriched candidates separately
    analysis_candidates: dict[tuple[float, float], int] = {}  # (ws, we) -> candidate_id

    t = MIN_START

    while t + MIN_DURATION <= video_duration:
        ws = t

        current_speech_count = 0
        current_total_speech_duration = 0.0
        current_word_density_score = 0.0
        current_word_count = 0

        best_end = None
        best_stop_score = -1
        best_speech_count = 0
        best_speech_duration = 0.0
        best_word_density_score = 0.0
        best_word_count = 0

        # For analysis: collect all stopping points for this window
        window_stopping_points = []

        for i, seg in enumerate(valid_ts):
            mid = (seg["start"] + seg["end"]) / 2.0

            if mid >= ws and mid <= ws + MAX_DURATION:
                duration = seg["end"] - seg["start"]
                text = seg.get("text", "").strip()

                if text:
                    current_speech_count += 1
                    current_total_speech_duration += duration
                    current_word_density_score += _word_density(text, duration)
                    current_word_count += len(text.split())

                clip_duration = seg["end"] - ws

                if clip_duration >= MIN_DURATION and clip_duration <= MAX_DURATION:
                    next_seg = valid_ts[i + 1] if i + 1 < len(valid_ts) else None
                    stop_score = _score_stopping_point(seg, next_seg, clip_duration)

                    # Collect detailed stopping point for analysis
                    if collector is not None:
                        sp_detail = _score_stopping_point_detailed(seg, next_seg, clip_duration)
                        window_stopping_points.append(sp_detail)

                    if stop_score > best_stop_score:
                        best_stop_score = stop_score
                        best_end = seg["end"]
                        best_speech_count = current_speech_count
                        best_speech_duration = current_total_speech_duration
                        best_word_density_score = current_word_density_score
                        best_word_count = current_word_count
            elif mid > ws + MAX_DURATION:
                break

        if best_end is None:
            if collector is not None:
                collector.record_filtered_window(
                    ws, None, "no_stopping_point",
                    f"No valid stopping point found in [{ws:.1f}s → {ws + MAX_DURATION:.1f}s]",
                )
            t += STEP
            continue

        we = best_end
        speech_count = best_speech_count
        total_speech_duration = best_speech_duration
        score = best_word_density_score

        # ❌ skip empty or weak windows
        if speech_count == 0:
            if collector is not None:
                collector.record_filtered_window(
                    ws, we, "no_speech",
                    f"speech_count = 0 in window [{ws:.1f}s → {we:.1f}s]",
                )
            t += STEP
            continue

        # 🔥 ENERGY FILTER (this fixes your low-energy issue)
        clip_duration = we - ws
        if total_speech_duration < ENERGY_RATIO_THRESHOLD * clip_duration:
            if collector is not None:
                ratio = round(total_speech_duration / clip_duration, 3) if clip_duration > 0 else 0
                collector.record_filtered_window(
                    ws, we, "failed_energy_filter",
                    f"speech_ratio {ratio} < threshold {ENERGY_RATIO_THRESHOLD}",
                    inspection={
                        "speech_duration": round(total_speech_duration, 3),
                        "clip_duration": round(clip_duration, 3),
                        "actual_ratio": ratio,
                        "threshold": ENERGY_RATIO_THRESHOLD,
                    },
                )
            t += STEP
            continue

        # --- Candidate accepted ---
        candidates.append((score, ws, we))

        if collector is not None:
            collector.begin_candidate(ws)

            # Energy filter trace
            collector.record_energy_filter(
                total_speech_duration, clip_duration,
                ENERGY_RATIO_THRESHOLD, True,
            )

            # Record all stopping points
            for sp in window_stopping_points:
                collector.record_stopping_point(sp)

            # Build end analysis from the best stopping point
            best_sp = None
            for sp in window_stopping_points:
                if sp["timestamp"] == we:
                    if best_sp is None or sp["total_score"] > best_sp["total_score"]:
                        best_sp = sp
            end_analysis = {
                "timestamp": round(we, 3),
                "total_score": best_sp["total_score"] if best_sp else best_stop_score,
                "score_breakdown": best_sp["score_breakdown"] if best_sp else [],
                "transcript_preview": "",
            }
            # Get transcript preview at end
            for s in valid_ts:
                if abs(s["end"] - we) < 0.01:
                    end_analysis["transcript_preview"] = s.get("text", "").strip()[:100]
                    break

            # Metrics
            speech_ratio = round(total_speech_duration / clip_duration, 3) if clip_duration > 0 else 0
            metrics = {
                "word_count": best_word_count,
                "word_density": round(score, 3),
                "speech_segment_count": speech_count,
                "speech_duration": round(total_speech_duration, 3),
                "speech_ratio": speech_ratio,
                "raw_score": round(score, 3),
            }

            start_analysis = _analyze_start(ws, valid_ts)

            cand_id = collector._candidate_counter - 1  # begin_candidate already incremented
            analysis_candidates[(ws, we)] = cand_id

            collector.finalize_candidate(we, metrics, start_analysis, end_analysis)

        t += STEP

    # --- Dedup ---
    raw_count = len(candidates)
    best = {}
    for score, ws, we in candidates:
        key = (ws, we)
        if score > best.get(key, -1):
            best[key] = score

    if collector is not None:
        collector.record_decision(
            1, "sliding_window_scan",
            f"Scanned {raw_count + len(collector.filtered_windows)} windows "
            f"(step={STEP}s), produced {raw_count} raw candidates",
        )
        collector.record_decision(
            2, "filter_results",
            f"{len(collector.filtered_windows)} filtered out "
            f"({sum(1 for fw in collector.filtered_windows if fw['reason'] == 'no_stopping_point')} no_stopping_point, "
            f"{sum(1 for fw in collector.filtered_windows if fw['reason'] == 'no_speech')} no_speech, "
            f"{sum(1 for fw in collector.filtered_windows if fw['reason'] == 'failed_energy_filter')} failed_energy_filter)",
        )
        collector.record_decision(
            3, "dedup",
            f"{raw_count} raw → {len(best)} unique (start,end) positions (kept best score per position)",
        )

    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)

    selected: list[Segment] = []
    selection_rank = 0

    for (ws, we), score in ranked:
        if len(selected) >= max_clips:
            break

        overlap_with = None
        for s in selected:
            if _windows_overlap(ws, we, s["start"], s["end"]):
                overlap_with = s
                break

        if overlap_with is not None:
            if collector is not None:
                cand_id = analysis_candidates.get((ws, we))
                if cand_id is not None:
                    collector.mark_candidate_rejected(
                        cand_id, selection_rank,
                        "overlap",
                        f"Overlaps with selected clip [{overlap_with['start']:.1f}s → {overlap_with['end']:.1f}s]",
                    )
            selection_rank += 1
            continue

        # Map raw word density score to a viral score between 75% and 98%
        viral_score = int(75 + min(score * 4, 23))
        selected.append(Segment(start=ws, end=we, score=viral_score))

        if collector is not None:
            cand_id = analysis_candidates.get((ws, we))
            if cand_id is not None:
                collector.mark_candidate_selected(cand_id, selection_rank)

        selection_rank += 1

    # Mark remaining unselected candidates as "lower_score"
    if collector is not None:
        for (ws, we), score in ranked:
            cand_id = analysis_candidates.get((ws, we))
            if cand_id is not None:
                for c in collector.candidates:
                    if c["id"] == cand_id and not c["selected"] and c["rejection_reason"] is None:
                        c["rejection_reason"] = "lower_score"
                        c["trace"].append({
                            "step": "selection",
                            "result": "rejected",
                            "reason": "lower_score",
                            "detail": f"Not selected — {max_clips} clip slots already filled by higher-scoring candidates",
                        })
                        break

    clips_from_ranked = len(selected)

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
    clips_duplicated = 0
    if not selected:
        selected = _uniform_fallback(video_duration, max_clips)

    while len(selected) < max_clips:
        selected.append(dict(selected[-1]))
        clips_duplicated += 1

    selected = selected[:max_clips]

    clips_from_fallback = len(selected) - clips_from_ranked

    if collector is not None:
        collector.record_decision(
            4, "rank_and_select",
            f"Sorted {len(best)} candidates by score descending. "
            f"Selected top {clips_from_ranked} non-overlapping.",
        )
        if clips_from_fallback > 0:
            collector.record_decision(
                5, "fallback",
                f"{clips_from_fallback} clip(s) filled from uniform fallback",
            )
        else:
            collector.record_decision(
                5, "fallback_check",
                f"{clips_from_ranked}/{max_clips} slots filled from ranked candidates. No fallback needed.",
            )

    # 🔥 APPLY CLEAN EXTENSION
    extension_details = []
    for seg in selected:
        pre_extension_end = seg["end"]
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

        if collector is not None:
            if abs(seg["end"] - pre_extension_end) > 0.01:
                extension_details.append(
                    f"clip [{seg['start']:.1f}s] extended {pre_extension_end:.1f}s → {seg['end']:.1f}s"
                )
            seg["_pre_extension_end"] = pre_extension_end  # temp field for final_clips

    if collector is not None:
        if extension_details:
            collector.record_decision(
                6, "end_extension",
                f"Applied _align_end: {'; '.join(extension_details)}",
            )
        else:
            collector.record_decision(6, "end_extension", "No extensions applied")

    selected.sort(key=lambda s: s["start"])

    # Clamp extended ends so adjacent clips don't overlap
    clamp_count = 0
    for i in range(len(selected) - 1):
        if selected[i]["start"] != selected[i + 1]["start"] and \
           selected[i]["end"] > selected[i + 1]["start"]:
            selected[i]["end"] = selected[i + 1]["start"]
            clamp_count += 1

    if collector is not None:
        if clamp_count > 0:
            collector.record_decision(
                7, "overlap_clamp",
                f"Clamped {clamp_count} overlapping adjacent clip end(s)",
            )
        else:
            collector.record_decision(7, "overlap_clamp", "No adjacent clips overlapped after extension")

    # --- Build final_clips for analysis ---
    if collector is not None:
        for clip_idx, seg in enumerate(selected):
            # Find the candidate this clip came from
            cand_id = None
            cand = None
            for c in collector.candidates:
                if abs(c["window_start"] - seg["start"]) < 0.01:
                    cand_id = c["id"]
                    cand = c
                    break

            # Build start/end reasoning lists
            start_reasoning = []
            end_reasoning = []
            if cand and cand.get("start_analysis"):
                for check in cand["start_analysis"].get("checks", []):
                    if check.get("passed"):
                        start_reasoning.append(f"{check['name']} — {check['detail']}")

            if cand and cand.get("end_analysis"):
                for bd in cand["end_analysis"].get("score_breakdown", []):
                    if bd.get("passed"):
                        end_reasoning.append(bd["detail"])

            pre_ext = seg.pop("_pre_extension_end", seg["end"])
            if abs(pre_ext - seg["end"]) > 0.01:
                end_reasoning.append(
                    f"Extended from {pre_ext:.1f}s → {seg['end']:.1f}s to reach sentence boundary"
                )

            # Selection explanation
            total_considered = len(collector.candidates)
            key_strengths = []
            if cand:
                m = cand.get("metrics", {})
                if m.get("word_density"):
                    key_strengths.append(f"Word density {m['word_density']:.2f} w/s")
                if m.get("speech_ratio"):
                    key_strengths.append(f"Speech ratio {m['speech_ratio']:.2f} (above {ENERGY_RATIO_THRESHOLD} threshold)")
                ea = cand.get("end_analysis", {})
                if ea.get("total_score"):
                    key_strengths.append(f"Stop score {ea['total_score']}/8 at end")
                sa = cand.get("start_analysis", {})
                for check in sa.get("checks", []):
                    if check.get("name") == "sentence_boundary" and check.get("passed"):
                        key_strengths.append("Clean sentence boundary at start")
                        break

            # Find next best alternative
            next_best = None
            if clip_idx == 0 and len(selected) > 1:
                next_clip = selected[1]
                for c2 in collector.candidates:
                    if c2["selected"] and abs(c2["window_start"] - next_clip["start"]) < 0.01:
                        next_best = {
                            "candidate_id": c2["id"],
                            "rank": c2.get("final_rank", 1),
                            "score_delta": round(
                                (c2["metrics"].get("raw_score", 0) -
                                 (cand["metrics"].get("raw_score", 0) if cand else 0)),
                                3
                            ),
                            "start": c2["window_start"],
                            "end": c2["window_end"],
                        }
                        break

            clip_data = {
                "clip_index": clip_idx,
                "candidate_id": cand_id,
                "filename": None,  # filled by pipeline after generate_clips
                "start": round(seg["start"], 3),
                "end": round(seg["end"], 3),
                "duration": round(seg["end"] - seg["start"], 3),
                "pre_extension_end": round(pre_ext, 3),
                "transcript_preview": cand["start_analysis"]["transcript_preview"] if cand and cand.get("start_analysis") else "",
                "viral_score": seg.get("score", 0),
                "raw_score": cand["metrics"].get("raw_score", 0) if cand else 0,
                "end_score": cand["end_analysis"]["total_score"] if cand and cand.get("end_analysis") else 0,
                "selection_explanation": {
                    "rank": cand.get("final_rank", clip_idx) if cand else clip_idx,
                    "total_candidates_considered": total_considered,
                    "reason": f"Rank #{(cand.get('final_rank', clip_idx) if cand else clip_idx) + 1} non-overlapping candidate by score",
                    "key_strengths": key_strengths,
                    "next_best_alternative": next_best,
                },
                "start_reasoning": start_reasoning,
                "end_reasoning": end_reasoning,
                "from_fallback": cand is None,
                "duplicated": False,
            }
            collector.record_final_clip(clip_data)

        collector.stop_timer()

    # --- Remove temp fields from selected ---
    for seg in selected:
        seg.pop("_pre_extension_end", None)

    if collect_analysis and collector is not None:
        return selected, collector.to_dict()

    return selected


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _uniform_fallback(video_duration: float, max_clips: int) -> list[Segment]:
    if video_duration <= PREF_MAX_DURATION:
        # Independent dicts, not `[base] * max_clips`: the caller mutates each
        # segment in place (end extension, overlap clamping, temp-field removal),
        # and aliasing makes one write land on all three clips.
        return [
            Segment(start=0.0, end=video_duration, score=80)
            for _ in range(max_clips)
        ]

    zone = video_duration / max_clips
    segments = []

    for i in range(max_clips):
        mid = zone * i + zone / 2
        ws = max(0.0, mid - PREF_MAX_DURATION / 2)
        ws, we = _clamp_window(ws, video_duration)
        segments.append(Segment(start=ws, end=we, score=85 - i))

    return segments