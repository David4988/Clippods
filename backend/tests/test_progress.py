import time
from job_manager import create_job, update_job, get_job
from services.input_processing import format_speed, format_eta

def test_format_speed():
    assert format_speed(None) is None
    assert format_speed(500) == "500.0 B/s"
    assert format_speed(2048) == "2.0 KB/s"
    assert format_speed(2.1 * 1024 * 1024) == "2.1 MB/s"
    assert format_speed("bad") is None

def test_format_eta():
    assert format_eta(None) is None
    assert format_eta(45) == "45s"
    assert format_eta(77) == "1m 17s"
    assert format_eta("bad") is None

def test_job_manager_extensions():
    job_id = create_job()
    job = get_job(job_id)
    
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["message"] == "Queued"
    assert job["elapsed_seconds"] == 0
    assert job["speed"] is None
    assert job["eta"] is None
    
    # Verify update_job doesn't overwrite fields not passed
    update_job(job_id, progress=10, message="Downloading...")
    job = get_job(job_id)
    assert job["progress"] == 10
    assert job["message"] == "Downloading..."
    assert job["status"] == "queued" # Unchanged
    
    # Test setting values to None
    update_job(job_id, speed="2.1 MB/s", eta="1m 17s")
    job = get_job(job_id)
    assert job["speed"] == "2.1 MB/s"
    assert job["eta"] == "1m 17s"
    
    update_job(job_id, speed=None, eta=None)
    job = get_job(job_id)
    assert job["speed"] is None
    assert job["eta"] is None

def test_dynamic_elapsed_seconds():
    job_id = create_job()
    time.sleep(1.1)
    job = get_job(job_id)
    # Active job: elapsed_seconds increases dynamically
    assert job["elapsed_seconds"] >= 1
    
    # Freeze elapsed_seconds on completed status
    update_job(job_id, status="completed")
    job = get_job(job_id)
    frozen_elapsed = job["elapsed_seconds"]
    
    time.sleep(1.1)
    job2 = get_job(job_id)
    # Frozen job: elapsed_seconds remains constant
    assert job2["elapsed_seconds"] == frozen_elapsed
