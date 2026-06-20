"""
tests/test_transcription.py — Unit tests for Faster-Whisper-based transcribe()

Run with: pytest tests/test_transcription.py -v
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def _fake_segment(start, end, text):
    """Create a SimpleNamespace that mimics a faster-whisper Segment object."""
    return SimpleNamespace(start=start, end=end, text=text)


def _make_mock_model(segments):
    """Create a MagicMock that mimics WhisperModel and its .transcribe() method."""
    mock_model = MagicMock()
    info = SimpleNamespace(language="en", language_probability=0.98)
    mock_model.transcribe.return_value = (iter(segments), info)
    return mock_model


def _make_failing_mock_model():
    """Create a MagicMock whose .transcribe() raises an Exception."""
    mock_model = MagicMock()
    mock_model.transcribe.side_effect = Exception("fail")
    return mock_model


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
        """Faster-Whisper internal failure → HTTPException 502."""
        audio = _make_audio(tmp_path)

        with patch("services.transcription.model", _make_failing_mock_model()):
            with pytest.raises(HTTPException) as exc_info:
                transcribe(str(audio))

        assert exc_info.value.status_code == 502

    def test_returns_segments_on_success(self, tmp_path):
        """Happy path: Faster-Whisper returns segments → correct contract output."""
        audio = _make_audio(tmp_path)

        mock_segments = [
            _fake_segment(0.0, 1.5, "Hello"),
            _fake_segment(1.5, 3.0, "world"),
        ]

        with patch("services.transcription.model", _make_mock_model(mock_segments)):
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

        mock_segments = [
            _fake_segment(None, 2.0, "missing start"),
            _fake_segment(0.0, None, "missing end"),
            _fake_segment(1.0, 2.0, "valid"),
        ]

        with patch("services.transcription.model", _make_mock_model(mock_segments)):
            result = transcribe(str(audio))

        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "valid"

    def test_float_conversion(self, tmp_path):
        """Ensures start/end are always floats."""
        audio = _make_audio(tmp_path)

        mock_segments = [
            _fake_segment(1, 2, "test"),
        ]

        with patch("services.transcription.model", _make_mock_model(mock_segments)):
            result = transcribe(str(audio))

        assert isinstance(result["segments"][0]["start"], float)
        assert isinstance(result["segments"][0]["end"], float)