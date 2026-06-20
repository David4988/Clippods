"""
tests/test_integration.py — Integration tests for POST /process (JSON) and POST /process/upload (multipart)

Tests the full request → response flow using FastAPI's TestClient.
FFmpeg + Sarvam calls are mocked so no real media processing occurs.

Run with: python -m pytest tests/test_integration.py -v
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _pipeline_patches(tmp_path: Path, generate_return: list[str] | None = None):
    """Return a list of patches that mock every service in _run_pipeline."""
    import ffmpeg as ffmpeg_module

    if generate_return is None:
        generate_return = [str(tmp_path / f"clip_{i}.mp4") for i in range(3)]

    return [
        patch("routers.video.get_video_input",
              new=AsyncMock(return_value=tmp_path / "video.mp4")),
        patch("routers.video.extract_audio",
              return_value=str(tmp_path / "audio.wav")),
        patch("routers.video.transcribe",
              return_value={"segments": [{"start": 0.0, "end": 5.0, "text": "hi"}]}),
        patch.object(ffmpeg_module, "probe",
                     return_value={"format": {"duration": "120.0"}}),
        patch("routers.video.select_segments",
              return_value=[{"start": 0.0,  "end": 20.0},
                             {"start": 50.0, "end": 70.0},
                             {"start": 100.0,"end": 120.0}]),
        patch("routers.video.generate_clips",
              return_value=generate_return),
        patch("routers.video.cleanup_file"),
    ]


def _apply(patches):
    """Start all patches; caller must stop them."""
    for p in patches:
        p.start()
    return patches


def _stop(patches):
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Route contract — health + existence
# ---------------------------------------------------------------------------

class TestRouteContract:

    def test_health_endpoint_ok(self):
        """/health returns 200."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_post_process_json_route_exists(self):
        """POST /process (JSON) is registered — empty body gives 422, not 404/405."""
        resp = client.post("/process", json={})
        assert resp.status_code not in (404, 405)

    def test_post_process_upload_route_exists(self):
        """POST /process/upload (multipart) is registered."""
        resp = client.post("/process/upload")
        assert resp.status_code not in (404, 405)

    def test_json_route_requires_video_url_field(self):
        """JSON body missing video_url → 422 with {error} contract shape."""
        resp = client.post("/process", json={"other": "field"})
        assert resp.status_code == 422
        assert "error" in resp.json()
        assert "detail" not in resp.json()

    def test_json_route_rejects_empty_body(self):
        """Empty JSON body → 422 with {error} contract shape."""
        resp = client.post("/process", json={})
        assert resp.status_code == 422
        assert "error" in resp.json()
        assert "detail" not in resp.json()

    def test_upload_route_requires_file(self):
        """Multipart with no file field → 422 with {error} contract shape."""
        resp = client.post("/process/upload", data={})
        assert resp.status_code == 422
        assert "error" in resp.json()
        assert "detail" not in resp.json()


# ---------------------------------------------------------------------------
# POST /process (JSON body) — Content-Type: application/json
# ---------------------------------------------------------------------------

class TestJsonRoute:

    def test_returns_200_with_valid_url(self, tmp_path):
        """Valid JSON body with video_url → 200 + correct shape."""
        patches = _pipeline_patches(tmp_path)
        _apply(patches)
        try:
            resp = client.post("/process", json={"video_url": "https://example.com/v.mp4"})
        finally:
            _stop(patches)

        assert resp.status_code == 200
        body = resp.json()
        assert "clips" in body
        assert body["clips"] == ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]

    def test_response_clips_are_basenames_only(self, tmp_path):
        """Absolute paths from generate_clips are stripped to basenames."""
        abs_paths = [f"/deep/outputs/run/{n}" for n in
                     ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]]
        patches = _pipeline_patches(tmp_path, generate_return=abs_paths)
        _apply(patches)
        try:
            resp = client.post("/process", json={"video_url": "https://x.com/v"})
        finally:
            _stop(patches)

        assert resp.status_code == 200
        for clip in resp.json()["clips"]:
            assert "/" not in clip and "\\" not in clip

    def test_pipeline_error_propagates_as_error_key(self, tmp_path):
        """A 502 from transcribe → HTTP 502 with {error: 'Audio not clear enough'}."""
        import ffmpeg as ffmpeg_module
        from fastapi import HTTPException

        with patch("routers.video.get_video_input",
                   new=AsyncMock(return_value=tmp_path / "video.mp4")), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "60.0"}}), \
             patch("routers.video.extract_audio",
                   return_value=str(tmp_path / "audio.wav")), \
             patch("routers.video.transcribe",
                   side_effect=HTTPException(502, "Sarvam down")), \
             patch("routers.video.cleanup_file"):

            resp = client.post("/process", json={"video_url": "https://x.com/v"})

        assert resp.status_code == 502
        body = resp.json()
        assert "error" in body
        assert "detail" not in body
        assert body["error"] == "Audio not clear enough"


# ---------------------------------------------------------------------------
# POST /process/upload (multipart) — Content-Type: multipart/form-data
# ---------------------------------------------------------------------------

class TestUploadRoute:

    def test_returns_200_with_valid_file(self, tmp_path):
        """Valid file upload → 200 + correct shape."""
        patches = _pipeline_patches(tmp_path)
        _apply(patches)
        try:
            resp = client.post(
                "/process/upload",
                files={"file": ("clip.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
            )
        finally:
            _stop(patches)

        assert resp.status_code == 200
        body = resp.json()
        assert body["clips"] == ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]


# ---------------------------------------------------------------------------
# Cleanup behaviour
# ---------------------------------------------------------------------------

class TestCleanup:

    def test_cleanup_called_on_success(self, tmp_path):
        """cleanup_file is called for video and audio on success."""
        import ffmpeg as ffmpeg_module

        video = tmp_path / "video.mp4"
        audio = tmp_path / "audio.wav"
        video.write_bytes(b"x")
        audio.write_bytes(b"x")

        mock_cleanup = MagicMock()

        with patch("routers.video.get_video_input", new=AsyncMock(return_value=video)), \
             patch("routers.video.extract_audio", return_value=str(audio)), \
             patch("routers.video.transcribe",
                   return_value={"segments": [{"start": 0.0, "end": 5.0, "text": "x"}]}), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "60.0"}}), \
             patch("routers.video.select_segments",
                   return_value=[{"start": 0.0, "end": 20.0},
                                  {"start": 20.0, "end": 40.0},
                                  {"start": 40.0, "end": 60.0}]), \
             patch("routers.video.generate_clips",
                   return_value=[str(tmp_path / f"clip_{i}.mp4") for i in range(3)]), \
             patch("routers.video.cleanup_file", mock_cleanup):

            client.post("/process", json={"video_url": "https://x.com/v"})

        cleaned = {str(c.args[0]) for c in mock_cleanup.call_args_list}
        assert str(video) in cleaned
        assert str(audio) in cleaned

    def test_cleanup_called_on_failure(self, tmp_path):
        """cleanup_file still runs when a pipeline step raises."""
        import ffmpeg as ffmpeg_module
        from fastapi import HTTPException

        video = tmp_path / "video.mp4"
        audio = tmp_path / "audio.wav"
        video.write_bytes(b"x")
        audio.write_bytes(b"x")

        mock_cleanup = MagicMock()

        with patch("routers.video.get_video_input", new=AsyncMock(return_value=video)), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "60.0"}}), \
             patch("routers.video.extract_audio", return_value=str(audio)), \
             patch("routers.video.transcribe",
                   side_effect=HTTPException(502, "Sarvam down")), \
             patch("routers.video.cleanup_file", mock_cleanup):

            resp = client.post("/process", json={"video_url": "https://x.com/v"})

        assert resp.status_code == 502
        cleaned = {str(c.args[0]) for c in mock_cleanup.call_args_list}
        assert str(video) in cleaned
        assert str(audio) in cleaned


# ---------------------------------------------------------------------------
# Duration guard
# ---------------------------------------------------------------------------

class TestDurationGuard:

    def test_rejects_video_longer_than_2_hours(self, tmp_path):
        """Video > 7200s → 400 with contract error string."""
        import ffmpeg as ffmpeg_module

        with patch("routers.video.get_video_input",
                   new=AsyncMock(return_value=tmp_path / "video.mp4")), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "7201.0"}}), \
             patch("routers.video.cleanup_file"):

            resp = client.post("/process", json={"video_url": "https://x.com/long.mp4"})

        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "Video too long (max 2 hours)"
        assert "detail" not in body

    def test_accepts_video_exactly_at_limit(self, tmp_path):
        """Video at exactly 7200s → allowed through."""
        import ffmpeg as ffmpeg_module
        patches = _pipeline_patches(tmp_path)
        # Override probe to return exactly 7200s
        import ffmpeg as fm
        for p in patches:
            if hasattr(p, "attribute") and p.attribute == "probe":
                p.new = MagicMock(return_value={"format": {"duration": "7200.0"}})

        with patch("routers.video.get_video_input",
                   new=AsyncMock(return_value=tmp_path / "video.mp4")), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "7200.0"}}), \
             patch("routers.video.extract_audio",
                   return_value=str(tmp_path / "audio.wav")), \
             patch("routers.video.transcribe",
                   return_value={"segments": [{"start": 0.0, "end": 5.0, "text": "x"}]}), \
             patch("routers.video.select_segments",
                   return_value=[{"start": 0.0, "end": 20.0},
                                  {"start": 300.0, "end": 320.0},
                                  {"start": 600.0, "end": 620.0}]), \
             patch("routers.video.generate_clips",
                   return_value=[str(tmp_path / f"clip_{i}.mp4") for i in range(3)]), \
             patch("routers.video.cleanup_file"):

            resp = client.post("/process", json={"video_url": "https://x.com/v"})

        assert resp.status_code == 200

    def test_error_key_not_detail(self, tmp_path):
        """Rejected long video → {error: ...} never {detail: ...}."""
        import ffmpeg as ffmpeg_module

        with patch("routers.video.get_video_input",
                   new=AsyncMock(return_value=tmp_path / "video.mp4")), \
             patch.object(ffmpeg_module, "probe",
                          return_value={"format": {"duration": "9999.0"}}), \
             patch("routers.video.cleanup_file"):

            resp = client.post("/process", json={"video_url": "https://x.com/long.mp4"})

        assert "error" in resp.json()
        assert "detail" not in resp.json()
