"""
tests/test_transcription.py — Unit tests for Task 3: transcribe + _normalise_response

Run with: pytest tests/test_transcription.py -v
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest
from fastapi import HTTPException

from services.transcription import TranscriptResult, _normalise_response, transcribe


# ---------------------------------------------------------------------------
# Sub-task 3.2 — Normalisation Logic
# ---------------------------------------------------------------------------

class TestNormaliseResponse:

    def test_full_response_with_segments(self):
        """Segments present → normalised into contract shape."""
        raw = {
            "transcript": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "Hello"},
                {"start": 1.5, "end": 2.8, "text": "world"},
            ],
        }
        result = _normalise_response(raw)
        assert len(result["segments"]) == 2
        assert result["segments"][0] == {"start": 0.0, "end": 1.5, "text": "Hello"}
        assert result["segments"][1] == {"start": 1.5, "end": 2.8, "text": "world"}

    def test_accepts_text_field_alias(self):
        """Accepts 'text' key as well as 'transcript'; result still has segments."""
        raw = {"text": "Hello", "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}]}
        result = _normalise_response(raw)
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "Hello"

    def test_no_segments_synthesises_fallback(self):
        """No segments → single fallback segment at 0.0→0.0 with full text."""
        raw = {"transcript": "No timestamps here"}
        result = _normalise_response(raw)
        assert len(result["segments"]) == 1
        assert result["segments"][0]["start"] == 0.0
        assert result["segments"][0]["end"] == 0.0
        assert result["segments"][0]["text"] == "No timestamps here"

    def test_empty_response(self):
        """Completely empty raw dict → empty segments list."""
        result = _normalise_response({})
        assert result["segments"] == []

    def test_malformed_segments_skipped(self):
        """Segments missing start/end are silently dropped."""
        raw = {
            "transcript": "ok",
            "segments": [
                {"start": 0.0, "text": "missing end"},        # no 'end'
                {"end": 2.0, "text": "missing start"},        # no 'start'
                {"start": 0.5, "end": 1.5, "text": "valid"},  # ok
            ],
        }
        result = _normalise_response(raw)
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "valid"

    def test_float_coercion(self):
        """Integer timing values from API are coerced to float."""
        raw = {
            "transcript": "hi",
            "segments": [{"start": 0, "end": 2, "text": "hi"}],
        }
        result = _normalise_response(raw)
        assert isinstance(result["segments"][0]["start"], float)
        assert isinstance(result["segments"][0]["end"], float)


# ---------------------------------------------------------------------------
# Sub-task 3.1 — API Client
# ---------------------------------------------------------------------------

class TestTranscribe:

    def _make_audio(self, tmp_path: Path, content: bytes = b"RIFF....WAVEfmt ") -> Path:
        p = tmp_path / "audio.wav"
        p.write_bytes(content)
        return p

    def _mock_success_response(self) -> MagicMock:
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.status_code = 200
        resp.json.return_value = {
            "transcript": "Hello Sarvam",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello Sarvam"}],
        }
        return resp

    def test_raises_500_when_no_api_key(self, tmp_path):
        """Missing SARVAM_API_KEY → HTTPException 500."""
        audio = self._make_audio(tmp_path)
        with patch.dict(os.environ, {"SARVAM_API_KEY": ""}):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))
        assert exc_info.value.status_code == 500

    def test_raises_400_when_file_missing(self):
        """Non-existent audio file → HTTPException 400."""
        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}):
            with pytest.raises(HTTPException) as exc_info:
                transcribe("/nonexistent/audio.wav")
        assert exc_info.value.status_code == 400

    def test_raises_400_when_file_empty(self, tmp_path):
        """Zero-byte audio file → HTTPException 400."""
        audio = self._make_audio(tmp_path, content=b"")
        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))
        assert exc_info.value.status_code == 400

    def test_raises_502_on_api_error(self, tmp_path):
        """Sarvam API 4xx/5xx → HTTPException 502."""
        audio = self._make_audio(tmp_path)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.is_success = False
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}), \
             patch("services.transcription.httpx.Client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))
        assert exc_info.value.status_code == 502

    def test_raises_504_on_timeout(self, tmp_path):
        """httpx.TimeoutException → HTTPException 504."""
        audio = self._make_audio(tmp_path)

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}), \
             patch("services.transcription.httpx.Client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))
        assert exc_info.value.status_code == 504

    def test_returns_normalised_result_on_success(self, tmp_path):
        """Happy path: valid audio + 200 response → TranscriptResult returned."""
        audio = self._make_audio(tmp_path)
        mock_resp = self._mock_success_response()

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}), \
             patch("services.transcription.httpx.Client", return_value=mock_client):
            result = transcribe(str(audio))

        assert len(result["segments"]) == 1
        assert result["segments"][0]["start"] == 0.0
        assert result["segments"][0]["end"] == 1.0

    def test_posts_to_correct_endpoint_with_auth(self, tmp_path):
        """Confirms correct URL, header, and file field are used."""
        audio = self._make_audio(tmp_path)
        mock_resp = self._mock_success_response()

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch.dict(os.environ, {"SARVAM_API_KEY": "my-secret-key"}), \
             patch("services.transcription.httpx.Client", return_value=mock_client):
            transcribe(str(audio))

        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == "https://api.sarvam.ai/speech-to-text"
        assert call_kwargs[1]["headers"]["api-subscription-key"] == "my-secret-key"
        assert "file" in call_kwargs[1]["files"]
