"""
services/analysis_collector.py — Instrumentation engine for the Algorithm Debugger.

Collects every decision made during select_segments() as an execution trace.
Pure data container with zero external dependencies (no FastAPI, no FFmpeg).
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class AnalysisCollector:
    """Accumulates algorithm decisions during a single select_segments() run."""

    def __init__(
        self,
        video_duration: float,
        config: dict,
        transcript: list[dict],
        algorithm_version: str,
        schema_version: str,
    ):
        self.meta: dict[str, Any] = {
            "schema_version": schema_version,
            "algorithm_version": algorithm_version,
            "job_id": None,           # set later by pipeline
            "run_uuid": None,         # set later by pipeline
            "source": None,           # set later by pipeline
            "source_url": None,       # set later by pipeline
            "filename": None,         # set later by pipeline
            "video_duration_seconds": video_duration,
            "transcript_segment_count": len(transcript),
            "processing_time_ms": None,  # set at finalize
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": config,
        }
        self.transcript: list[dict] = [
            {
                "index": i,
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker"),
                "word_count": len(seg.get("text", "").split()) if seg.get("text") else 0,
                "duration": round(seg.get("end", 0.0) - seg.get("start", 0.0), 3),
            }
            for i, seg in enumerate(transcript)
        ]
        self.candidates: list[dict] = []
        self.filtered_windows: list[dict] = []
        self.decision_log: list[dict] = []
        self.final_clips: list[dict] = []

        # Internal state for building a candidate
        self._current_candidate: Optional[dict] = None
        self._candidate_counter: int = 0
        self._start_time_ns: Optional[int] = None

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    def start_timer(self) -> None:
        """Call at the very start of select_segments."""
        import time
        self._start_time_ns = time.perf_counter_ns()

    def stop_timer(self) -> None:
        """Call at the very end of select_segments."""
        if self._start_time_ns is not None:
            import time
            elapsed_ns = time.perf_counter_ns() - self._start_time_ns
            self.meta["processing_time_ms"] = round(elapsed_ns / 1_000_000, 1)

    # ------------------------------------------------------------------
    # Candidate lifecycle
    # ------------------------------------------------------------------

    def begin_candidate(self, window_start: float) -> None:
        """Start tracking a new candidate window."""
        self._current_candidate = {
            "id": self._candidate_counter,
            "window_start": round(window_start, 3),
            "window_end": None,
            "duration": None,
            "trace": [
                {
                    "step": "candidate_generated",
                    "detail": f"Window starting at {window_start:.1f}s created",
                }
            ],
            "metrics": {},
            "start_analysis": None,
            "end_analysis": None,
            "stopping_points": [],
            "selected": False,
            "final_rank": None,
            "rejection_reason": None,
        }
        self._candidate_counter += 1

    def record_trace_step(
        self,
        step: str,
        result: Optional[str] = None,
        detail: Optional[str] = None,
        inspection: Optional[dict] = None,
    ) -> None:
        """Append a step to the current candidate's execution trace."""
        if self._current_candidate is None:
            return
        entry: dict[str, Any] = {"step": step}
        if result is not None:
            entry["result"] = result
        if detail is not None:
            entry["detail"] = detail
        if inspection is not None:
            entry["inspection"] = inspection
        self._current_candidate["trace"].append(entry)

    def record_energy_filter(
        self,
        speech_duration: float,
        clip_duration: float,
        threshold: float,
        passed: bool,
    ) -> None:
        """Record energy filter result on the current candidate."""
        ratio = round(speech_duration / clip_duration, 3) if clip_duration > 0 else 0.0
        inspection = {
            "speech_duration": round(speech_duration, 3),
            "clip_duration": round(clip_duration, 3),
            "actual_ratio": ratio,
            "threshold": threshold,
            "verdict": f"{ratio} {'≥' if passed else '<'} {threshold} → {'passed' if passed else 'failed'}",
        }
        self.record_trace_step(
            "energy_filter",
            result="passed" if passed else "failed",
            inspection=inspection,
        )

    def record_stopping_point(self, point_data: dict) -> None:
        """Record an evaluated stopping point for the current candidate."""
        if self._current_candidate is not None:
            self._current_candidate["stopping_points"].append(point_data)

    def finalize_candidate(
        self,
        window_end: float,
        metrics: dict,
        start_analysis: dict,
        end_analysis: dict,
    ) -> None:
        """Close out the current candidate with computed data."""
        if self._current_candidate is None:
            return

        c = self._current_candidate
        c["window_end"] = round(window_end, 3)
        c["duration"] = round(window_end - c["window_start"], 3)
        c["metrics"] = metrics
        c["start_analysis"] = start_analysis
        c["end_analysis"] = end_analysis

        # Mark the best stopping point
        if c["stopping_points"]:
            best_score = max(sp["total_score"] for sp in c["stopping_points"])
            for sp in c["stopping_points"]:
                sp["selected"] = (
                    sp["total_score"] == best_score
                    and sp["timestamp"] == end_analysis.get("timestamp")
                )

        self.record_trace_step(
            "stopping_point_evaluation",
            detail=f"{len(c['stopping_points'])} points evaluated, "
                   f"best score {end_analysis.get('total_score', '?')} at {window_end:.1f}s",
        )

        self.candidates.append(c)
        self._current_candidate = None

    # ------------------------------------------------------------------
    # Filtered windows (never became candidates)
    # ------------------------------------------------------------------

    def record_filtered_window(
        self,
        window_start: float,
        window_end: Optional[float],
        reason: str,
        detail: str,
        inspection: Optional[dict] = None,
    ) -> None:
        """Record a window that was filtered out before becoming a candidate."""
        entry: dict[str, Any] = {
            "window_start": round(window_start, 3),
            "window_end": round(window_end, 3) if window_end is not None else None,
            "reason": reason,
            "detail": detail,
        }
        if inspection is not None:
            entry["inspection"] = inspection
        self.filtered_windows.append(entry)

    # ------------------------------------------------------------------
    # Global decision log
    # ------------------------------------------------------------------

    def record_decision(self, step: int, event: str, detail: str) -> None:
        """Record a global pipeline decision (not per-candidate)."""
        self.decision_log.append({
            "step": step,
            "event": event,
            "detail": detail,
        })

    # ------------------------------------------------------------------
    # Selection / rejection (called during ranked selection phase)
    # ------------------------------------------------------------------

    def mark_candidate_selected(self, candidate_id: int, rank: int) -> None:
        """Mark a candidate as selected in the final output."""
        for c in self.candidates:
            if c["id"] == candidate_id:
                c["selected"] = True
                c["final_rank"] = rank
                c["trace"].append({
                    "step": "selection",
                    "result": "selected",
                    "detail": f"Selected as clip (rank #{rank})",
                })
                break

    def mark_candidate_rejected(
        self,
        candidate_id: int,
        rank: int,
        reason: str,
        detail: str,
    ) -> None:
        """Mark a candidate as rejected with a reason."""
        for c in self.candidates:
            if c["id"] == candidate_id:
                c["final_rank"] = rank
                c["rejection_reason"] = reason
                c["trace"].append({
                    "step": "selection",
                    "result": "rejected",
                    "reason": reason,
                    "detail": detail,
                })
                break

    # ------------------------------------------------------------------
    # Final clips
    # ------------------------------------------------------------------

    def record_final_clip(self, clip_data: dict) -> None:
        """Record a final selected clip with its explanation."""
        self.final_clips.append(clip_data)

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------

    def compute_stats(self) -> dict:
        """Compute aggregate statistics from collected data."""
        all_candidates = self.candidates
        selected = [c for c in all_candidates if c["selected"]]
        rejected = [c for c in all_candidates if not c["selected"]]

        # Rejection breakdown
        rejection_breakdown: dict[str, int] = {}
        for c in rejected:
            reason = c.get("rejection_reason") or "unknown"
            rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1

        # Filter breakdown
        filter_breakdown: dict[str, int] = {}
        for fw in self.filtered_windows:
            reason = fw.get("reason", "unknown")
            filter_breakdown[reason] = filter_breakdown.get(reason, 0) + 1

        # Duration stats (from selected clips)
        durations = [c["duration"] for c in all_candidates if c["duration"] is not None]
        duration_stats = self._compute_numeric_stats(durations)

        # Duration distribution buckets
        duration_dist = [
            {"range": "8-10s", "count": sum(1 for d in durations if 8 <= d < 10)},
            {"range": "10-12s", "count": sum(1 for d in durations if 10 <= d < 12)},
            {"range": "12-14s", "count": sum(1 for d in durations if 12 <= d < 14)},
            {"range": "14-16s", "count": sum(1 for d in durations if 14 <= d < 16)},
            {"range": "16-18s", "count": sum(1 for d in durations if 16 <= d < 18)},
            {"range": "18-20s", "count": sum(1 for d in durations if 18 <= d <= 20)},
        ]
        duration_stats["distribution"] = duration_dist

        # Word density stats
        word_densities = [
            c["metrics"].get("word_density", 0)
            for c in all_candidates
            if c["metrics"].get("word_density") is not None
        ]
        word_density_stats = self._compute_numeric_stats(word_densities)

        # Speech ratio stats
        speech_ratios = [
            c["metrics"].get("speech_ratio", 0)
            for c in all_candidates
            if c["metrics"].get("speech_ratio") is not None
        ]
        speech_ratio_stats = self._compute_numeric_stats(speech_ratios)

        # Stop score stats
        stop_scores = []
        for c in all_candidates:
            if c.get("end_analysis") and c["end_analysis"].get("total_score") is not None:
                stop_scores.append(c["end_analysis"]["total_score"])

        stop_score_stats = self._compute_numeric_stats(stop_scores)
        if stop_scores:
            score_range = range(
                int(min(stop_scores)),
                int(max(stop_scores)) + 1,
            )
            stop_score_stats["distribution"] = [
                {"score": s, "count": stop_scores.count(s)}
                for s in score_range
            ]

        # Count clips from fallback / duplicated
        clips_from_fallback = sum(
            1 for fc in self.final_clips
            if fc.get("from_fallback", False)
        )
        clips_duplicated = sum(
            1 for fc in self.final_clips
            if fc.get("duplicated", False)
        )

        return {
            "total_windows_evaluated": len(all_candidates) + len(self.filtered_windows),
            "total_candidates": len(all_candidates),
            "unique_after_dedup": len(all_candidates),  # updated during dedup phase
            "selected": len(selected),
            "rejected": len(rejected),
            "from_fallback": clips_from_fallback,
            "duplicated": clips_duplicated,
            "rejection_breakdown": rejection_breakdown,
            "filter_breakdown": filter_breakdown,
            "duration": duration_stats,
            "word_density": word_density_stats,
            "speech_ratio": speech_ratio_stats,
            "stop_scores": stop_score_stats,
        }

    @staticmethod
    def _compute_numeric_stats(values: list[float]) -> dict:
        """Compute min/max/mean for a list of numbers."""
        if not values:
            return {"min": None, "max": None, "mean": None}
        return {
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "mean": round(statistics.mean(values), 3),
        }

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return the full analysis.json payload."""
        return {
            "meta": self.meta,
            "transcript": self.transcript,
            "candidates": self.candidates,
            "filtered_windows": self.filtered_windows,
            "decision_log": self.decision_log,
            "final_clips": self.final_clips,
            "stats": self.compute_stats(),
        }

    def save(self, output_dir: Path) -> Path:
        """Write analysis.json to *output_dir*. Returns the file path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "analysis.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path
