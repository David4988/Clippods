import io
import json
import time
import os
import shutil
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app
import config
from job_manager import create_job, update_job, get_job, cancel_job, is_job_cancelled
from services.job_worker import worker_pool

@pytest.fixture(autouse=True)
def enable_async_queue():
    old_sync = worker_pool.synchronous
    worker_pool.synchronous = False
    yield
    worker_pool.synchronous = old_sync

client = TestClient(app)

def test_upload_validation_invalid_ext():
    # Unsupported file extension
    files = {"file": ("video.txt", b"some content", "video/mp4")}
    response = client.post("/process/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["error"]

def test_upload_validation_invalid_mime():
    # Unsupported MIME type
    files = {"file": ("video.mp4", b"some content", "text/plain")}
    response = client.post("/process/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported content type" in response.json()["error"]

def test_upload_validation_oversized():
    # Mock size configuration temporarily to 1KB
    old_max = config.MAX_UPLOAD_SIZE_BYTES
    config.MAX_UPLOAD_SIZE_BYTES = 1024 # 1KB
    config.MAX_UPLOAD_SIZE_MB = 0.001
    
    try:
        files = {"file": ("video.mp4", b"x" * 2048, "video/mp4")} # 2KB payload
        response = client.post("/process/upload", files=files)
        assert response.status_code == 413
        assert "exceeds maximum limit" in response.json()["error"]
    finally:
        config.MAX_UPLOAD_SIZE_BYTES = old_max
        config.MAX_UPLOAD_SIZE_MB = int(old_max / (1024 * 1024))

def test_path_sanitization_traversal():
    # Attempt path traversal on serve clip endpoint using backslashes
    response = client.get("/clips/fa8e2c_clip_0.mp4\\..\\etc\\passwd")
    assert response.status_code == 400
    assert "Invalid clip name format" in response.json()["error"]

    response = client.get("/clips/fa8e2c_clip_0.mp4\\..\\sub")
    assert response.status_code == 400
    
    # Attempt traversal on dev/analysis (even if disabled, it validates uuid first)
    old_enabled = config.ENABLE_DEBUGGER
    config.ENABLE_DEBUGGER = True
    try:
        response = client.get("/dev/analysis/invalid-uuid-format")
        assert response.status_code == 400
        assert "Invalid run_uuid format" in response.json()["detail"]
    finally:
        config.ENABLE_DEBUGGER = old_enabled

def test_debugger_disabled_by_default():
    # Confirm disabled by default
    assert config.ENABLE_DEBUGGER is False
    
    response = client.get("/dev/analysis/jobs")
    assert response.status_code == 403
    
    response = client.get("/dev/analysis/fa8e2c90-0000-0000-0000-000000000000")
    assert response.status_code == 403

def test_queue_concurrency_and_position(monkeypatch):
    # Mock _run_pipeline to sleep 0.5s to allow jobs to stack in the queue
    async def mock_run_pipeline(*args, **kwargs):
        import asyncio
        await asyncio.sleep(0.5)
        return []

    from unittest.mock import patch
    with patch("routers.video._run_pipeline", new=mock_run_pipeline):
        # Submit multiple mock background run jobs and verify queue positions
        job_ids = []
        for _ in range(5):
            # Create a mock job via POST process
            response = client.post("/process", json={"video_url": "https://www.youtube.com/watch?v=mock"})
            assert response.status_code == 202
            job_ids.append(response.json()["job_id"])

        try:
            # Check status and queue position
            queued_jobs = []
            for jid in job_ids:
                status_resp = client.get(f"/status/{jid}")
                assert status_resp.status_code == 200
                data = status_resp.json()
                if data["status"] == "queued":
                    assert data["queue_position"] is not None
                    assert data["estimated_wait_seconds"] is not None
                    queued_jobs.append(data)
                    
            # Cancel the jobs to clean up
            for jid in job_ids:
                client.post(f"/cancel/{jid}")
        finally:
            pass

def test_job_cancellation_lifecycle():
    job_id = create_job()
    update_job(job_id, status="generating_clips")
    
    # Mock a running subprocess Popen handle
    # Runs a dummy ping command
    proc = subprocess.Popen(["ping", "127.0.0.1", "-n", "4"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    from job_manager import set_active_process, clear_active_process
    set_active_process(job_id, proc)
    
    try:
        # Cancel job
        cancel_resp = client.post(f"/cancel/{job_id}")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"
        
        # Verify job status in manager is updated
        job = get_job(job_id)
        assert job["status"] == "cancelled"
        assert job["error"] == "Job cancelled by user."
        
        # Check subprocess is killed
        # wait a bit
        time.sleep(0.5)
        assert proc.poll() is not None # non-None means terminated
    finally:
        proc.kill()
        clear_active_process(job_id)

def test_garbage_collection(tmp_path, monkeypatch):
    # Setup mock TEMP_DIR and OUTPUTS_DIR
    temp_dir = tmp_path / "temp"
    outputs_dir = tmp_path / "outputs"
    temp_dir.mkdir()
    outputs_dir.mkdir()
    
    # Mock settings in config
    monkeypatch.setattr(config, "TEMP_DIR", temp_dir)
    monkeypatch.setattr(config, "OUTPUTS_DIR", outputs_dir)
    monkeypatch.setattr(config, "TEMP_FILE_MAX_AGE_HOURS", 0.0001) # clean instantly
    monkeypatch.setattr(config, "OUTPUT_DIR_MAX_AGE_HOURS", 0.0001) # clean instantly
    
    # Create temp files
    f1 = temp_dir / "old_temp.wav"
    f1.write_text("wav file content")
    
    # Create run outputs
    r1 = outputs_dir / "fa8e2c90-0000-0000-0000-000000000000"
    r1.mkdir()
    (r1 / "clip_0.mp4").write_text("mp4 clip")
    
    # Set modify time to past for old file
    past = time.time() - 3600 # 1 hour ago
    os.utime(str(f1), (past, past))
    os.utime(str(r1), (past, past))
    
    # Run garbage collection
    from utils import run_garbage_collection
    run_garbage_collection()
    
    # Verify files deleted
    assert not f1.exists()
    assert not r1.exists()

def test_concurrent_uploads_stress():
    # Mock _run_pipeline to sleep 0.5s to keep worker threads occupied
    async def mock_run_pipeline(*args, **kwargs):
        import asyncio
        await asyncio.sleep(0.5)
        return []

    from unittest.mock import patch
    with patch("routers.video._run_pipeline", new=mock_run_pipeline):
        import concurrent.futures

        # Submit 5 concurrent multipart uploads
        def upload_one_mock(i):
            # We use a distinct name to prevent collisions
            files = {"file": (f"stress_video_{i}.mp4", b"x" * 128, "video/mp4")}
            return client.post("/process/upload", files=files)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_one_mock, i) for i in range(5)]
            responses = [f.result() for f in futures]

        # Verify that all uploads are received and return HTTP 202 Accepted
        job_ids = []
        for resp in responses:
            assert resp.status_code == 202
            job_ids.append(resp.json()["job_id"])

        # Verify queue limits and positions dynamically
        try:
            queued_count = 0
            for jid in job_ids:
                status_resp = client.get(f"/status/{jid}")
                assert status_resp.status_code == 200
                data = status_resp.json()
                if data["status"] in ("queued", "processing", "completed"):
                    queued_count += 1

            assert queued_count > 0
        finally:
            # Cancel all stress test jobs
            for jid in job_ids:
                client.post(f"/cancel/{jid}")
