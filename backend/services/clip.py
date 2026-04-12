"""
ClipPods — Clip Extraction Service
Extracts video clips using FFmpeg and supports muxing dubbed audio.
"""

import os
import subprocess

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def preprocess_video(input_path: str, output_path: str) -> str:
    """
    Prepares video for pipeline (GPU-accelerated if possible).
    Standardizes format to mp4 with H264 & AAC.
    """
    import shutil as _shutil
    ffmpeg_path = _shutil.which("ffmpeg") or _shutil.which("ffmpeg.exe") or "ffmpeg"
    gpu_cmd = [
        ffmpeg_path, "-y", "-hwaccel", "cuda", "-i", input_path,
        "-c:v", "h264_nvenc", "-preset", "fast", "-cq", "23",
        "-c:a", "aac", output_path
    ]
    cpu_cmd = [
        ffmpeg_path, "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", output_path
    ]
    
    try:
        subprocess.run(gpu_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except Exception:
        print("GPU Preprocessing failed, falling back to CPU")
        subprocess.run(cpu_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path


def extract_video_clip(
    input_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
):
    """
    Extract a video clip from input_path between start_sec and end_sec.
    Re-encodes video using GPU if available, else CPU, to ensure exact frame cuts.
    """
    duration = end_sec - start_sec
    if duration <= 0:
        raise ValueError("Invalid duration")

    import shutil as _shutil
    ffmpeg_path = _shutil.which("ffmpeg") or _shutil.which("ffmpeg.exe") or "ffmpeg"
    cmd = [
        ffmpeg_path, "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        output_path
    ]
    
    # We rely on subprocess.run; check=True raises exception on failure
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mux_video_with_audio(video_path: str, audio_path: str, output_path: str):
    """
    Replaces the audio track of video_path with audio_path.
    Ends at the shortest stream so TTS sync doesn't freeze the final frame forever.
    """
    tmp_path = output_path + ".tmp.mp4"
    import shutil as _shutil
    ffmpeg_path = _shutil.which("ffmpeg") or _shutil.which("ffmpeg.exe") or "ffmpeg"
    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        tmp_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    import shutil
    shutil.move(tmp_path, output_path)
