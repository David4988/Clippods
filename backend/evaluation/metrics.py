"""
Automatic selection metrics that need no reference labels.

Phase 0: clip count, duplicates, overlaps, durations, legacy fallback usage.
Phase 6: boundary metrics from VAD + the speech structure (clip edges inside
speech, edges at sentence boundaries, leading/trailing silence, durations in the
20–45 s target, untrusted transcript share). Metrics needing gold moments or
human labels (master plan §10.2) stay in `NOT_YET_MEASURED` so reports never
imply they were checked.
"""
from __future__ import annotations

import statistics

NOT_YET_MEASURED = [
    "truncated_ending_rate", "candidate_recall_at_k", "precision_at_5",
    "semantic_redundancy", "topic_diversity", "asr_wer_cer", "language_id_accuracy",
    "hallucination_rate",
]


def _overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def selection_metrics(clips: list[dict], expected_count: int, video_duration: float,
                      analysis: dict | None = None, transcript=None) -> dict:
    durations = [round(c["end"] - c["start"], 3) for c in clips]
    spans = [(round(c["start"], 3), round(c["end"], 3)) for c in clips]

    identical_pairs = 0
    overlapping_pairs = 0
    max_overlap_ratio = 0.0
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            if spans[i] == spans[j]:
                identical_pairs += 1
            ov = _overlap(clips[i], clips[j])
            if ov > 0:
                overlapping_pairs += 1
                shorter = min(durations[i], durations[j]) or 1e-9
                max_overlap_ratio = max(max_overlap_ratio, ov / shorter)

    metrics = {
        "clip_count": len(clips),
        "expected_clip_count": expected_count,
        "clip_count_ok": len(clips) == expected_count,
        "distinct_spans": len(set(spans)),
        "identical_pairs": identical_pairs,
        "overlapping_pairs": overlapping_pairs,
        "max_overlap_ratio": round(max_overlap_ratio, 3),
        "out_of_bounds": sum(1 for c in clips if c["start"] < 0 or c["end"] > video_duration + 1e-3),
        "duration_s": {
            "values": durations,
            "min": min(durations) if durations else None,
            "max": max(durations) if durations else None,
            "mean": round(statistics.mean(durations), 3) if durations else None,
        },
        "coverage_of_video": round(sum(durations) / video_duration, 4) if video_duration else None,
    }

    if analysis is not None and "final_clips" in analysis:
        final = analysis["final_clips"]
        metrics["legacy"] = {
            "candidates": len(analysis.get("candidates", [])),
            "filtered_windows": len(analysis.get("filtered_windows", [])),
            "clips_from_fallback": sum(1 for fc in final if fc.get("from_fallback")),
            "clips_from_ranked": sum(1 for fc in final if not fc.get("from_fallback")),
            # Reported separately because the legacy trace always says 0 (issue 12).
            "reported_duplicated": analysis.get("stats", {}).get("duplicated"),
            "selection_time_ms": analysis.get("meta", {}).get("processing_time_ms"),
        }

    if transcript is not None and transcript.speech_regions is not None:
        metrics["boundary"] = boundary_metrics(clips, transcript)
    if analysis is not None and "shortfall_reason" in analysis:
        metrics["shortfall_reason"] = analysis["shortfall_reason"]

    metrics["not_yet_measured"] = NOT_YET_MEASURED
    return metrics


TARGET_S = (20.0, 45.0)        # D7
SENTENCE_EDGE_TOLERANCE_S = 0.3


def boundary_metrics(clips: list[dict], transcript) -> dict:
    """How cleanly clip edges sit relative to speech (VAD) and sentence boundaries."""
    from bisect import bisect_left

    from services.speech_structure import build_speech_structure
    from services.transcript_quality import segment_suspicion

    regions = transcript.speech_regions.regions
    structure = build_speech_structure(transcript)
    starts_at = {s.word_range[0] for s in structure.sentences}
    ends_at = {s.word_range[1] for s in structure.sentences}
    start_times = sorted(c.cut_in for c in structure.cut_points
                         if c.cut_in is not None and c.before_word in starts_at)
    end_times = sorted(c.cut_out for c in structure.cut_points
                       if c.cut_out is not None and c.after_word in ends_at)
    untrusted = [(s.start, s.end) for s in transcript.segments if s.text and segment_suspicion(s)]

    def inside_speech(t: float) -> bool:
        return any(a < t < b for a, b in regions)

    def near(t: float, times: list[float]) -> bool:
        i = bisect_left(times, t)
        return any(abs(times[j] - t) <= SENTENCE_EDGE_TOLERANCE_S for j in (i - 1, i) if 0 <= j < len(times))

    def lead_trail(c: dict) -> tuple[float, float]:
        inside = [(max(a, c["start"]), min(b, c["end"])) for a, b in regions if b > c["start"] and a < c["end"]]
        if not inside:
            return c["end"] - c["start"], 0.0
        return inside[0][0] - c["start"], c["end"] - inside[-1][1]

    def overlap(a: float, b: float, spans) -> float:
        return sum(max(0.0, min(b, e) - max(a, s)) for s, e in spans)

    n = len(clips)
    lt = [lead_trail(c) for c in clips]
    inside = sum(inside_speech(c["start"]) for c in clips) + sum(inside_speech(c["end"]) for c in clips)
    return {
        "edges_inside_speech": inside,
        "edges_inside_speech_share": round(inside / (2 * n), 3) if n else None,
        "starts_at_sentence_start": sum(near(c["start"], start_times) for c in clips),
        "ends_at_sentence_end": sum(near(c["end"], end_times) for c in clips),
        "leading_silence_s_mean": round(statistics.mean(x for x, _ in lt), 3) if n else None,
        "trailing_silence_s_mean": round(statistics.mean(y for _, y in lt), 3) if n else None,
        "durations_in_target": sum(TARGET_S[0] <= c["end"] - c["start"] <= TARGET_S[1] for c in clips),
        "untrusted_share_mean": round(statistics.mean(
            overlap(c["start"], c["end"], untrusted) / max(c["end"] - c["start"], 1e-9) for c in clips), 3) if n else None,
    }
