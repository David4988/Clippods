"""
tests/test_input_processing.py — Unit tests for Task 1: get_video_input

Run with: pytest tests/test_input_processing.py -v
"""
import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from services.input_processing import (
    download_video_from_url,
    get_video_input,
    save_uploaded_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload(filename: str = "video.mp4", content: bytes = b"fake-video-bytes") -> UploadFile:
    """Build a minimal UploadFile mock."""
    upload = MagicMock(spec=UploadFile)
    upload.filename = filename
    upload.read = asyncio.coroutine(lambda: content) if False else None  # patched below
    return upload


def _chunked_read(data: bytes):
    """
    Build a stand-in for ``UploadFile.read(size)`` that streams *data* and then
    returns b"" — the same contract Starlette's UploadFile honours. A mock that
    ignores the size argument and keeps returning the same bytes makes
    save_uploaded_file loop until it trips the size limit.
    """
    remaining = bytearray(data)

    async def _read(size: int = -1):
        if size is None or size < 0:
            size = len(remaining)
        chunk = bytes(remaining[:size])
        del remaining[:size]
        return chunk

    return _read


# ---------------------------------------------------------------------------
# Sub-task 1.1 — URL Handler
# ---------------------------------------------------------------------------

class TestDownloadVideoFromUrl:
    def test_returns_valid_path_on_success(self, tmp_path):
        """yt-dlp success → returns existing Path."""
        fake_file = tmp_path / "video.mp4"
        fake_file.write_bytes(b"fake")

        mock_info = {"ext": "mp4"}
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = str(fake_file)
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("services.input_processing.yt_dlp.YoutubeDL", return_value=mock_ydl):
            result = download_video_from_url("https://example.com/video")

        assert isinstance(result, Path)
        assert result.exists()

    def test_raises_400_on_download_error(self):
        """yt-dlp DownloadError → HTTPException 400."""
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("not found")
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("services.input_processing.yt_dlp.YoutubeDL", return_value=mock_ydl):
            with pytest.raises(HTTPException) as exc_info:
                download_video_from_url("https://bad-url.com")

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Sub-task 1.2 — Upload Handler
# ---------------------------------------------------------------------------

class TestSaveUploadedFile:
    @pytest.mark.asyncio
    async def test_returns_valid_path_on_success(self):
        """Valid upload → file written to temp/, valid Path returned."""
        upload = MagicMock(spec=UploadFile)
        upload.filename = "clip.mp4"
        upload.read = _chunked_read(b"fake-video-content")

        result = await save_uploaded_file(upload)

        assert isinstance(result, Path)
        assert result.exists()
        assert result.suffix == ".mp4"
        assert result.read_bytes() == b"fake-video-content"
        result.unlink()  # cleanup

    @pytest.mark.asyncio
    async def test_raises_400_on_empty_file(self):
        """Empty upload → HTTPException 400."""
        upload = MagicMock(spec=UploadFile)
        upload.filename = "empty.mp4"
        upload.read = _chunked_read(b"")

        with pytest.raises(HTTPException) as exc_info:
            await save_uploaded_file(upload)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Sub-task 1.3 — Input Validator via get_video_input
# ---------------------------------------------------------------------------

class TestGetVideoInput:
    @pytest.mark.asyncio
    async def test_raises_422_when_both_provided(self):
        """Both url and file → HTTPException 422."""
        upload = MagicMock(spec=UploadFile)
        upload.filename = "v.mp4"

        with pytest.raises(HTTPException) as exc_info:
            await get_video_input("https://example.com/v", upload)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_raises_422_when_neither_provided(self):
        """Neither url nor file → HTTPException 422."""
        with pytest.raises(HTTPException) as exc_info:
            await get_video_input(None, None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_routes_to_url_handler(self):
        """URL only → delegates to download_video_from_url."""
        fake_path = Path("temp/fake.mp4")

        with patch(
            "services.input_processing.download_video_from_url",
            return_value=fake_path,
        ) as mock_dl:
            result = await get_video_input("https://example.com/v", None)

        mock_dl.assert_called_once_with("https://example.com/v")
        assert result == fake_path

    @pytest.mark.asyncio
    async def test_routes_to_upload_handler(self):
        """File only → delegates to save_uploaded_file."""
        upload = MagicMock(spec=UploadFile)
        upload.filename = "clip.mp4"
        fake_path = Path("temp/fake.mp4")

        with patch(
            "services.input_processing.save_uploaded_file",
            return_value=fake_path,
        ) as mock_save:
            result = await get_video_input(None, upload)

        mock_save.assert_called_once_with(upload)
        assert result == fake_path
