"""
Phase 1 regression tests: backend correctness and observability.

Each test names the master-plan problem it covers. None of these change clip
selection; legacy selection is pinned separately in tests/legacy.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import config
import job_manager
from main import app
from services import transcription
from tests.legacy.test_legacy_v2_golden import load_fixture
from utils import write_json_atomic

client = TestClient(app)
BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _wait(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/status/{job_id}").json()
        if body.get("status") in ("completed", "error", "cancelled"):
            return body
        time.sleep(0.05)
    raise TimeoutError(job_id)


def _fake_clip_paths(selected):
    run_dir = config.OUTPUTS_DIR / os.urandom(16).hex()
    run_dir.mkdir(parents=True)
    paths = []
    for i, _ in enumerate(selected):
        p = run_dir / f"{run_dir.name}_clip_{i}.mp4"
        p.write_bytes(b"\x00" * 32)
        paths.append(str(p))
    return paths


def _pipeline(tmp_path, *, segments, duration="300.0", transcribe_side_effect=None,
              generate_side_effect=None):
    """Patch the media-touching services; keep the REAL select_segments."""
    import ffmpeg as ffmpeg_module
    transcribe_kwargs = ({"side_effect": transcribe_side_effect} if transcribe_side_effect
                         else {"return_value": {"segments": segments}})
    return [
        patch("routers.video.get_video_input", new=AsyncMock(return_value=tmp_path / "video.mp4")),
        patch.object(ffmpeg_module, "probe", return_value={"format": {"duration": duration}}),
        patch("routers.video.extract_audio", return_value=str(tmp_path / "audio.wav")),
        patch("routers.video.transcribe", **transcribe_kwargs),
        patch("routers.video.generate_clips", side_effect=generate_side_effect
              or (lambda video, selected, job_id=None: _fake_clip_paths(selected))),
    ]


def _run_url_job(patches) -> dict:
    for p in patches:
        p.start()
    try:
        job_id = client.post("/process", json={"video_url": "https://example.com/v"}).json()["job_id"]
        return _wait(job_id)
    finally:
        for p in patches:
            p.stop()


def _analysis_for(job: dict) -> dict:
    path = config.OUTPUTS_DIR / job["run_uuid"] / "analysis.json"
    return json.loads(path.read_bytes().decode("utf-8"))


# ---------------------------------------------------------------------------
# P-OBS-1: analysis.json is UTF-8 and atomic
# ---------------------------------------------------------------------------

def test_write_json_atomic_handles_indic_text_and_arrows(tmp_path):
    data = {"hi": "असली वजह यह है।", "ta": "யாரும் பேசுவதில்லை.", "trace": "5.0s → 20.0s ≥ 0.6"}
    path = write_json_atomic(tmp_path / "analysis.json", data)
    assert json.loads(path.read_bytes().decode("utf-8")) == data


def test_write_json_atomic_keeps_previous_file_when_serialisation_fails(tmp_path):
    path = write_json_atomic(tmp_path / "analysis.json", {"v": 1})
    with pytest.raises(TypeError):
        write_json_atomic(path, {"v": object()})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["analysis.json"]


def test_completed_run_saves_readable_analysis_with_pipeline_record(tmp_path):
    fx = load_fixture("hindi_danda_5min")
    job = _run_url_job(_pipeline(tmp_path, segments=fx["segments"]))
    assert job["status"] == "completed", job
    assert job["warnings"] == []

    analysis = _analysis_for(job)
    assert analysis["meta"]["job_id"] and analysis["final_clips"]
    assert any("।" in seg["text"] for seg in analysis["transcript"])
    pipeline = analysis["pipeline"]
    assert pipeline["status"] == "completed" and pipeline["failed_stage"] is None
    assert [s["stage"] for s in pipeline["stages"]] == [
        "download", "probe", "extract_audio", "transcribe", "select_segments", "generate_clips"]
    assert all(s["ok"] and s["wall_s"] is not None for s in pipeline["stages"])


def test_analysis_write_failure_is_visible_on_the_job(tmp_path):
    fx = load_fixture("english_podcast_10min")
    patches = _pipeline(tmp_path, segments=fx["segments"], duration="600.0")
    patches.append(patch("routers.video.write_json_atomic", side_effect=OSError("disk full")))
    job = _run_url_job(patches)
    assert job["status"] == "completed"
    assert len(job["warnings"]) == 1 and "disk full" in job["warnings"][0]


def test_completed_run_selection_is_unchanged_by_the_pipeline_changes(tmp_path):
    """The router still calls legacy select_segments with the same inputs."""
    from tests.legacy.test_legacy_v2_golden import GOLDEN
    fx = load_fixture("english_podcast_10min")
    job = _run_url_job(_pipeline(tmp_path, segments=fx["segments"], duration="600.0"))
    golden = json.loads((GOLDEN / "english_podcast_10min@3.json").read_text(encoding="utf-8"))
    assert [(c["start"], c["end"]) for c in _analysis_for(job)["final_clips"]] == \
        [(c["start"], c["end"]) for c in golden["selected"]]


# ---------------------------------------------------------------------------
# P-OBS-2: failed and cancelled runs leave an analysis record
# ---------------------------------------------------------------------------

def test_failed_run_records_stage_and_error(tmp_path, monkeypatch):
    boom = HTTPException(status_code=502, detail="Transcription failed: RuntimeError: decoder exploded")
    job = _run_url_job(_pipeline(tmp_path, segments=[], transcribe_side_effect=boom))
    assert job["status"] == "error"
    assert job["run_uuid"]

    analysis = _analysis_for(job)
    assert analysis["pipeline"]["status"] == "error"
    assert analysis["pipeline"]["failed_stage"] == "transcribe"
    assert "decoder exploded" in analysis["pipeline"]["error"]
    assert analysis["final_clips"] == [] and analysis["candidates"] == []

    monkeypatch.setattr(config, "ENABLE_DEBUGGER", True)
    listed = {j["run_uuid"]: j for j in client.get("/dev/analysis/jobs").json()["jobs"]}
    assert listed[job["run_uuid"]]["pipeline_status"] == "error"


def test_late_cancel_removes_rendered_clips_and_records_cancellation(tmp_path, monkeypatch):
    # Runs through the real threaded worker: the pytest-only synchronous route
    # bypass reports cancelled jobs as "error" (P-REL-7), production does not.
    from services.job_worker import worker_pool
    monkeypatch.setattr(worker_pool, "synchronous", False)
    fx = load_fixture("english_podcast_10min")
    rendered = {}

    def render_then_cancel(video, selected, job_id=None):
        paths = _fake_clip_paths(selected)
        rendered["dir"] = Path(paths[0]).parent
        job_manager.cancel_job(job_id)
        return paths

    patches = _pipeline(tmp_path, segments=fx["segments"], duration="600.0",
                        generate_side_effect=render_then_cancel)
    job = _run_url_job(patches)
    assert job["status"] == "cancelled"
    assert not rendered["dir"].exists()
    assert _analysis_for(job)["pipeline"]["status"] == "cancelled"


def test_max_video_duration_comes_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 60.0)
    job = _run_url_job(_pipeline(tmp_path, segments=[], duration="61.0"))
    assert job["status"] == "error" and job["error"] == "Video too long (max 1 minute)"
    assert _analysis_for(job)["pipeline"]["failed_stage"] == "probe"


# ---------------------------------------------------------------------------
# P-REL-1: .env is loaded before settings are read
# ---------------------------------------------------------------------------

def _python_with_env_file(tmp_path, env_text: str, extra_env: dict | None = None) -> str:
    env_file = tmp_path / "test.env"
    env_file.write_text(env_text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLIPPODS_DISABLE_DOTENV", "ENABLE_DEBUGGER", "MAX_CONCURRENT_JOBS")}
    env["CLIPPODS_ENV_FILE"] = str(env_file)
    env.update(extra_env or {})
    code = ("import main, config, routers.analysis as a; "
            "print(config.ENABLE_DEBUGGER, config.MAX_CONCURRENT_JOBS, main.ENABLE_DEBUGGER, a.config.ENABLE_DEBUGGER)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


def test_env_file_values_take_effect_when_importing_main(tmp_path):
    assert _python_with_env_file(tmp_path, "ENABLE_DEBUGGER=true\nMAX_CONCURRENT_JOBS=7\n") == "True 7 True True"


def test_real_environment_variables_override_env_file(tmp_path):
    line = _python_with_env_file(tmp_path, "MAX_CONCURRENT_JOBS=7\n", {"MAX_CONCURRENT_JOBS": "3"})
    assert line.split()[1] == "3"


# ---------------------------------------------------------------------------
# Issue 15 / P-REL-2 / P-REL-3: transcription failures, progress, cancellation
# ---------------------------------------------------------------------------

def _audio(tmp_path) -> str:
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF....WAVEfmt ")
    return str(p)


def _model(segments, duration=None, consumed=None):
    def generator():
        for seg in segments:
            if isinstance(seg, Exception):
                raise seg
            if consumed is not None:
                consumed.append(seg)
            yield seg

    model = SimpleNamespace()
    model.transcribe = lambda *a, **k: (generator(), SimpleNamespace(language="en", duration=duration))
    return model


def _seg(start, end, text="x"):
    return SimpleNamespace(start=start, end=end, text=text)


def test_unavailable_model_raises_instead_of_returning_a_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(transcription, "get_model", lambda: None)
    monkeypatch.setattr(transcription, "_model_load_error", "ImportError: No module named 'av'")
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe(_audio(tmp_path))
    assert exc.value.status_code == 503
    assert "No module named 'av'" in exc.value.detail


def test_model_load_failure_is_retried(monkeypatch):
    attempts = []

    class FlakyWhisper:
        def __init__(self, *a, **k):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("download interrupted")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FlakyWhisper))
    monkeypatch.setattr(transcription, "_model", None)
    assert transcription.get_model() is None
    assert "download interrupted" in transcription._model_load_error
    assert isinstance(transcription.get_model(), FlakyWhisper)
    assert len(attempts) == 2


def test_error_while_decoding_keeps_the_cause(tmp_path, monkeypatch):
    model = _model([_seg(0, 1), RuntimeError("CUDA-less decoder crashed mid-stream")])
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe(_audio(tmp_path))
    assert exc.value.status_code == 502
    assert "decoder crashed mid-stream" in exc.value.detail


def test_cancellation_stops_transcription_between_segments(tmp_path, monkeypatch):
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="transcribing")
    consumed = []
    segments = [_seg(i, i + 1) for i in range(50)]
    model = _model(segments, duration=50.0, consumed=consumed)
    monkeypatch.setattr(transcription, "get_model", lambda: model)

    real_update = job_manager.update_job

    def cancel_after_third(jid, **kwargs):
        real_update(jid, **kwargs)
        if len(consumed) >= 3:
            job_manager.cancel_job(jid)

    monkeypatch.setattr(job_manager, "update_job", cancel_after_third)
    with pytest.raises(HTTPException) as exc:
        transcription.transcribe(_audio(tmp_path), job_id)
    assert exc.value.status_code == 499
    assert len(consumed) < len(segments)


def test_transcription_reports_monotonic_progress(tmp_path, monkeypatch):
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="transcribing", progress=60)
    seen = []
    monkeypatch.setattr(job_manager, "update_job",
                        lambda jid, **kw: seen.append((kw.get("progress"), kw.get("message"))))
    model = _model([_seg(t, t + 10) for t in range(0, 100, 10)], duration=100.0)
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    transcription.transcribe(_audio(tmp_path), job_id)

    progress = [p for p, _ in seen]
    assert progress == sorted(progress) and len(set(progress)) == len(progress)
    assert 60 <= progress[0] and progress[-1] <= 74
    assert seen[-1][1] == "Transcribing audio... 1:40 / 1:40"


def test_job_id_does_not_change_the_transcript(tmp_path, monkeypatch):
    segments = [_seg(0.0, 1.2, " Hello "), _seg(None, 2.0, "dropped"), _seg(1.2, 3.0, "world")]
    monkeypatch.setattr(transcription, "get_model", lambda: _model(segments, duration=3.0))
    without = transcription.transcribe(_audio(tmp_path))
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="transcribing")
    monkeypatch.setattr(transcription, "get_model", lambda: _model(segments, duration=3.0))
    assert transcription.transcribe(_audio(tmp_path), job_id) == without == {
        "segments": [{"start": 0.0, "end": 1.2, "text": "Hello"}, {"start": 1.2, "end": 3.0, "text": "world"}]}


# ---------------------------------------------------------------------------
# P-REL-8: uploads in "processing" can be cancelled
# ---------------------------------------------------------------------------

def test_processing_status_is_cancellable():
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="processing")
    assert job_manager.cancel_job(job_id) is True
    assert job_manager.get_job(job_id)["status"] == "cancelled"


# ---------------------------------------------------------------------------
# P-REL-4 / D18 / issue 20: garbage collection
# ---------------------------------------------------------------------------

@pytest.fixture()
def gc_dirs(tmp_path, monkeypatch):
    temp_dir, outputs_dir = tmp_path / "temp", tmp_path / "outputs"
    temp_dir.mkdir()
    outputs_dir.mkdir()
    monkeypatch.setattr(config, "TEMP_DIR", temp_dir)
    monkeypatch.setattr(config, "OUTPUTS_DIR", outputs_dir)
    monkeypatch.setattr(config, "TEMP_FILE_MAX_AGE_HOURS", 0.0001)
    monkeypatch.setattr(config, "OUTPUT_DIR_MAX_AGE_HOURS", 0.0001)
    return temp_dir, outputs_dir


def _age(path: Path, seconds: float = 3600) -> None:
    past = time.time() - seconds
    os.utime(path, (past, past))


def test_gc_never_deletes_files_of_a_running_job(gc_dirs):
    from utils import run_garbage_collection
    temp_dir, _ = gc_dirs
    video = temp_dir / "0123456789abcdef0123456789abcdef.mp4"
    audio = temp_dir / "fedcba9876543210fedcba9876543210.wav"
    for f in (video, audio):
        f.write_bytes(b"data")
        _age(f)

    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="transcribing")
    job_manager.register_job_path(job_id, video)
    job_manager.register_job_path(job_id, audio)

    run_garbage_collection()
    assert video.exists() and audio.exists()

    job_manager.update_job(job_id, status="completed")
    run_garbage_collection()
    assert not video.exists() and not audio.exists()


def test_gc_keeps_debug_runs_when_debugger_enabled(gc_dirs, monkeypatch):
    from utils import run_garbage_collection
    _, outputs_dir = gc_dirs
    debug_run = outputs_dir / "11111111111111111111111111111111"
    plain_run = outputs_dir / "22222222222222222222222222222222"
    for run in (debug_run, plain_run):
        run.mkdir()
        (run / "clip_0.mp4").write_bytes(b"x")
    (debug_run / "analysis.json").write_text("{}", encoding="utf-8")
    for run in (debug_run, plain_run):
        _age(run)

    monkeypatch.setattr(config, "ENABLE_DEBUGGER", True)
    monkeypatch.setattr(config, "DEBUG_RUN_MAX_AGE_HOURS", 0.0)
    run_garbage_collection()
    assert debug_run.exists() and not plain_run.exists()

    monkeypatch.setattr(config, "ENABLE_DEBUGGER", False)
    run_garbage_collection()
    assert not debug_run.exists()


def test_finished_job_records_are_evicted_after_ttl(monkeypatch):
    finished = job_manager.create_job()
    running = job_manager.create_job()
    job_manager.update_job(finished, status="completed")
    job_manager.update_job(running, status="transcribing")

    future = time.time() + 10 * 3600
    assert job_manager.evict_expired_jobs(3600, now=future) >= 1
    assert job_manager.get_job(finished) is None
    assert job_manager.get_job(running) is not None


def test_status_response_does_not_expose_internal_timestamps():
    job_id = job_manager.create_job()
    job_manager.update_job(job_id, status="completed")
    body = client.get(f"/status/{job_id}").json()
    assert "finished_at" not in body and "start_time" not in body
    assert body["warnings"] == []


# ---------------------------------------------------------------------------
# P-REL-13: lifespan handler starts and stops background services
# ---------------------------------------------------------------------------

def test_lifespan_starts_and_stops_worker_pool_and_gc(monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main.worker_pool, "start", lambda: calls.append("pool.start"))
    monkeypatch.setattr(main.worker_pool, "stop", lambda: calls.append("pool.stop"))
    monkeypatch.setattr(main, "_gc_worker_loop", lambda: calls.append("gc.run"))
    with TestClient(main.app) as lifespan_client:
        assert lifespan_client.get("/health").json() == {"status": "ok"}
    assert calls[0] == "pool.start" and calls[-1] == "pool.stop" and "gc.run" in calls
