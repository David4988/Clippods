from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Faster-Whisper model initialisation (Lazy Loaded)
# ---------------------------------------------------------------------------
import logging
import os
import threading

logger = logging.getLogger(__name__)

# On serverless the only writable location is /tmp. On a normal machine leave the
# default (~/.cache/huggingface) alone — pinning it to /tmp means the ~150MB model
# is re-downloaded after every reboot, which is not something you want happening
# in the middle of a live demo.
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ.setdefault("HF_HOME", "/tmp/huggingface")

_model = None
_model_lock = threading.Lock()
_model_load_error: str | None = None


def get_model():
    """
    Return the shared Faster-Whisper model, loading it on first use.

    Returns None if it cannot be loaded; the reason is kept in
    `_model_load_error`. A failed load is retried on the next call, so a
    transient problem (e.g. the first model download failing) does not disable
    transcription for the life of the process.
    """
    global _model, _model_load_error
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel("base", device="cpu", compute_type="int8")
            _model_load_error = None
            logger.info("Faster-Whisper 'base' model loaded (cpu/int8).")
        except Exception as e:
            _model_load_error = f"{type(e).__name__}: {e}"
            logger.error("Faster-Whisper could not be loaded: %s", _model_load_error)

    return _model

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Segment(TypedDict):
    start: float
    end: float
    text: str


class TranscriptResult(TypedDict):
    segments: list[Segment]


# Transcription occupies this slice of the job progress bar (the router sets 60
# before calling and 75 when selection starts).
_PROGRESS_START = 60
_PROGRESS_END = 74


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def transcribe(audio_path: str, job_id: str | None = None) -> TranscriptResult:
    """
    Transcribe *audio_path* with the legacy configuration (model "base",
    cpu/int8, beam 5, automatic language detection, no VAD, no word timestamps).

    With a job_id, progress is reported as decoding advances and cancellation is
    honoured between segments. Neither changes what is decoded.

    Raises HTTPException:
      400  audio missing or empty
      499  job cancelled during transcription
      502  Faster-Whisper failed while transcribing (message keeps the cause)
      503  Faster-Whisper could not be loaded (no stub transcript is produced)
    """
    import time
    from utils import log_instrumentation

    start_time = time.time()
    log_instrumentation("transcription")

    try:
        src = Path(audio_path)

        if not src.exists() or src.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file not found or empty: {audio_path}",
            )

        model = get_model()

        if model is None:
            # Previously a fake 30-second transcript was returned here and the
            # job "succeeded" with clips cut from nothing.
            raise HTTPException(
                status_code=503,
                detail=(
                    "Transcription is unavailable: Faster-Whisper could not be loaded "
                    f"({_model_load_error or 'unknown error'}). Install the backend "
                    "dependencies into .venv312 (see README) and restart the server."
                ),
            )

        segments: list[Segment] = []
        try:
            # faster-whisper decodes lazily: model.transcribe() only detects the
            # language, and the real decoding happens while iterating. Both
            # parts must be inside this error boundary.
            segments_generator, info = model.transcribe(audio_path, beam_size=5)
            total_duration = getattr(info, "duration", None)
            last_progress = None

            for seg in segments_generator:
                start = seg.start
                end = seg.end
                text = seg.text or ""

                if start is not None and end is not None:
                    segments.append(
                        Segment(
                            start=float(start),
                            end=float(end),
                            text=text.strip(),
                        )
                    )

                if job_id is not None:
                    last_progress = _report_progress(job_id, end, total_duration, last_progress)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Transcription failed: {type(exc).__name__}: {exc}",
            ) from exc

        return TranscriptResult(segments=segments)
    finally:
        elapsed = time.time() - start_time
        log_instrumentation("transcription", elapsed)


def _report_progress(job_id: str, position: float | None, total: float | None,
                     last_progress: int | None) -> int | None:
    """Honour cancellation and publish progress. Returns the last published value."""
    from job_manager import is_job_cancelled, update_job

    if is_job_cancelled(job_id):
        raise HTTPException(status_code=499, detail="Job cancelled by user.")

    if not total or position is None:
        return last_progress

    fraction = max(0.0, min(1.0, float(position) / float(total)))
    progress = _PROGRESS_START + int(fraction * (_PROGRESS_END - _PROGRESS_START))
    if progress != last_progress:
        update_job(
            job_id,
            progress=progress,
            message=f"Transcribing audio... {_clock(position)} / {_clock(total)}",
        )
    return progress


def _clock(seconds: float) -> str:
    seconds = int(max(0, min(seconds, 359999)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
