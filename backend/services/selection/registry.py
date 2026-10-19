"""
services/selection/registry.py — one registry of clip-selection engines.

Used by the offline evaluation harness (evaluation/engines.py). The production
router keeps calling the legacy `select_segments` directly (its tests patch that
name) and calls boundary_v1 through `run("boundary_v1", ...)` when
SELECTION_ENGINE says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class SelectionInput:
    transcript: Any                   # services.transcript.Transcript
    video_duration: float
    clip_count: int
    structure: Any = None             # services.speech_structure.SpeechStructure (built if absent)
    audio_path: Optional[str] = None  # 16 kHz mono WAV for loudness features


@dataclass
class SelectionResult:
    clips: list[dict]                 # [{"start", "end", ...}] in output order
    analysis: Optional[dict]          # engine-specific trace (debugger payload)
    engine_version: str


def _legacy_v2(inp: SelectionInput) -> SelectionResult:
    from services.analysis_constants import ALGORITHM_VERSION
    from services.segment_selection import select_segments

    selected, analysis = select_segments(
        inp.transcript.legacy_segments(),   # the only view legacy_v2 understands
        inp.video_duration, max_clips=inp.clip_count, collect_analysis=True,
    )
    return SelectionResult(clips=selected, analysis=analysis, engine_version=ALGORITHM_VERSION)


def _boundary_v1(inp: SelectionInput) -> SelectionResult:
    from services.selection import boundary_v1
    from services.speech_structure import build_speech_structure

    structure = inp.structure if inp.structure is not None else build_speech_structure(inp.transcript)
    clips, analysis = boundary_v1.select(inp.transcript, structure, inp.video_duration,
                                         inp.clip_count, audio_path=inp.audio_path)
    return SelectionResult(clips=clips, analysis=analysis, engine_version=boundary_v1.ENGINE_VERSION)


ENGINES: dict[str, Callable[[SelectionInput], SelectionResult]] = {
    "legacy_v2": _legacy_v2,
    "boundary_v1": _boundary_v1,
}


def run(name: str, inp: SelectionInput) -> SelectionResult:
    try:
        engine = ENGINES[name]
    except KeyError:
        raise ValueError(f"unknown selection engine {name!r}; available: {sorted(ENGINES)}") from None
    return engine(inp)
