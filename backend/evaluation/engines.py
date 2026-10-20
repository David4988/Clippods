"""
Selection engines available to the evaluation runner.

An engine spec is "<name>@<clip_count>", e.g. "legacy_v2@3" (historical
behaviour), "legacy_v2@5" (fair comparison with the 5-clip target) or
"boundary_v1@5" (Phase 6 engine).

Engines come from the production registry (services/selection/registry.py), so
the harness evaluates exactly what the app runs, plus evaluation-only baselines
listed in EVAL_ENGINES. Every engine gets the same inputs, so comparisons
isolate selection:

    run_engine(spec, transcript, video_duration, audio_path=None) -> EngineResult
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from services.selection.registry import ENGINES, SelectionInput, SelectionResult

_SPEC_RE = re.compile(r"^(?P<name>[a-z][a-z0-9_+]*)@(?P<count>[1-9][0-9]?)$")

EngineResult = SelectionResult

# legacy_v2's duration constants scaled from 15–20 s clips to ~8–10 s.
LEGACY_10S = {"MIN_DURATION": 6.0, "PREF_MIN_DURATION": 7.0, "PREF_MAX_DURATION": 7.0,
              "MAX_DURATION": 10.0, "BUFFER": 1.0}


def _legacy_v2_10s(inp: SelectionInput) -> SelectionResult:
    """
    Evaluation-only: legacy_v2 with ~10 s clips, so a listening A/B against
    boundary_v1 (D7: ~10 s) compares moments and cuts rather than length. The
    legacy code is unchanged; its module constants are swapped for this call only.
    """
    from unittest.mock import patch

    from services import segment_selection

    with patch.multiple(segment_selection, **LEGACY_10S):
        result = ENGINES["legacy_v2"](inp)
    return SelectionResult(result.clips, result.analysis, result.engine_version + "+10s")


EVAL_ENGINES = {**ENGINES, "legacy_v2_10s": _legacy_v2_10s}


@dataclass(frozen=True)
class EngineSpec:
    name: str
    clip_count: int

    @property
    def label(self) -> str:
        return f"{self.name}@{self.clip_count}"


def parse_engine_spec(spec: str) -> EngineSpec:
    match = _SPEC_RE.match(spec.strip())
    if not match:
        raise ValueError(f"engine spec must look like 'legacy_v2@5', got {spec!r}")
    name = match["name"]
    if name not in EVAL_ENGINES:
        raise ValueError(f"unknown engine {name!r}; available: {sorted(EVAL_ENGINES)}")
    return EngineSpec(name, int(match["count"]))


def run_engine(spec: EngineSpec, transcript, video_duration: float,
               audio_path: Optional[str] = None) -> EngineResult:
    return EVAL_ENGINES[spec.name](SelectionInput(
        transcript=transcript, video_duration=video_duration, clip_count=spec.clip_count,
        audio_path=audio_path,
    ))
