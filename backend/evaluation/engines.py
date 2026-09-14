"""
Selection engines available to the evaluation runner.

An engine spec is "<name>@<clip_count>", e.g. "legacy_v2@3" (historical
behaviour) or "legacy_v2@5" (fair comparison with the 5-clip target, D23).

Every engine takes the same inputs so that comparisons isolate selection:

    run(transcript: Transcript, video_duration: float, clip_count: int) -> EngineResult

Phase 0 registers only legacy_v2, which calls the production
`select_segments` unchanged. New engines (boundary_v1, boundary_v1+semantic)
are added in later phases behind the same interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_SPEC_RE = re.compile(r"^(?P<name>[a-z][a-z0-9_+]*)@(?P<count>[1-9][0-9]?)$")


@dataclass(frozen=True)
class EngineSpec:
    name: str
    clip_count: int

    @property
    def label(self) -> str:
        return f"{self.name}@{self.clip_count}"


@dataclass
class EngineResult:
    clips: list[dict]          # [{"start": float, "end": float, ...}] in output order
    analysis: dict | None      # engine-specific trace (debugger payload)
    engine_version: str


def parse_engine_spec(spec: str) -> EngineSpec:
    match = _SPEC_RE.match(spec.strip())
    if not match:
        raise ValueError(f"engine spec must look like 'legacy_v2@5', got {spec!r}")
    name = match["name"]
    if name not in ENGINES:
        raise ValueError(f"unknown engine {name!r}; available: {sorted(ENGINES)}")
    return EngineSpec(name, int(match["count"]))


def _run_legacy_v2(transcript, video_duration: float, clip_count: int) -> EngineResult:
    from services.analysis_constants import ALGORITHM_VERSION
    from services.segment_selection import select_segments

    selected, analysis = select_segments(
        transcript.legacy_segments(),  # the only view legacy_v2 understands
        video_duration,
        max_clips=clip_count,
        collect_analysis=True,
    )
    return EngineResult(clips=selected, analysis=analysis, engine_version=ALGORITHM_VERSION)


ENGINES: dict[str, Callable[..., EngineResult]] = {
    "legacy_v2": _run_legacy_v2,
}


def run_engine(spec: EngineSpec, transcript, video_duration: float) -> EngineResult:
    return ENGINES[spec.name](transcript, video_duration, spec.clip_count)
