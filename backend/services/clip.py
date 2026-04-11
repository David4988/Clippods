# backend/services/clip.py

"""
clip.py – ML Engineer 2 (Clip Extractor)
Responsibilities: Cut audio/video at exact timestamps via FFmpeg
"""

import asyncio
import os
from typing import List, Tuple

from config import STORAGE_ROOT

OUTPUTS_DIR = os.path.join(STORAGE_ROOT, "outputs")

# Limit concurrent FFmpeg processes to avoid OOM on low-resource machines
_ffmpeg_semaphore = asyncio.Semaphore(3)


async def generate_clips(
    input_file: str,
    segments,
    video_id: str,
) -> List[Tuple[int, str]]:
    """
    Generate video clips using FFmpeg (parallel async subprocess).

    Args:
        input_file: path to original video/audio
        segments:   list of Segment objects with start_time / end_time
        video_id:   unique job identifier for output filenames

    Returns:
        list of (segment_index, output_path) tuples — only successfully
        rendered clips are included, preserving correct index mapping.
    """
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    async def _cut_clip(i: int, seg) -> Tuple[int, str] | None:
        async with _ffmpeg_semaphore:
            # Validate timestamps
            if seg.end_time <= seg.start_time:
                print(f"[CLIP] ❌ Invalid segment {i}: start >= end")
                return None

            output_path = os.path.join(OUTPUTS_DIR, f"clip_{video_id}_{i}.mp4")

            print(f"\n[CLIP] ▶ Cutting clip {i}")
            print(f"[CLIP] Input:  {input_file}")
            print(f"[CLIP] Range:  {seg.start_time}s → {seg.end_time}s")
            print(f"[CLIP] Output: {output_path}")

            command = [
                "ffmpeg",
                "-y",
                "-ss", str(seg.start_time),   # fast seek
                "-to", str(seg.end_time),
                "-i", input_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
                "-loglevel", "error",
                output_path,
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

                if proc.returncode != 0:
                    print(f"[CLIP] ❌ FFmpeg error clip {i}: {stderr.decode()}")

                    # Cleanup failed file
                    if os.path.exists(output_path):
                        os.remove(output_path)

                    return None

                print(f"[CLIP] ✅ Finished clip {i}")
                return (i, output_path)

            except asyncio.TimeoutError:
                print(f"[CLIP] ❌ Clip {i} timed out (>300s)")

                if os.path.exists(output_path):
                    os.remove(output_path)

                return None

            except Exception as e:
                print(f"[CLIP] ❌ Exception clip {i}: {e}")

                if os.path.exists(output_path):
                    os.remove(output_path)

                return None

    # Run all clips in parallel (bounded by _ffmpeg_semaphore)
    tasks = [_cut_clip(i, seg) for i, seg in enumerate(segments)]
    results = await asyncio.gather(*tasks)

    # Return only successful (index, path) tuples
    return [r for r in results if r is not None]