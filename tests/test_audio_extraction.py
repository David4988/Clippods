"""
tests/test_audio_extraction.py — Unit tests for Task 2: extract_audio

Run with: pytest tests/test_audio_extraction.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.audio_extraction import extract_audio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_probe(has_audio: bool = True) -> dict:
    """Return a minimal ffmpeg.probe() response."""
    streams = []
    if has_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    else:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    return {"streams": streams}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractAudio:

    def test_raises_400_when_file_not_found(self):
        """Non-existent video path → HTTPException 400."""
        with pytest.raises(HTTPException) as exc_info:
            extract_audio("/nonexistent/path/video.mp4")

        assert exc_info.value.status_code == 400
        assert "not found" in exc_info.value.detail.lower()

    def test_raises_400_on_corrupt_file(self, tmp_path):
        """Corrupt video that fails ffmpeg.probe → HTTPException 400."""
        corrupt = tmp_path / "corrupt.mp4"
        corrupt.write_bytes(b"this is not a valid video")

        import ffmpeg as ffmpeg_lib
        with patch("services.audio_extraction.ffmpeg.probe",
                   side_effect=ffmpeg_lib.Error("probe", b"", b"Invalid data")):
            with pytest.raises(HTTPException) as exc_info:
                extract_audio(str(corrupt))

        assert exc_info.value.status_code == 400
        assert "corrupt" in exc_info.value.detail.lower()

    def test_raises_400_when_no_audio_stream(self, tmp_path):
        """Video with no audio track → HTTPException 400."""
        video = tmp_path / "silent.mp4"
        video.write_bytes(b"fake-video")

        with patch("services.audio_extraction.ffmpeg.probe",
                   return_value=_make_probe(has_audio=False)):
            with pytest.raises(HTTPException) as exc_info:
                extract_audio(str(video))

        assert exc_info.value.status_code == 400
        assert "no audio" in exc_info.value.detail.lower()

    def test_returns_wav_path_on_success(self, tmp_path):
        """Happy path: valid video → returns existing .wav path string."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"fake-video")

        # Simulate a successful ffmpeg run by writing the output file ourselves
        def fake_run(self_node, quiet=False):
            # The output path is whatever get_temp_path(".wav") resolved to;
            # we intercept the ffmpeg chain and write a dummy .wav instead.
            pass

        fake_wav = tmp_path / "output.wav"
        fake_wav.write_bytes(b"RIFF....WAVEfmt ")  # minimal non-empty stub

        mock_stream = MagicMock()
        mock_stream.output.return_value = mock_stream
        mock_stream.overwrite_output.return_value = mock_stream
        mock_stream.run.return_value = None

        with patch("services.audio_extraction.ffmpeg.probe",
                   return_value=_make_probe(has_audio=True)), \
             patch("services.audio_extraction.ffmpeg.input",
                   return_value=mock_stream), \
             patch("services.audio_extraction.get_temp_path",
                   return_value=fake_wav):

            result = extract_audio(str(video))

        assert isinstance(result, str)
        assert result.endswith(".wav")
        assert Path(result).exists()

    def test_raises_400_on_ffmpeg_extraction_error(self, tmp_path):
        """ffmpeg.Error during .run() → HTTPException 400."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"fake-video")

        import ffmpeg as ffmpeg_lib

        mock_stream = MagicMock()
        mock_stream.output.return_value = mock_stream
        mock_stream.overwrite_output.return_value = mock_stream
        mock_stream.run.side_effect = ffmpeg_lib.Error("run", b"", b"Conversion failed")

        with patch("services.audio_extraction.ffmpeg.probe",
                   return_value=_make_probe(has_audio=True)), \
             patch("services.audio_extraction.ffmpeg.input",
                   return_value=mock_stream):
            with pytest.raises(HTTPException) as exc_info:
                extract_audio(str(video))

        assert exc_info.value.status_code == 400
        assert "extraction failed" in exc_info.value.detail.lower()
