"""
Evaluation runner.

Run layout (outside git, never touched by the production GC):

    <eval_dir>/runs/<run_id>/
      run.json                      what was run: dataset, engines, git state,
                                    library versions, machine, status, errors
      summary.json                  one row per item × engine (metrics digest)
      items/<item_id>/
        stages.json                 cache key, hit/miss and build facts per stage
        <engine_label>/
          selection.json            the clips the engine chose
          analysis.json             the engine's full trace (debugger payload)
          metrics.json              automatic metrics (evaluation.metrics)
          clips/                    rendered MP4s, only with --render

Promoting a run copies the small JSON (not analysis traces, clips or media)
into backend/evaluation/results/<run_id>/ so approved results are versioned.
"""
from __future__ import annotations

import platform
import secrets
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from evaluation import stages
from evaluation.cache import StageCache
from evaluation.dataset import Dataset, verify_media
from evaluation.engines import EngineSpec, run_engine
from evaluation.metrics import selection_metrics
from evaluation.resources import Measure
from evaluation.storage import BACKEND_DIR, REPO_DIR, read_json, runs_dir, write_json

RUN_SCHEMA = "clippods-eval-run/1"
RESULTS_DIR = BACKEND_DIR / "evaluation" / "results"


@dataclass
class RunOptions:
    engines: list[EngineSpec]
    use_cache: bool = True
    render: bool = False
    item_ids: list[str] | None = None
    note: str = ""


@dataclass
class RunOutcome:
    run_id: str
    run_dir: Path
    failed_items: list[str] = field(default_factory=list)


def _git_state() -> dict:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], cwd=REPO_DIR, capture_output=True,
                                  text=True, timeout=10, check=True).stdout.strip()
        except Exception:
            return None
    status = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def _environment() -> dict:
    import psutil
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "packages": {name: stages._package_version(name) for name in
                     ("faster-whisper", "ctranslate2", "onnxruntime", "ffmpeg-python", "yt-dlp")},
    }


def new_run_id(dataset: Dataset) -> str:
    return f"{time.strftime('%Y%m%dT%H%M%S')}-{dataset.label}-{secrets.token_hex(3)}"


def run_evaluation(dataset: Dataset, options: RunOptions, log=print) -> RunOutcome:
    cache = StageCache(enabled=options.use_cache)
    run_id = new_run_id(dataset)
    run_dir = runs_dir() / run_id
    run_dir.mkdir(parents=True)

    items = dataset.items
    if options.item_ids:
        unknown = set(options.item_ids) - {i.id for i in items}
        if unknown:
            raise ValueError(f"unknown item ids: {sorted(unknown)}")
        items = [i for i in items if i.id in options.item_ids]

    run = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "status": "running",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "finished_at": None,
        "note": options.note,
        "dataset": {"name": dataset.name, "version": dataset.version, "frozen": dataset.frozen,
                    "manifest": str(dataset.manifest_path) if dataset.manifest_path else None,
                    "manifest_sha256": dataset.manifest_sha256,
                    "items": [i.id for i in items]},
        "engines": [e.label for e in options.engines],
        "options": {"use_cache": options.use_cache, "render": options.render},
        "git": _git_state(),
        "environment": _environment(),
        "items": {},
    }
    write_json(run_dir / "run.json", run)

    summary_rows = []
    outcome = RunOutcome(run_id, run_dir)

    for item in items:
        log(f"[{item.id}] start")
        item_dir = run_dir / "items" / item.id
        item_record: dict = {"status": "running", "stages": {}, "engines": {}}
        run["items"][item.id] = item_record
        try:
            with Measure() as total:
                media_sha = verify_media(item)

                probe = stages.run_probe(cache, item.media_path, media_sha)
                duration = probe.entry["build"]["duration_s"]
                if not probe.entry["build"]["has_audio"]:
                    raise stages.StageError("media has no audio stream")
                log(f"[{item.id}] probe {'hit' if probe.hit else 'built'} ({duration:.1f}s media)")

                audio = stages.run_audio(cache, item.media_path, media_sha)
                log(f"[{item.id}] audio {'hit' if audio.hit else 'built'}")

                transcript_res = stages.run_transcript_legacy(cache, audio, duration)
                log(f"[{item.id}] transcript_legacy {'hit' if transcript_res.hit else 'built'} "
                    f"({transcript_res.entry['build']['segment_count']} segments, "
                    f"{transcript_res.entry['build']['wall_s']}s to build)")
                transcript = stages.load_transcript(transcript_res)

                stage_records = {
                    res.stage: {"key": res.key, "cache_hit": res.hit, "build": res.entry["build"],
                                "config": res.entry["config"]}
                    for res in (probe, audio, transcript_res)
                }
                stage_records["transcript_legacy"]["language_mode_requested"] = item.language_mode
                stage_records["transcript_legacy"]["language_mode_honoured"] = False
                item_record["stages"] = stage_records
                write_json(item_dir / "stages.json", stage_records)

                for spec in options.engines:
                    engine_dir = item_dir / spec.label
                    with Measure() as m:
                        result = run_engine(spec, transcript, duration)
                    metrics = selection_metrics(result.clips, spec.clip_count, duration, result.analysis)
                    metrics["engine_wall_s"] = m.wall_s

                    clip_files: list[str] = []
                    if options.render:
                        clip_files = _render(item.media_path, result.clips, engine_dir / "clips")

                    write_json(engine_dir / "selection.json", {
                        "engine": spec.label, "engine_version": result.engine_version,
                        "item_id": item.id, "video_duration_s": duration,
                        "clips": [{**c, "rank_in_output": idx, "file": clip_files[idx] if clip_files else None}
                                  for idx, c in enumerate(result.clips)],
                    })
                    if result.analysis is not None:
                        write_json(engine_dir / "analysis.json", result.analysis)
                    write_json(engine_dir / "metrics.json", metrics)

                    item_record["engines"][spec.label] = {"engine_version": result.engine_version,
                                                          "wall_s": m.wall_s}
                    summary_rows.append(_summary_row(item.id, spec.label, duration, stage_records, metrics))
                    log(f"[{item.id}] {spec.label}: {metrics['clip_count']} clips, "
                        f"{metrics['identical_pairs']} identical pairs, "
                        f"{metrics['overlapping_pairs']} overlapping pairs")

            item_record["status"] = "ok"
            item_record["total"] = total.as_dict()
        except Exception as exc:
            item_record["status"] = "error"
            item_record["error"] = f"{type(exc).__name__}: {exc}"
            item_record["traceback"] = traceback.format_exc()
            outcome.failed_items.append(item.id)
            log(f"[{item.id}] ERROR {type(exc).__name__}: {exc}")
        finally:
            write_json(run_dir / "run.json", run)

    run["status"] = "completed_with_errors" if outcome.failed_items else "completed"
    run["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_json(run_dir / "run.json", run)
    write_json(run_dir / "summary.json", {"run_id": run_id, "rows": summary_rows})
    return outcome


def _summary_row(item_id: str, engine: str, duration: float, stage_records: dict, metrics: dict) -> dict:
    asr = stage_records["transcript_legacy"]["build"]
    return {
        "item": item_id,
        "engine": engine,
        "video_duration_s": duration,
        "asr_wall_s": asr.get("wall_s"),
        "asr_rtf": asr.get("real_time_factor"),
        "asr_cache_hit": stage_records["transcript_legacy"]["cache_hit"],
        "clip_count": metrics["clip_count"],
        "distinct_spans": metrics["distinct_spans"],
        "identical_pairs": metrics["identical_pairs"],
        "overlapping_pairs": metrics["overlapping_pairs"],
        "duration_min_s": metrics["duration_s"]["min"],
        "duration_max_s": metrics["duration_s"]["max"],
        "clips_from_fallback": metrics.get("legacy", {}).get("clips_from_fallback"),
    }


def _render(media_path: Path, clips: list[dict], dest: Path) -> list[str]:
    """Cut clips with the production renderer, then move them out of OUTPUTS_DIR."""
    from services.clip_generation import generate_clips

    paths = [Path(p) for p in generate_clips(str(media_path), clips)]
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for idx, p in enumerate(paths):
        target = dest / f"clip_{idx}.mp4"
        shutil.move(str(p), target)
        moved.append(target.name)
    if paths:
        shutil.rmtree(paths[0].parent, ignore_errors=True)
    return moved


def promote_run(run_id: str) -> Path:
    """Copy a run's small, reviewable JSON into git-tracked results/."""
    src = runs_dir() / run_id
    if not (src / "run.json").exists():
        raise FileNotFoundError(f"no run {run_id!r} under {runs_dir()}")
    run = read_json(src / "run.json")
    if run.get("status") == "running":
        raise ValueError(f"run {run_id!r} has not finished")

    dest = RESULTS_DIR / run_id
    if dest.exists():
        raise FileExistsError(f"{dest} already exists; results are immutable once promoted")
    dest.mkdir(parents=True)
    # Tracebacks contain absolute local paths; keep them out of git.
    items = {item_id: {k: v for k, v in record.items() if k != "traceback"}
             for item_id, record in run.get("items", {}).items()}
    write_json(dest / "run.json", {**run, "items": items})
    if (src / "summary.json").exists():
        shutil.copy2(src / "summary.json", dest / "summary.json")
    for item_dir in (src / "items").glob("*"):
        for f in item_dir.glob("stages.json"):
            (dest / "items" / item_dir.name).mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / "items" / item_dir.name / f.name)
        for engine_dir in (p for p in item_dir.iterdir() if p.is_dir()):
            for name in ("selection.json", "metrics.json"):
                if (engine_dir / name).exists():
                    target = dest / "items" / item_dir.name / engine_dir.name
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(engine_dir / name, target / name)
    return dest
