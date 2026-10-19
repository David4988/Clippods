"""
Tests for the offline evaluation harness (backend/evaluation).

Heavy dependencies (ffprobe, FFmpeg audio extraction, Faster-Whisper) are stubbed
at the production-function boundary, so these tests exercise the harness's own
logic: cache keys and invalidation, atomic UTF-8 artifacts, manifest validation,
engine specs, metrics and the run layout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation import cache as cache_mod
from evaluation import dataset as ds
from evaluation import storage
from evaluation.engines import parse_engine_spec, run_engine
from evaluation.metrics import selection_metrics
from services.transcription import transcribe_rich as REAL_TRANSCRIBE_RICH
from tests.fakes import transcript_from_segments
from tests.legacy.test_legacy_v2_golden import load_fixture


@pytest.fixture()
def eval_dir(tmp_path, monkeypatch):
    root = tmp_path / "eval_data"
    monkeypatch.setenv("CLIPPODS_EVAL_DIR", str(root))
    return root


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def test_write_json_is_utf8_and_leaves_no_temp_files(eval_dir):
    path = eval_dir / "x" / "analysis.json"
    data = {"hi": "असली वजह यह है।", "ta": "யாரும் பேசுவதில்லை.", "arrow": "5.0s → 20.0s ≥ 0.6"}
    storage.write_json(path, data)
    assert json.loads(path.read_bytes().decode("utf-8")) == data
    assert [p.name for p in path.parent.iterdir()] == ["analysis.json"]


def test_default_eval_dir_is_outside_production_storage(monkeypatch):
    import config
    monkeypatch.delenv("CLIPPODS_EVAL_DIR", raising=False)
    root = storage.eval_dir()
    assert root == storage.REPO_DIR / "eval_data"
    for production_dir in (config.TEMP_DIR, config.OUTPUTS_DIR):
        assert production_dir not in root.parents and root != production_dir


def test_eval_data_is_gitignored():
    ignore = (storage.REPO_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "eval_data/" in ignore


def test_sha256_file_is_memoised_and_tracks_changes(eval_dir, tmp_path):
    media = tmp_path / "v.mp4"
    media.write_bytes(b"one")
    first = storage.sha256_file(media)
    assert storage.sha256_file(media) == first
    media.write_bytes(b"two-changed")
    assert storage.sha256_file(media) != first


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def test_stage_key_is_order_independent_and_sensitive_to_every_part():
    base = cache_mod.stage_key("asr", "1", {"audio": "k1"}, {"model": "base", "beam": 5})
    assert base == cache_mod.stage_key("asr", "1", {"audio": "k1"}, {"beam": 5, "model": "base"})
    assert base != cache_mod.stage_key("asr", "2", {"audio": "k1"}, {"model": "base", "beam": 5})
    assert base != cache_mod.stage_key("asr", "1", {"audio": "k2"}, {"model": "base", "beam": 5})
    assert base != cache_mod.stage_key("asr", "1", {"audio": "k1"}, {"model": "large-v3", "beam": 5})
    assert base != cache_mod.stage_key("vad", "1", {"audio": "k1"}, {"model": "base", "beam": 5})


def test_cache_builds_once_then_hits(eval_dir):
    c = cache_mod.StageCache()
    calls = []

    def build(work: Path):
        calls.append(work)
        (work / "payload.txt").write_text("data", encoding="utf-8")
        return {"wall_s": 1.0}

    first = c.get_or_build("demo", "1", {"a": 1}, {"b": 2}, build)
    second = c.get_or_build("demo", "1", {"a": 1}, {"b": 2}, build)
    assert (first.hit, second.hit) == (False, True)
    assert len(calls) == 1
    assert (second.path / "payload.txt").read_text(encoding="utf-8") == "data"
    assert second.entry["build"] == {"wall_s": 1.0}


def test_failed_build_leaves_no_entry(eval_dir):
    c = cache_mod.StageCache()

    def boom(work: Path):
        (work / "partial.wav").write_bytes(b"half")
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        c.get_or_build("demo", "1", {}, {}, boom)
    key = cache_mod.stage_key("demo", "1", {}, {})
    assert c.lookup("demo", key) is None
    assert not any(c.entry_path("demo", key).parent.iterdir())


def test_entry_without_marker_is_not_trusted(eval_dir):
    c = cache_mod.StageCache()
    key = cache_mod.stage_key("demo", "1", {}, {})
    c.entry_path("demo", key).mkdir(parents=True)  # e.g. a hand-copied or crashed entry
    result = c.get_or_build("demo", "1", {}, {}, lambda w: {"rebuilt": True})
    assert result.hit is False and result.entry["build"] == {"rebuilt": True}


def test_disabled_cache_rebuilds(eval_dir):
    cache_mod.StageCache().get_or_build("demo", "1", {}, {}, lambda w: {"n": 1})
    result = cache_mod.StageCache(enabled=False).get_or_build("demo", "1", {}, {}, lambda w: {"n": 2})
    assert result.hit is False and result.entry["build"] == {"n": 2}


# ---------------------------------------------------------------------------
# dataset manifests
# ---------------------------------------------------------------------------

def _manifest(**overrides):
    data = {"schema": ds.SCHEMA, "dataset": "clippods-eval", "version": "v1", "frozen": False,
            "items": [{"id": "en-short-01", "media": {"filename": "en-short-01.mp4"}, "languages": ["en"]}]}
    data.update(overrides)
    return data


def test_valid_manifest_parses(eval_dir):
    dataset = ds.parse_manifest(_manifest())
    assert dataset.label == "clippods-eval-v1"
    assert dataset.items[0].media_path == eval_dir / "media" / "en-short-01.mp4"
    assert dataset.items[0].language_mode == "auto"


@pytest.mark.parametrize("items, message", [
    ([{"id": "a", "media": {"filename": "a.mp4"}, "languages": ["en"]}] * 2, "duplicate id"),
    ([{"id": "Bad ID", "media": {"filename": "a.mp4"}, "languages": ["en"]}], "id must match"),
    ([{"id": "a", "media": {}, "languages": ["en"]}], "media.filename or media.path"),
    ([{"id": "a", "media": {"filename": "a.mp4"}, "languages": ["fr"]}], "languages must be"),
    ([{"id": "a", "media": {"filename": "a.mp4"}, "languages": ["ta"], "language_mode": "tamil"}],
     "language_mode must be"),
])
def test_invalid_manifests_are_rejected(eval_dir, items, message):
    with pytest.raises(ds.ManifestError, match=message):
        ds.parse_manifest(_manifest(items=items))


def test_frozen_manifest_requires_pinned_hashes_and_portable_paths(eval_dir):
    items = [{"id": "a", "media": {"path": "C:/videos/a.mp4"}, "languages": ["hi"]}]
    with pytest.raises(ds.ManifestError) as exc:
        ds.parse_manifest(_manifest(frozen=True, items=items))
    assert "must pin media.sha256" in str(exc.value)
    assert "must use media.filename" in str(exc.value)


def test_verify_media_detects_hash_mismatch(eval_dir):
    media = eval_dir / "media" / "en-short-01.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video bytes")
    items = [{"id": "en-short-01", "media": {"filename": "en-short-01.mp4", "sha256": "0" * 64},
              "languages": ["en"]}]
    with pytest.raises(ds.ManifestError, match="sha256 mismatch"):
        ds.verify_media(ds.parse_manifest(_manifest(items=items)).items[0])


def test_committed_v1_template_is_valid():
    path = storage.BACKEND_DIR / "evaluation" / "datasets" / "clippods-eval" / "v1" / "manifest.json"
    dataset = ds.load_manifest(path)
    assert dataset.frozen is False  # frozen in Phase 2 after human review


# ---------------------------------------------------------------------------
# engines & metrics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec, label", [("legacy_v2@3", "legacy_v2@3"), (" legacy_v2@5 ", "legacy_v2@5"),
                                         ("boundary_v1@5", "boundary_v1@5")])
def test_engine_spec_parsing(spec, label):
    assert parse_engine_spec(spec).label == label


@pytest.mark.parametrize("spec", ["legacy_v2", "legacy_v2@0", "boundary_v2@5", "LEGACY@3"])
def test_bad_engine_specs(spec):
    with pytest.raises(ValueError):
        parse_engine_spec(spec)


def test_legacy_engine_matches_production_function_and_golden():
    fx = load_fixture("english_podcast_10min")
    result = run_engine(parse_engine_spec("legacy_v2@5"), transcript_from_segments(fx["segments"]), fx["video_duration"])
    golden = json.loads((Path(__file__).parents[1] / "legacy" / "golden" / "english_podcast_10min@5.json")
                        .read_text(encoding="utf-8"))
    assert result.clips == golden["selected"]
    assert result.engine_version == "adaptive_v2"


def test_metrics_count_identical_and_overlapping_clips():
    clips = [{"start": 0, "end": 12}, {"start": 0, "end": 12}, {"start": 10, "end": 30}, {"start": 40, "end": 55}]
    m = selection_metrics(clips, expected_count=5, video_duration=60)
    assert m["clip_count_ok"] is False
    assert m["identical_pairs"] == 1
    assert m["distinct_spans"] == 3
    assert m["overlapping_pairs"] == 3  # (0,1) identical, (0,2) and (1,2) partial
    assert m["max_overlap_ratio"] == 1.0
    # Clip-edge quality is measured since Phase 6 (needs a transcript); labels-based metrics are not.
    assert "truncated_ending_rate" in m["not_yet_measured"]
    assert "mid_word_cut_rate" not in m["not_yet_measured"] and "boundary" not in m


def test_metrics_surface_duplicates_legacy_trace_hides():
    fx = load_fixture("short_12s")
    result = run_engine(parse_engine_spec("legacy_v2@5"), transcript_from_segments(fx["segments"]), fx["video_duration"])
    m = selection_metrics(result.clips, 5, fx["video_duration"], result.analysis)
    assert m["identical_pairs"] == 10 and m["legacy"]["reported_duplicated"] == 0


# ---------------------------------------------------------------------------
# runner (stubbed media stages)
# ---------------------------------------------------------------------------

@pytest.fixture()
def stubbed_media(eval_dir, monkeypatch):
    """Replace ffprobe, audio extraction and Whisper with deterministic stubs."""
    import ffmpeg
    import config
    from services import audio_extraction, transcription

    fx = load_fixture("hindi_danda_5min")
    calls = {"probe": 0, "audio": 0, "transcribe": 0}

    def fake_probe(path):
        calls["probe"] += 1
        return {"format": {"duration": str(fx["video_duration"]), "size": "1234"},
                "streams": [{"codec_type": "audio"}, {"codec_type": "video"}]}

    def fake_extract(path, job_id=None):
        calls["audio"] += 1
        wav = config.TEMP_DIR / f"stub-{calls['audio']}.wav"
        wav.write_bytes(b"RIFF")
        return str(wav)

    def fake_transcribe(path, *, profile=None, language_mode="auto", job_id=None):
        calls["transcribe"] += 1
        calls["language_mode"] = language_mode
        return transcript_from_segments(fx["segments"], language="hi")

    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(audio_extraction, "extract_audio", fake_extract)
    monkeypatch.setattr(transcription, "transcribe_rich", fake_transcribe)

    media = eval_dir / "media" / "hi-sample.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"not really a video")
    return media, calls


def test_adhoc_run_writes_layout_and_reuses_cache(stubbed_media):
    from evaluation.runner import RunOptions, run_evaluation

    media, calls = stubbed_media
    dataset = ds.adhoc_dataset([media], language_mode="hi")
    options = RunOptions(engines=[parse_engine_spec("legacy_v2@3"), parse_engine_spec("legacy_v2@5")])

    first = run_evaluation(dataset, options, log=lambda *_: None)
    second = run_evaluation(dataset, options, log=lambda *_: None)

    assert first.failed_items == [] and second.failed_items == []
    assert calls == {"probe": 1, "audio": 1, "transcribe": 1, "language_mode": "hi"}  # second run: cache hits

    run = storage.read_json(first.run_dir / "run.json")
    assert run["status"] == "completed"
    assert run["engines"] == ["legacy_v2@3", "legacy_v2@5"]
    item_dir = first.run_dir / "items" / "hi-sample"
    stages_json = storage.read_json(item_dir / "stages.json")
    assert stages_json["transcript"]["config"]["language_mode"] == "hi"
    assert stages_json["transcript"]["config"]["profile"]["name"] == "legacy"
    assert stages_json["transcript"]["build"]["language"] == "hi"
    for label, count in (("legacy_v2@3", 3), ("legacy_v2@5", 5)):
        selection = storage.read_json(item_dir / label / "selection.json")
        assert len(selection["clips"]) == count
        analysis_text = (item_dir / label / "analysis.json").read_text(encoding="utf-8")
        assert "।" in analysis_text and "→" in analysis_text  # UTF-8 survives on Windows
    rows = storage.read_json(first.run_dir / "summary.json")["rows"]
    assert [r["engine"] for r in rows] == ["legacy_v2@3", "legacy_v2@5"]
    second_stages = storage.read_json(second.run_dir / "items" / "hi-sample" / "stages.json")
    assert all(s["cache_hit"] for s in second_stages.values())


def test_unavailable_model_is_a_failure_and_nothing_is_cached(stubbed_media, monkeypatch):
    from evaluation.runner import RunOptions, run_evaluation
    from services import transcription

    media, _ = stubbed_media
    monkeypatch.setattr(transcription, "transcribe_rich", REAL_TRANSCRIBE_RICH)
    monkeypatch.setattr(transcription, "get_model", lambda *a, **k: None)
    outcome = run_evaluation(ds.adhoc_dataset([media]),
                             RunOptions(engines=[parse_engine_spec("legacy_v2@5")]), log=lambda *_: None)
    run = storage.read_json(outcome.run_dir / "run.json")
    assert outcome.failed_items == ["hi-sample"]
    assert "Transcription is unavailable" in run["items"]["hi-sample"]["error"]
    assert not list((storage.cache_dir() / "transcript").rglob("_entry.json"))


def test_promote_copies_small_json_only(stubbed_media, monkeypatch, tmp_path):
    from evaluation import runner

    media, _ = stubbed_media
    monkeypatch.setattr(runner, "RESULTS_DIR", tmp_path / "results")
    outcome = runner.run_evaluation(ds.adhoc_dataset([media]),
                                    runner.RunOptions(engines=[parse_engine_spec("legacy_v2@5")]),
                                    log=lambda *_: None)
    dest = runner.promote_run(outcome.run_id)
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == ["items/hi-sample/legacy_v2@5/metrics.json", "items/hi-sample/legacy_v2@5/selection.json",
                     "items/hi-sample/stages.json", "run.json", "summary.json"]
    assert "traceback" not in (dest / "run.json").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        runner.promote_run(outcome.run_id)
