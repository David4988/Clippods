"""
services/audio_extraction.py — Task 2: extract_audio
Extracts a 16 kHz mono PCM WAV audio track from a video file using ffmpeg-python.
"""
from pathlib import Path

import ffmpeg
from fastapi import HTTPException

from utils import get_temp_path


# ---------------------------------------------------------------------------
# Sub-task 2.1: FFmpeg Integration
# Sub-task 2.2: Error Handling (corrupt/missing audio)
# ---------------------------------------------------------------------------

def extract_audio(video_path: str) -> str:
    """
    Extract the audio track from *video_path* and write it as a 16 kHz mono WAV.

    Parameters
    ----------
    video_path : str
        Absolute or relative path to the source video file.

    Returns
    -------
    str
        Absolute path string to the extracted .wav file in temp/.

    Raises
    ------
    HTTPException(400)
        If the video file does not exist, contains no audio stream,
        or the ffmpeg process fails (e.g. corrupt container).
    """
    import time
    from utils import log_instrumentation

    start_time = time.time()
    log_instrumentation("audio extraction")

    try:
        src = Path(video_path)

        # --- Guard 1: file must exist -------------------------------------------
        if not src.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Video file not found: {video_path}",
            )

        # --- Guard 2: probe for at least one audio stream -----------------------
        try:
            probe = ffmpeg.probe(str(src))
        except ffmpeg.Error as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            raise HTTPException(
                status_code=400,
                detail=f"Could not probe video file (possibly corrupt): {stderr}",
            ) from exc

        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
        if not audio_streams:
            raise HTTPException(
                status_code=400,
                detail="Video file contains no audio track.",
            )

        # --- Extract: 16 kHz, mono, PCM s16le → WAV ----------------------------
        output_path = get_temp_path(".wav")

        try:
            (
                ffmpeg
                .input(str(src))
                .output(
                    str(output_path),
                    format="wav",
                    acodec="pcm_s16le",   # 16-bit PCM — universal STT compatibility
                    ar=16000,             # 16 kHz sample rate
                    ac=1,                 # mono
                    t=30,                 # limit to 30 seconds
                )
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
            raise HTTPException(
                status_code=400,
                detail=f"Audio extraction failed: {stderr}",
            ) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise HTTPException(
                status_code=500,
                detail="Audio extraction produced no output file.",
            )

        return str(output_path)
    finally:
        elapsed = time.time() - start_time
        log_instrumentation("audio extraction", elapsed)
