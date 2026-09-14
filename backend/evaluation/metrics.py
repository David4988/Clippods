"""
Automatic selection metrics that need no reference labels.

Phase 0 deliberately implements only what can be computed honestly today:
clip count, duplicates, overlaps, durations and legacy fallback usage. Metrics
that need VAD, word timing, gold moments or human labels (master plan §10.2)
are added in the phases that produce those signals, and are listed in
`NOT_YET_MEASURED` so reports never imply they were checked.
"""
from __future__ import annotations

import statistics

NOT_YET_MEASURED = [
    "mid_word_cut_rate", "mid_sentence_cut_rate", "truncated_ending_rate",
    "leading_trailing_silence", "candidate_recall_at_k", "precision_at_5",
    "semantic_redundancy", "topic_diversity", "asr_wer_cer", "language_id_accuracy",
    "hallucination_rate",
]


def _overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def selection_metrics(clips: list[dict], expected_count: int, video_duration: float,
                      analysis: dict | None = None) -> dict:
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

    metrics["not_yet_measured"] = NOT_YET_MEASURED
    return metrics
