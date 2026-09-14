"""
Golden (characterization) tests for the legacy_v2 selection engine.

These tests pin what `select_segments` does TODAY, defects included, so that:
  * the legacy engine stays available as an unchanged baseline (decision D19), and
  * any accidental change to it is caught.

They are not a statement that this behaviour is correct.

To intentionally re-record goldens (only with approval, e.g. a deliberate
legacy change):  UPDATE_LEGACY_GOLDEN=1 pytest tests/legacy
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from services.segment_selection import select_segments

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"
UPDATE = os.environ.get("UPDATE_LEGACY_GOLDEN") == "1"

FIXTURE_NAMES = sorted(p.stem for p in FIXTURES.glob("*.json"))
CLIP_COUNTS = (3, 5)  # legacy_v2@3 = historical, legacy_v2@5 = fair comparison (D23)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _canonical_hash(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def snapshot(fixture: dict, max_clips: int) -> dict:
    """Deterministic, reviewable summary of one legacy_v2 run."""
    try:
        selected, analysis = select_segments(
            copy.deepcopy(fixture["segments"]),
            fixture["video_duration"],
            max_clips=max_clips,
            collect_analysis=True,
        )
    except Exception as exc:
        # Legacy behaviour worth pinning: the pipeline always calls with
        # collect_analysis=True, and AnalysisCollector reads raw segments before
        # select_segments validates them, so malformed input raises there.
        return {
            "analysis_mode_raises": f"{type(exc).__name__}: {exc}",
            "selected_without_analysis": select_segments(
                copy.deepcopy(fixture["segments"]),
                fixture["video_duration"],
                max_clips=max_clips,
            ),
        }
    return {
        "selected": selected,
        "final_clips": analysis["final_clips"],
        "decision_log": analysis["decision_log"],
        "stats": analysis["stats"],
        "counts": {
            "transcript_segments": len(analysis["transcript"]),
            "candidates": len(analysis["candidates"]),
            "filtered_windows": len(analysis["filtered_windows"]),
        },
        # Full candidate/filter traces are large; hashing them still detects any change.
        "candidates_sha256": _canonical_hash(analysis["candidates"]),
        "filtered_windows_sha256": _canonical_hash(analysis["filtered_windows"]),
        "config": analysis["meta"]["config"],
        "algorithm_version": analysis["meta"]["algorithm_version"],
    }


@pytest.mark.parametrize("max_clips", CLIP_COUNTS)
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_legacy_v2_matches_golden(name, max_clips):
    actual = json.loads(json.dumps(snapshot(load_fixture(name), max_clips), ensure_ascii=False))
    golden_path = GOLDEN / f"{name}@{max_clips}.json"

    if UPDATE:
        GOLDEN.mkdir(exist_ok=True)
        golden_path.write_text(json.dumps(actual, ensure_ascii=False, indent=1), encoding="utf-8")
        pytest.skip(f"re-recorded {golden_path.name}")

    assert golden_path.exists(), f"missing golden {golden_path.name}; record with UPDATE_LEGACY_GOLDEN=1"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected, f"legacy_v2 output changed for {name}@{max_clips}"


def test_every_fixture_has_goldens_for_both_clip_counts():
    if UPDATE:
        pytest.skip("recording")
    missing = [f"{n}@{k}" for n in FIXTURE_NAMES for k in CLIP_COUNTS
               if not (GOLDEN / f"{n}@{k}.json").exists()]
    assert not missing
