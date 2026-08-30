"""
tests/test_upload_contract.py — Frontend/backend contract for POST /process/upload.

These cover the upload paths that actually broke in practice: the form field name,
the Content-Type values real browsers send, and filenames that are not simple
identifiers. Validation happens before the pipeline runs, so these are fast.
"""
import io

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from job_manager import get_job
from services.job_worker import JobWorkerPool

client = TestClient(app)

# A tiny non-empty payload. Validation is by extension + Content-Type, so the
# bytes only need to be non-empty — the pipeline rejects them later.
_PAYLOAD = b"\x00\x00\x00\x18ftypmp42" + b"x" * 64


def _upload(filename, content=_PAYLOAD, content_type="video/mp4"):
    return client.post(
        "/process/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


class TestUploadAccepted:
    def test_valid_mp4_creates_job(self):
        resp = _upload("demo.mp4")
        assert resp.status_code == 202, resp.text
        assert "job_id" in resp.json()

    @pytest.mark.parametrize("filename", ["demo.mov", "demo.mkv", "demo.webm"])
    def test_all_documented_extensions_accepted(self, filename):
        resp = _upload(filename)
        assert resp.status_code == 202, resp.text

    def test_filename_with_spaces_accepted(self):
        """Browsers send the raw filename; spaces must not break the upload."""
        resp = _upload("My Demo Clip (final).mp4")
        assert resp.status_code == 202, resp.text

    def test_uppercase_extension_accepted(self):
        resp = _upload("DEMO.MP4")
        assert resp.status_code == 202, resp.text

    @pytest.mark.parametrize(
        "content_type",
        ["", "application/octet-stream", "video/mp4; charset=binary"],
    )
    def test_generic_content_types_accepted(self, content_type):
        """
        Browsers send an empty or generic Content-Type for video files on many
        OS/browser combinations. The extension whitelist is the real gate, so
        these must not be rejected.
        """
        resp = _upload("demo.mp4", content_type=content_type)
        assert resp.status_code == 202, resp.text


class TestUploadRejected:
    def test_unsupported_extension(self):
        resp = _upload("notes.txt")
        assert resp.status_code == 400
        assert "Unsupported file extension" in resp.json()["error"]

    def test_extensionless_filename(self):
        resp = _upload("video")
        assert resp.status_code == 400
        assert "Unsupported file extension" in resp.json()["error"]

    def test_contradicting_content_type_still_rejected(self):
        """Relaxing generic types must not disable the check entirely."""
        resp = _upload("demo.mp4", content_type="text/plain")
        assert resp.status_code == 400
        assert "Unsupported content type" in resp.json()["error"]

    def test_empty_upload(self):
        resp = _upload("demo.mp4", content=b"")
        assert resp.status_code == 400
        assert "empty" in resp.json()["error"].lower()

    def test_missing_file_field(self):
        """No multipart part at all → contract error shape, never {"detail": ...}."""
        resp = client.post("/process/upload")
        assert resp.status_code == 422
        assert "error" in resp.json()
        assert "detail" not in resp.json()

    def test_wrong_field_name(self):
        """The frontend must send the part as `file`."""
        resp = client.post(
            "/process/upload",
            files={"video": ("demo.mp4", io.BytesIO(_PAYLOAD), "video/mp4")},
        )
        assert resp.status_code == 422
        assert "error" in resp.json()


class TestUploadFilenameSafety:
    @pytest.mark.parametrize(
        "filename",
        [
            "../../../../etc/passwd.mp4",
            "..\\..\\windows\\system32\\evil.mp4",
            "demo.mp4\x00.txt",
            "/absolute/path/demo.mp4",
        ],
    )
    def test_unsafe_filenames_never_escape_temp_dir(self, filename):
        """
        The client-supplied filename is used only for its extension — the file on
        disk is named from a fresh UUID — so traversal attempts cannot write
        outside temp/. Either the request is rejected or it is stored safely;
        what must never happen is a write outside TEMP_DIR.
        """
        before = set(config.TEMP_DIR.iterdir())
        resp = _upload(filename)
        assert resp.status_code in (202, 400), resp.text

        for path in set(config.TEMP_DIR.iterdir()) - before:
            assert path.parent == config.TEMP_DIR
            assert ".." not in path.name


class TestWorkerPoolLifecycle:
    def test_submit_job_does_not_deadlock_when_pool_not_started(self):
        """
        Regression: submit_job() held a non-reentrant lock while calling start(),
        which re-acquired it. Any upload arriving before/without startup wedged
        the request thread forever and the job never left 'queued'.
        """
        pool = JobWorkerPool(num_workers=1)
        pool.synchronous = False
        try:
            assert pool.submit_job("job-deadlock-check", lambda: None) is True
        finally:
            pool.stop()

    def test_job_never_left_in_non_terminal_state(self):
        """A task that dies without updating the job must still end terminal."""
        from job_manager import create_job

        pool = JobWorkerPool(num_workers=1)
        pool.synchronous = False
        job_id = create_job()
        try:
            def _explode():
                raise RuntimeError("worker blew up before touching the job")

            assert pool.submit_job(job_id, _explode) is True

            deadline_states = []
            for _ in range(100):
                state = get_job(job_id)["status"]
                deadline_states.append(state)
                if state in ("completed", "error", "cancelled"):
                    break
                import time
                time.sleep(0.05)

            assert get_job(job_id)["status"] == "error", deadline_states
        finally:
            pool.stop()


class TestTempArtifactCleanup:
    def test_removes_yt_dlp_part_fragments(self):
        """
        yt-dlp leaves `<uuid>.fNNN.<ext>.part` fragments next to the merged file.
        Deleting only the merged file leaks tens of megabytes per job.
        """
        from utils import cleanup_temp_artifacts, get_temp_path

        merged = get_temp_path(".mp4")
        stem = merged.name.split(".")[0]
        merged.write_bytes(b"merged")

        fragments = [
            config.TEMP_DIR / f"{stem}.f401.mp4.part",
            config.TEMP_DIR / f"{stem}.f140.m4a.part",
        ]
        for f in fragments:
            f.write_bytes(b"fragment")

        # An unrelated job's file must survive.
        other = get_temp_path(".mp4")
        other.write_bytes(b"other job")

        try:
            cleanup_temp_artifacts(merged)
            assert not merged.exists()
            for f in fragments:
                assert not f.exists(), f"leaked {f.name}"
            assert other.exists(), "cleanup removed an unrelated job's file"
        finally:
            for f in [merged, other, *fragments]:
                if f.exists():
                    f.unlink()
