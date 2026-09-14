"""Tests for Phase 2 dataset tooling: add, label templates, label validation, check, freeze."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation import dataset_tools as tools
from evaluation import labels as lb
from evaluation import storage
from evaluation.__main__ import main as cli


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPODS_EVAL_DIR", str(tmp_path / "eval_data"))
    import ffmpeg

    durations = {}

    def fake_probe(path):
        name = Path(path).name
        if name.startswith("silent"):
            return {"format": {"duration": "10"}, "streams": [{"codec_type": "video"}]}
        return {"format": {"duration": str(durations.get(name, 600.0))},
                "streams": [{"codec_type": "audio"}, {"codec_type": "video"}]}

    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    manifest = tmp_path / "datasets" / "clippods-eval" / "v1" / "manifest.json"
    storage.write_json(manifest, {"schema": "clippods-eval-manifest/1", "dataset": "clippods-eval",
                                  "version": "v1", "frozen": False, "items": []})
    media = storage.media_dir()
    media.mkdir(parents=True)
    return manifest, media, durations


def _media(folder: Path, name: str, content: bytes = b"video") -> Path:
    path = folder / name
    path.write_bytes(content + name.encode())
    return path


def _complete_labels(item_id: str, duration: float = 600.0) -> dict:
    labels = lb.template(item_id, duration, ["ta"])
    labels.update({
        "status": "complete", "labeler": "owner", "labeled_at": "2026-09-20",
        "gold_moments": [{"id": f"m{i}", "start": 60.0 * i, "end": 60.0 * i + 40, "type": "hook",
                          "strength": 2, "note": ""} for i in range(1, 6)],
        "must_not": [{"start": 0.0, "end": 20.0, "reason": "intro music"}],
        "transcript_excerpts": [{"id": f"x{i}", "start": 30.0 + 150 * i, "end": 30.0 + 150 * i + 140,
                                 "language": "ta", "script": "native", "text": "உரை"} for i in range(3)],
    })
    return labels


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def test_add_item_hashes_probes_and_appends(workspace):
    manifest, media, durations = workspace
    durations["ta-long.mp4"] = 5412.3
    video = _media(media, "ta-long.mp4")
    item = tools.add_item(manifest, video, "ta-podcast-long-01", ["ta"], tags=["podcast", "long-form"],
                          speakers=2, source_url="https://www.youtube.com/watch?v=abc", notes="Tamil long-form")
    data = storage.read_json(manifest)
    assert data["items"] == [item]
    assert item["media"] == {"filename": "ta-long.mp4", "sha256": storage.sha256_file(video)}
    assert item["duration_s"] == 5412.3 and item["source"]["kind"] == "youtube"


def test_add_refuses_media_outside_media_dir_unless_copied(workspace, tmp_path):
    manifest, media, _ = workspace
    outside = _media(tmp_path, "hi-short.mp4")
    with pytest.raises(tools.DatasetToolError, match="not in the media directory"):
        tools.add_item(manifest, outside, "hi-short-01", ["hi"])
    tools.add_item(manifest, outside, "hi-short-01", ["hi"], copy_into_media_dir=True)
    assert (media / "hi-short.mp4").exists() and outside.exists()


@pytest.mark.parametrize("item_id, languages, match", [
    ("dup", ["en"], "already exists"),
    ("Bad Id", ["en"], "id must match"),
    ("fr-01", ["fr"], "languages must be"),
])
def test_add_rejects_bad_items_without_touching_manifest(workspace, item_id, languages, match):
    manifest, media, _ = workspace
    tools.add_item(manifest, _media(media, "a.mp4"), "dup", ["en"])
    before = manifest.read_bytes()
    with pytest.raises((tools.DatasetToolError, ValueError), match=match):
        tools.add_item(manifest, _media(media, f"{item_id.replace(' ', '_')}-b.mp4"), item_id, languages)
    assert manifest.read_bytes() == before


def test_add_rejects_media_without_audio(workspace):
    manifest, media, _ = workspace
    with pytest.raises(tools.DatasetToolError, match="no audio stream"):
        tools.add_item(manifest, _media(media, "silent.mp4"), "silent-01", ["en"])


def test_add_refuses_frozen_manifest(workspace):
    manifest, media, _ = workspace
    data = storage.read_json(manifest)
    data["frozen"] = True
    storage.write_json(manifest, data)
    with pytest.raises(tools.DatasetToolError, match="frozen"):
        tools.add_item(manifest, _media(media, "x.mp4"), "x-01", ["en"])


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------

def test_label_template_is_created_once(workspace):
    manifest, media, _ = workspace
    tools.add_item(manifest, _media(media, "ta.mp4"), "ta-01", ["ta"])
    path = tools.label_template(manifest, "ta-01")
    labels = storage.read_json(path)
    assert labels["status"] == "draft" and labels["duration_s"] == 600.0
    assert labels["languages"]["dominant"] == "ta"
    with pytest.raises(tools.DatasetToolError, match="refusing to overwrite"):
        tools.label_template(manifest, "ta-01")


def test_complete_labels_pass_strict_validation():
    report = lb.validate_labels(_complete_labels("ta-01"), "ta-01", 600.0, require_complete=True)
    assert report.ok, report.errors


@pytest.mark.parametrize("mutate, message", [
    (lambda l: l["gold_moments"][0].update(end=10.0), "must be after start"),
    (lambda l: l["gold_moments"][0].update(end=9999.0), "past the media duration"),
    (lambda l: l["gold_moments"][0].update(type="funny"), "type must be one of"),
    (lambda l: l["gold_moments"][0].update(strength=5), "strength must be"),
    (lambda l: l["gold_moments"][1].update(id="m1"), "ids must be present and unique"),
    (lambda l: l.update(gold_moments=l["gold_moments"][:3]), "expected 5–10 gold_moments"),
    (lambda l: l["gold_moments"][0].update(start=5.0, end=40.0), "overlaps a must_not region"),
    (lambda l: l["transcript_excerpts"][1].update(start=100.0, end=250.0), "overlap"),
    (lambda l: l["transcript_excerpts"][0].update(script="latin"), "script must be one of"),
    (lambda l: l["transcript_excerpts"][0].update(text=" "), "text is empty"),
    (lambda l: l.update(status="draft"), "status must be 'complete'"),
    (lambda l: l.update(labeler=""), "labeler is required"),
    (lambda l: l.update(item_id="other"), "does not match manifest item"),
    (lambda l: l["languages"]["code_switch_regions"].append({"start": 1, "end": 5, "languages": ["ta"]}),
     "languages must list 2+"),
])
def test_label_validation_errors(mutate, message):
    labels = _complete_labels("ta-01")
    mutate(labels)
    report = lb.validate_labels(labels, "ta-01", 600.0, require_complete=True)
    assert any(message in e for e in report.errors), report.errors


def test_draft_labels_only_warn_about_counts():
    report = lb.validate_labels(lb.template("en-01", 600.0, ["en"]), "en-01", 600.0, require_complete=False)
    assert report.ok
    assert any("gold_moments" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# check & freeze
# ---------------------------------------------------------------------------

def test_check_reports_missing_labels_media_changes_and_composition(workspace):
    manifest, media, durations = workspace
    durations["ta.mp4"] = 5400.0
    video = _media(media, "ta.mp4")
    tools.add_item(manifest, video, "ta-long-01", ["ta"])

    report = tools.check(manifest)
    assert report.ok  # missing labels only warn outside freeze mode
    assert ("Tamil long", 1, 1) in report.composition
    assert ("English long (60–120 min)", 0, 2) in report.composition
    assert report.totals["hours"] == 1.5

    strict = tools.check(manifest, for_freeze=True)
    assert not strict.ok and any("no labels file" in e for e in strict.errors)

    video.write_bytes(b"re-encoded by mistake")
    assert any("sha256 mismatch" in e for e in tools.check(manifest).errors)


def test_freeze_refuses_until_ready_then_pins_labels(workspace):
    manifest, media, _ = workspace
    tools.add_item(manifest, _media(media, "ta.mp4"), "ta-01", ["ta"])
    label_path = tools.label_template(manifest, "ta-01")

    report = tools.freeze(manifest, "owner")
    assert not report.frozen and storage.read_json(manifest)["frozen"] is False

    storage.write_json(label_path, _complete_labels("ta-01"))
    report = tools.freeze(manifest, "owner")
    assert report.frozen, [r.errors for r in report.label_reports] + report.errors

    data = storage.read_json(manifest)
    assert data["frozen"] is True and data["frozen_by"] == "owner"
    assert data["items"][0]["labels_sha256"]
    with pytest.raises(tools.DatasetToolError, match="already frozen"):
        tools.freeze(manifest, "owner")

    labels = storage.read_json(label_path)
    labels["notes"] = "edited later"
    storage.write_json(label_path, labels)
    assert any("labels changed after the dataset was frozen" in e for e in tools.check(manifest).errors)


def test_cli_end_to_end(workspace, capsys):
    manifest, media, _ = workspace
    video = _media(media, "en.mp4")
    assert cli(["dataset", "add", "--manifest", str(manifest), "--media", str(video), "--id", "en-short-01",
                "--languages", "en", "--tags", "podcast,high-energy", "--notes", "energetic host"]) == 0
    assert cli(["dataset", "label-template", "--manifest", str(manifest), "--item", "en-short-01"]) == 0
    assert cli(["dataset", "check", str(manifest)]) == 0
    assert cli(["dataset", "freeze", str(manifest), "--by", "owner"]) == 1
    out = capsys.readouterr().out
    assert "composition vs target" in out and "RESULT: not ready" in out
    assert cli(["dataset", "add", "--manifest", str(manifest), "--media", str(video), "--id", "en-short-01",
                "--languages", "en"]) == 2


def test_committed_v1_manifest_passes_non_strict_check():
    path = storage.BACKEND_DIR / "evaluation" / "datasets" / "clippods-eval" / "v1" / "manifest.json"
    report = tools.check(path)
    assert report.ok and report.item_count == 0 and report.frozen is False
