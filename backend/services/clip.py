"""
ClipPods — Clip Extraction Service (ML Engineer 2)
Extracts audio clips with fade in/out using FFmpeg via pydub.
"""

import os
import subprocess

def extract_clip(
    audio_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> str:
    """
    Extract a clip from audio_path between start_sec and end_sec.
    Uses native FFmpeg -c copy for fast, memory-safe splitting.
    Returns: output_path
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-c", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path
