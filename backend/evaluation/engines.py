"""
Selection engines available to the evaluation runner.

An engine spec is "<name>@<clip_count>", e.g. "legacy_v2@3" (historical
behaviour), "legacy_v2@5" (fair comparison with the 5-clip target) or
"boundary_v1@5" (Phase 6 engine).

Engines come from the production registry (services/selection/registry.py), so
the harness evaluates exactly what the app runs. Every engine gets the same
inputs, so comparisons isolate selection:

    run_engine(spec, transcript, video_duration, audio_path=None) -> EngineResult
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from services.selection.registry import ENGINES, SelectionInput, SelectionResult
from services.selection.registry import run as run_selection

_SPEC_RE = re.compile(r"^(?P<name>[a-z][a-z0-9_+]*)@(?P<count>[1-9][0-9]?)$")

EngineResult = SelectionResult


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
    if name not in ENGINES:
        raise ValueError(f"unknown engine {name!r}; available: {sorted(ENGINES)}")
    return EngineSpec(name, int(match["count"]))


def run_engine(spec: EngineSpec, transcript, video_duration: float,
               audio_path: Optional[str] = None) -> EngineResult:
    return run_selection(spec.name, SelectionInput(
        transcript=transcript, video_duration=video_duration, clip_count=spec.clip_count,
        audio_path=audio_path,
    ))
