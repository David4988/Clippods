"""
clip.py – ML Engineer 2 (FFmpeg Extraction)
Responsibilities: take a Segment + source video → render & save .mp4 clip
"""

import os
import asyncio
from backend.models import Segment, Clip
from backend.config import STORAGE_ROOT

OUTPUTS_DIR = os.path.join(STORAGE_ROOT, "outputs")


async def render_clip(segment: Segment, video_path: str, job_id: str, clip_index: int) -> Clip:
    """
    ML Engineer 2 – Clip Rendering Node
    ─────────────────────────────────────
    Extracts a time-bounded segment from the source video using FFmpeg
    and writes it to backend/storage/outputs/.

    Args:
        segment:     A scored Segment (start_time, end_time, id).
        video_path:  Path to the original source .mp4 file.
        job_id:      Parent job UUID (used for output filename).
        clip_index:  Index of this clip within the job (0-based).

    Returns:
        Clip model pointing to the rendered .mp4 file.
    """
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    out_filename = f"{job_id}_clip{clip_index}.mp4"
    out_path = os.path.join(OUTPUTS_DIR, out_filename)
    duration = segment.end_time - segment.start_time

    print(f"[ML-ENG-2] Rendering clip {clip_index}: {segment.start_time:.1f}s → {segment.end_time:.1f}s")

    # ── Production FFmpeg command ─────────────────────────────────────────────
    # cmd = [
    #     "ffmpeg", "-y",
    #     "-ss", str(segment.start_time),
    #     "-i", video_path,
    #     "-t", str(duration),
    #     "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    #     "-c:a", "aac", "-b:a", "128k",
    #     out_path,
    # ]
    # proc = await asyncio.create_subprocess_exec(
    #     *cmd,
    #     stdout=asyncio.subprocess.DEVNULL,
    #     stderr=asyncio.subprocess.PIPE,
    # )
    # _, stderr = await proc.communicate()
    # if proc.returncode != 0:
    #     raise RuntimeError(f"FFmpeg failed: {stderr.decode()}")
    # ─────────────────────────────────────────────────────────────────────────

    # Mock: touch an empty file so the pipeline can continue end-to-end
    await asyncio.sleep(0.5)
    open(out_path, "a").close()

    return Clip(
        id=f"{job_id}_clip{clip_index}",
        segment_id=segment.id,
        start_time=segment.start_time,
        end_time=segment.end_time,
        file_path=out_path,
        duration=duration,
    )


async def render_clips(segments: list[Segment], video_path: str, job_id: str) -> list[Clip]:
    """
    Render all highlight segments concurrently.

    Args:
        segments:   Top-N scored Segment objects from select_highlights().
        video_path: Source video .mp4 path.
        job_id:     Parent job UUID.

    Returns:
        List of Clip objects for every rendered file.
    """
    tasks = [
        render_clip(seg, video_path, job_id, idx)
        for idx, seg in enumerate(segments)
    ]
    return list(await asyncio.gather(*tasks))
