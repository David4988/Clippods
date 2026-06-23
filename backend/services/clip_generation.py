"""
services/clip_generation.py — Task 5: generate_clips
Cuts a source video into timed clips using FFmpeg stream-copy (no re-encoding).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import ffmpeg
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLIP_NAME_TEMPLATE = "{job_uuid}_clip_{index}.mp4"   # Sub-task 5.2: strict naming


# ---------------------------------------------------------------------------
# Sub-task 5.1 + 5.2: Batch FFmpeg Cutting with output naming
# ---------------------------------------------------------------------------

def generate_clips(
    video_path: str,
    segments: list[dict],
) -> list[str]:
    """
    Cut *video_path* into one MP4 clip per entry in *segments* using FFmpeg's
    fast-seek + stream-copy (no re-encoding).

    Output files are written to a unique run directory inside ``outputs/``
    and named strictly ``clip_0.mp4``, ``clip_1.mp4``, ``clip_2.mp4``.

    Parameters
    ----------
    video_path : str
        Path to the source video file.
    segments : list[dict]
        Each item must have ``"start": float`` and ``"end": float`` (seconds).
        Produced by ``select_segments()``.

    Returns
    -------
    list[str]
        Absolute path strings for each generated clip, in segment order.
        Length equals ``len(segments)``.

    Raises
    ------
    HTTPException(400)
        If the source video does not exist, segments list is empty, or any
        segment has an invalid start/end.
    HTTPException(500)
        If FFmpeg fails to produce an output file for any clip.
    """
    import time
    from utils import log_instrumentation

    start_time = time.time()
    log_instrumentation("clip generation")

    try:
        # --- Guard: source file -------------------------------------------------
        src = Path(video_path)
        if not src.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Source video not found: {video_path}",
            )

        # --- Guard: segments ----------------------------------------------------
        if not segments:
            raise HTTPException(
                status_code=400,
                detail="segments list is empty — nothing to cut.",
            )

        for i, seg in enumerate(segments):
            start = seg.get("start")
            end   = seg.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Segment {i} has non-numeric start/end: {seg}",
                )
            if end <= start:
                raise HTTPException(
                    status_code=400,
                    detail=f"Segment {i} has end ({end}) ≤ start ({start}).",
                )

        # --- Create a unique output directory per run ---------------------------
        import os
        import tempfile
        
        run_uuid = uuid.uuid4().hex
        
        if os.environ.get("VERCEL"):
            outputs_dir = Path(tempfile.gettempdir()) / "clippods_outputs"
        else:
            outputs_dir = Path(__file__).parent.parent / "outputs"
            
        run_dir = outputs_dir / run_uuid
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            run_dir = Path(tempfile.gettempdir()) / run_uuid
            run_dir.mkdir(parents=True, exist_ok=True)

        output_paths: list[str] = []

        # --- Sub-task 5.1: Batch FFmpeg fast-seek + stream-copy loop -----------
        for index, seg in enumerate(segments):
            start    = float(seg["start"])
            end      = float(seg["end"])
            duration = round(end - start, 6)

            # Sub-task 5.2: strict naming → {job_uuid}_clip_0.mp4, etc.
            out_path = run_dir / _CLIP_NAME_TEMPLATE.format(job_uuid=run_uuid, index=index)

            try:
                fade_out_start = max(0, duration - 2.5)

                (
                    ffmpeg
                    .input(str(src), ss=start)
                    .output(   
                        str(out_path),
                        t=duration,
                        vcodec="libx264",
                        acodec="aac",
                        preset="fast",
                        movflags="faststart",
                        af=f"volume=0.9,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_start}:d=2.5",
                        vf=f"fade=t=in:st=0:d=1,fade=t=out:st={fade_out_start}:d=2"
                    )
                    .overwrite_output()
                    .run(quiet=True)
                )
            except ffmpeg.Error as exc:
                stderr = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
                raise HTTPException(
                    status_code=500,
                    detail=f"FFmpeg failed on clip_{index}: {stderr}",
                ) from exc

            # Verify the file was actually written and is non-empty
            if not out_path.exists() or out_path.stat().st_size == 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"clip_{index}.mp4 was not produced by FFmpeg.",
                )

            output_paths.append(str(out_path))

        return output_paths
    finally:
        elapsed = time.time() - start_time
        log_instrumentation("clip generation", elapsed)
