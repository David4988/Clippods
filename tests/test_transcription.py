"""
tests/test_transcription.py — Unit tests for Whisper-based transcribe()

Run with: pytest tests/test_transcription.py -v
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.transcription import transcribe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audio(tmp_path: Path, content: bytes = b"RIFF....WAVEfmt ") -> Path:
    p = tmp_path / "audio.wav"
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranscribe:

    def test_raises_400_when_file_missing(self):
        """Non-existent audio file → HTTPException 400."""
        with pytest.raises(HTTPException) as exc_info:
            transcribe("/nonexistent/audio.wav")

        assert exc_info.value.status_code == 400

    def test_raises_400_when_file_empty(self, tmp_path):
        """Zero-byte audio file → HTTPException 400."""
        audio = _make_audio(tmp_path, content=b"")

        with pytest.raises(HTTPException) as exc_info:
            transcribe(str(audio))

        assert exc_info.value.status_code == 400

    def test_raises_502_on_whisper_failure(self, tmp_path):
        """Whisper internal failure → HTTPException 502."""
        audio = _make_audio(tmp_path)

        with patch("services.transcription.model.transcribe", side_effect=Exception("fail")):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))

        assert exc_info.value.status_code == 502

    def test_returns_segments_on_success(self, tmp_path):
        """Happy path: Whisper returns segments → correct contract output."""
        audio = _make_audio(tmp_path)

        mock_result = {
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "Hello"},
                {"start": 1.5, "end": 3.0, "text": "world"},
            ]
        }

        with patch("services.transcription.model.transcribe", return_value=mock_result):
            result = transcribe(str(audio))

        assert "segments" in result
        assert len(result["segments"]) == 2
        assert result["segments"][0] == {
            "start": 0.0,
            "end": 1.5,
            "text": "Hello",
        }

    def test_skips_invalid_segments(self, tmp_path):
        """Segments missing start/end are ignored."""
        audio = _make_audio(tmp_path)

        mock_result = {
            "segments": [
                {"start": 0.0, "text": "missing end"},
                {"end": 2.0, "text": "missing start"},
                {"start": 1.0, "end": 2.0, "text": "valid"},
            ]
        }

        with patch("services.transcription.model.transcribe", return_value=mock_result):
            result = transcribe(str(audio))

        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "valid"

    def test_float_conversion(self, tmp_path):
        """Ensures start/end are always floats."""
        audio = _make_audio(tmp_path)

        mock_result = {
            "segments": [
                {"start": 1, "end": 2, "text": "test"}
            ]
        }

        with patch("services.transcription.model.transcribe", return_value=mock_result):
            result = transcribe(str(audio))

        assert isinstance(result["segments"][0]["start"], float)
        assert isinstance(result["segments"][0]["end"], float)