import json
import tempfile
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app
from services.segment_selection import select_segments
from services.analysis_collector import AnalysisCollector
import config

client = TestClient(app)

def test_analysis_collector_unit():
    timestamps = [
        {"start": 10.0, "end": 12.0, "text": "Hello, this is Speaker A."},
        {"start": 13.0, "end": 20.0, "text": "And this is Speaker B joining in."}
    ]
    collector = AnalysisCollector(
        video_duration=30.0,
        config={"max_clips": 3},
        transcript=timestamps,
        algorithm_version="test_v1",
        schema_version="1.0"
    )
    collector.start_timer()
    collector.begin_candidate(10.0)
    collector.record_energy_filter(5.0, 10.0, 0.6, True)
    collector.record_stopping_point({
        "timestamp": 20.0,
        "clip_duration_at_point": 10.0,
        "total_score": 5,
        "score_breakdown": []
    })
    
    metrics = {"raw_score": 4.5, "word_density": 2.5}
    start_analysis = {"timestamp": 10.0, "checks": []}
    end_analysis = {"timestamp": 20.0, "total_score": 5, "score_breakdown": []}
    
    collector.finalize_candidate(20.0, metrics, start_analysis, end_analysis)
    collector.mark_candidate_selected(0, 0)
    
    collector.record_final_clip({
        "clip_index": 0,
        "candidate_id": 0,
        "filename": "clip_0.mp4",
        "start": 10.0,
        "end": 20.0
    })
    collector.stop_timer()
    
    data = collector.to_dict()
    assert data["meta"]["algorithm_version"] == "test_v1"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["selected"] is True
    assert data["candidates"][0]["final_rank"] == 0
    assert len(data["final_clips"]) == 1
    assert data["stats"]["total_candidates"] == 1


def test_select_segments_with_analysis():
    timestamps = [
        {"start": 5.0, "end": 10.0, "text": "This is a sentence starting and ending.", "speaker": "Speaker_A"},
        {"start": 11.0, "end": 18.0, "text": "Follow up segment.", "speaker": "Speaker_B"}
    ]
    result = select_segments(timestamps, 40.0, collect_analysis=True)
    assert isinstance(result, tuple)
    selected, analysis = result
    assert isinstance(selected, list)
    assert isinstance(analysis, dict)
    assert "meta" in analysis
    assert "candidates" in analysis
    assert "final_clips" in analysis
    assert "stats" in analysis
    assert len(analysis["final_clips"]) == 3  # because max_clips defaults to 3


def test_analysis_endpoints(tmp_path, monkeypatch):
    # Mock _get_outputs_dir to use a temp dir for test isolation
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    
    # Create a mock run directory and analysis.json with a valid UUID
    run_uuid = str(uuid.uuid4())
    run_dir = outputs_dir / run_uuid
    run_dir.mkdir()
    
    mock_analysis = {
        "meta": {
            "job_id": str(uuid.uuid4()),
            "filename": "test_video.mp4",
            "source": "youtube",
            "video_duration_seconds": 60.0,
            "timestamp": "2026-07-01T21:00:00Z",
            "algorithm_version": "test_v1"
        },
        "final_clips": [
            {"clip_index": 0, "filename": "clip_0.mp4"}
        ],
        "stats": {
            "total_candidates": 5
        }
    }
    
    (run_dir / "analysis.json").write_text(json.dumps(mock_analysis))
    (run_dir / "original.mp4").write_text("dummy-video-content")
    
    # Patch the _get_outputs_dir in routers.analysis
    from routers import analysis as routers_analysis
    monkeypatch.setattr(routers_analysis, "_get_outputs_dir", lambda: outputs_dir)
    
    # Mock ENABLE_DEBUGGER to True for endpoints testing
    monkeypatch.setattr(config, "ENABLE_DEBUGGER", True)
    
    # Test list jobs
    response = client.get("/dev/analysis/jobs")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["count"] == 1
    assert res_data["jobs"][0]["run_uuid"] == run_uuid
    assert res_data["jobs"][0]["filename"] == "test_video.mp4"

    # Test get specific run
    response = client.get(f"/dev/analysis/{run_uuid}")
    assert response.status_code == 200
    
    # Test get non-existent run
    response = client.get(f"/dev/analysis/{str(uuid.uuid4())}")
    assert response.status_code == 404

    # Test summary
    response = client.get(f"/dev/analysis/{run_uuid}/summary")
    assert response.status_code == 200
    summary = response.json()
    assert "meta" in summary
    assert "stats" in summary
    assert summary["final_clips_count"] == 1

    # Test video streaming
    response = client.get(f"/dev/video/{run_uuid}")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "video/mp4"
    assert response.content == b"dummy-video-content"
