"""
ClipPods — Clip Extraction Service (ML Engineer 2)
Extracts audio clips with fade in/out using FFmpeg via pydub.
"""

import os
from pydub import AudioSegment

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import CLIP_FADE_MS, CLIP_BITRATE


def extract_clip(
    audio_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> str:
    """
    Extract a clip from audio_path between start_sec and end_sec.
    Applies fade in/out. Exports as MP3.
    Returns: output_path
    """
    audio = AudioSegment.from_file(audio_path)
    clip = audio[int(start_sec * 1000):int(end_sec * 1000)]
    clip = clip.fade_in(CLIP_FADE_MS).fade_out(CLIP_FADE_MS)
    clip.export(output_path, format="mp3", bitrate=CLIP_BITRATE)
    return output_path
