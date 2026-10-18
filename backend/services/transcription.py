"""
services/transcription.py — source-language ASR with Faster-Whisper.

`transcribe_rich()` returns the typed Transcript contract (services/transcript.py):
language and confidence metadata, per-segment quality fields, optional word
timestamps, measured speech regions and visible quality flags.

`transcribe()` is the legacy entry point and returns only
`{"segments": [{"start", "end", "text"}]}`, decoded exactly as before.

ASR profiles (the decode settings are what change transcripts):

  legacy   base · cpu/int8 · beam 5 · no word timestamps · no VAD filter.
           Decodes identically to the pre-contract pipeline, so legacy_v2
           output is unchanged. Speech regions and language probes are measured
           on the side and never feed the decoder.
  rich_v1  legacy + word timestamps + VAD filter (faster-whisper defaults)
           + script-aware fallback: for Hindi/Tamil the byte-level
           compression-ratio fallback trigger is disabled (EV-2.4), while the
           log-probability fallback stays. Word timestamps move the decoder's
           seek position, so segment boundaries can differ from `legacy`.
           Intended for boundary-aware engines.

task is always "transcribe": speech is never translated.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional, TypedDict

from fastapi import HTTPException

from services.transcript import (
    LANGUAGE_MODES,
    SCHEMA,
    LanguageInfo,
    LanguageProbe,
    Transcript,
    TranscriptSegment,
    Word,
)

logger = logging.getLogger(__name__)

# On serverless the only writable location is /tmp. On a normal machine leave the
# default (~/.cache/huggingface) alone — pinning it to /tmp means the ~150MB model
# is re-downloaded after every reboot, which is not something you want happening
# in the middle of a live demo.
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ.setdefault("HF_HOME", "/tmp/huggingface")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AsrProfile:
    name: str
    model: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    word_timestamps: bool = False
    vad_filter: bool = False
    vad_parameters: Optional[dict] = None       # None = faster-whisper VadOptions defaults
    condition_on_previous_text: bool = True
    language_detection_segments: int = 1
    # faster-whisper defaults: fall back through these temperatures when a window's
    # compression_ratio > 2.4 or avg_logprob < -1.0. The ratio is byte-level and
    # script-biased (EV-2.4), so the fallback can misfire on Tamil.
    temperature: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    compression_ratio_threshold: Optional[float] = 2.4
    # When True, the language is resolved before decoding (forced, or detected on
    # the same audio the decoder sees) and passed explicitly; for languages in
    # NON_LATIN_SCRIPT_LANGUAGES the compression-ratio fallback trigger is disabled.
    script_aware_compression: bool = False
    # Measured alongside decoding; never change what the decoder sees.
    speech_regions: bool = True
    language_probes: int = 8                    # 30 s speech windows spread across the file


PROFILES: dict[str, AsrProfile] = {
    "legacy": AsrProfile(name="legacy"),
    "rich_v1": AsrProfile(name="rich_v1", word_timestamps=True, vad_filter=True,
                          script_aware_compression=True),
}

# Per-language decode profiles for the adaptive pipeline (services/asr_pipeline.py).
# All are rich_v1 + a model choice; the names are versioned so a transcript records
# exactly which settings produced it. Evidence: EV-3.1 (base good on English),
# EV-3.2/3.11 (large-v3 needed for Hindi/Tamil), EV-3.13 (previous-text conditioning
# keeps the code-switch script convention, so attempt 1 keeps it ON; the retry flips it).
_RICH = PROFILES["rich_v1"]
PROFILES.update({
    "en_v1": replace(_RICH, name="en_v1", model="base"),
    # D30 (EV-5.1): Hindi attempt 1 also runs with previous-text OFF. On Hindi-dominant
    # windows OFF beat ON on 4 of 5 (hi2 early 148 vs 73, hi2 late 139 vs 116, hi1 125
    # vs 19, hi3 early 116 vs 41 trusted words/min); only hi2 middle favoured ON. The
    # regional retry flips it back ON, so that behaviour stays reachable per region.
    "hi_v1": replace(_RICH, name="hi_v1", model="large-v3", condition_on_previous_text=False),
    # CP3/D25: Tamil attempt 1 runs with previous-text OFF. ON was far worse on both
    # tested Tamil windows (EV-3.11: 44 -> 138 and 15 -> 87 trusted words/min) and
    # collapsed to hard_fail on a full-length file (EV-4.4). The regional retry flips
    # it back ON, so previous-text conditioning is still reachable per region.
    "ta_v1": replace(_RICH, name="ta_v1", model="large-v3", condition_on_previous_text=False),
    # CP3/D29: PROPOSED, UNVALIDATED. The 0.4 temperature cap comes from EV-3.3
    # (unbounded fallback to T=1.0 produced word salad), but this profile has never
    # been measured as a whole, and no real-podcast `mixed` run exists yet.
    "mixed_v1": replace(_RICH, name="mixed_v1", model="large-v3", temperature=(0.0, 0.2, 0.4)),
})

# Whisper's compression ratio is gzip over UTF-8 bytes; clean text in these
# scripts already exceeds the 2.4 trigger (EV-2.4), so it misfires as "repetition".
NON_LATIN_SCRIPT_LANGUAGES = ("hi", "ta")

# What the legacy transcribe() wrapper runs: the legacy decode with nothing extra,
# so it never needs to decode audio itself.
_LEGACY_PLAIN = replace(PROFILES["legacy"], speech_regions=False, language_probes=0)


def get_profile(name: str) -> AsrProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown ASR profile {name!r}; available: {sorted(PROFILES)}") from None


# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

_models: dict[tuple[str, str, str], object] = {}
_model_lock = threading.Lock()
_model_load_error: str | None = None


def get_model(model: str = "base", device: str = "cpu", compute_type: str = "int8"):
    """
    Return a shared Faster-Whisper model, loading it on first use.

    Returns None if it cannot be loaded; the reason is kept in
    `_model_load_error`. A failed load is retried on the next call.
    """
    global _model_load_error
    key = (model, device, compute_type)
    if key in _models:
        return _models[key]

    with _model_lock:
        if key in _models:
            return _models[key]
        try:
            from faster_whisper import WhisperModel
            from config import ASR_MODEL_DIR
            _models[key] = WhisperModel(model, device=device, compute_type=compute_type,
                                        download_root=ASR_MODEL_DIR)
            _model_load_error = None
            logger.info("Faster-Whisper '%s' model loaded (%s/%s).", model, device, compute_type)
        except Exception as e:
            _model_load_error = f"{type(e).__name__}: {e}"
            logger.error("Faster-Whisper could not be loaded: %s", _model_load_error)
            return None
    return _models[key]


# ---------------------------------------------------------------------------
# Legacy types and entry point
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


def transcribe(audio_path: str, job_id: str | None = None) -> TranscriptResult:
    """
    Legacy entry point: the legacy decode, returning only start/end/text.

    Raises HTTPException:
      400  audio missing or empty
      499  job cancelled during transcription
      502  Faster-Whisper failed while transcribing (message keeps the cause)
      503  Faster-Whisper could not be loaded (no stub transcript is produced)
    """
    transcript = transcribe_rich(audio_path, job_id=job_id, profile=_LEGACY_PLAIN)
    return TranscriptResult(segments=transcript.legacy_segments())


# ---------------------------------------------------------------------------
# Rich transcription
# ---------------------------------------------------------------------------

def transcribe_rich(
    audio_path: str,
    *,
    job_id: str | None = None,
    profile: AsrProfile | str = "legacy",
    language_mode: str = "auto",
    prepared: "PreparedAudio | None" = None,
) -> Transcript:
    """
    Transcribe *audio_path* in its spoken language and return a Transcript.

    language_mode: "auto" (detect) or a forced "en" | "hi" | "ta".
    prepared: decoded audio, speech regions and probes already measured by the
    caller (adaptive pipeline), so they are not computed twice.
    Failures raise (see transcribe()); a transcript is never fabricated.
    """
    from services import transcript_quality
    from utils import log_instrumentation

    if isinstance(profile, str):
        profile = get_profile(profile)
    if language_mode not in LANGUAGE_MODES:
        raise HTTPException(status_code=400, detail=f"language must be one of {list(LANGUAGE_MODES)}")

    started = time.time()
    timings: dict[str, float] = {}
    log_instrumentation("transcription")
    try:
        src = Path(audio_path)
        if not src.exists() or src.stat().st_size == 0:
            raise HTTPException(status_code=400, detail=f"Audio file not found or empty: {audio_path}")

        model = get_model(profile.model, profile.device, profile.compute_type)
        if model is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Transcription is unavailable: Faster-Whisper could not be loaded "
                    f"({_model_load_error or 'unknown error'}). Install the backend "
                    "dependencies into .venv312 (see README) and restart the server."
                ),
            )

        pre_detect = profile.script_aware_compression and language_mode == "auto"
        needs_audio = profile.speech_regions or profile.language_probes > 0 or pre_detect
        audio = None
        speech = None
        probes: list[LanguageProbe] = []
        if prepared is not None:
            audio, speech, probes = prepared.audio, prepared.speech, list(prepared.probes)
            needs_audio = False

        try:
            if needs_audio:
                t0 = time.perf_counter()
                from faster_whisper import decode_audio
                audio = decode_audio(str(src), sampling_rate=16000)
                timings["decode_audio_s"] = round(time.perf_counter() - t0, 3)

            if profile.speech_regions and prepared is None:
                _raise_if_cancelled(job_id)
                t0 = time.perf_counter()
                from services.speech_regions import detect_speech_regions
                speech = detect_speech_regions(audio)
                timings["speech_regions_s"] = round(time.perf_counter() - t0, 3)

            if profile.language_probes > 0 and prepared is None:
                _raise_if_cancelled(job_id)
                t0 = time.perf_counter()
                probes = _probe_languages(model, audio, speech, profile.language_probes)
                timings["language_probes_s"] = round(time.perf_counter() - t0, 3)

            decode_language = None if language_mode == "auto" else language_mode
            detection = None
            if profile.script_aware_compression:
                if pre_detect:
                    _raise_if_cancelled(job_id)
                    t0 = time.perf_counter()
                    # Same audio the decoder will see (VAD-filtered when the profile filters).
                    detected, probability, all_probs = model.detect_language(
                        audio=audio,
                        vad_filter=profile.vad_filter,
                        vad_parameters=profile.vad_parameters,
                        language_detection_segments=profile.language_detection_segments,
                    )
                    detection = (detected, probability, all_probs)
                    decode_language = detected
                    timings["language_detection_s"] = round(time.perf_counter() - t0, 3)
            decode_options = decode_options_for(profile, decode_language)

            _raise_if_cancelled(job_id)
            t0 = time.perf_counter()
            segments, info = _decode(model, audio if audio is not None else str(src), profile,
                                     decode_language, decode_options, job_id)
            total_duration = getattr(info, "duration", None)
            timings["decode_s"] = round(time.perf_counter() - t0, 3)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Transcription failed: {type(exc).__name__}: {exc}",
            ) from exc

        audio_duration = (
            round(len(audio) / 16000, 3) if audio is not None
            else round(float(total_duration), 3) if isinstance(total_duration, (int, float))
            else (segments[-1].end if segments else 0.0)
        )

        forced = language_mode != "auto"
        if detection is not None:
            detected_probability, detected_top = detection[1], detection[2]
        else:
            detected_probability = getattr(info, "language_probability", None)
            detected_top = getattr(info, "all_language_probs", None)
        language = LanguageInfo(
            mode=language_mode,
            language=getattr(info, "language", None) or decode_language or "unknown",
            probability=None if forced else _float(detected_probability),
            top=[] if forced else [(code, round(float(p), 4)) for code, p in (detected_top or [])[:5]],
            probes=probes,
            uncertain=False,
            reasons=[],
        )

        t0 = time.perf_counter()
        transcript_quality.assess_language(language)
        transcript_quality.flag_segments(segments, language.language, audio_duration, speech)
        quality = transcript_quality.summarise(segments, language, speech)
        timings["quality_s"] = round(time.perf_counter() - t0, 3)
        timings["total_s"] = round(time.time() - started, 3)

        return Transcript(
            schema=SCHEMA,
            asr=_asr_record(profile, language_mode, info, decode_options, detection is not None),
            audio_duration=audio_duration,
            language=language,
            segments=segments,
            speech_regions=speech,
            quality=quality,
            timings=timings,
        )
    finally:
        log_instrumentation("transcription", time.time() - started)


# ---------------------------------------------------------------------------
# shared decode (full file and adaptive-pipeline regions)
# ---------------------------------------------------------------------------

@dataclass
class PreparedAudio:
    """Measurements the adaptive pipeline takes once and shares across attempts."""
    audio: object                           # float32 mono 16 kHz numpy array
    speech: Optional[object]                # SpeechRegions
    probes: list[LanguageProbe]


def decode_options_for(profile: AsrProfile, language: Optional[str]) -> dict:
    """Decode options beyond the fixed ones, including the script-aware override."""
    options = _non_default_decode_options(profile)
    if profile.script_aware_compression and language in NON_LATIN_SCRIPT_LANGUAGES:
        options["compression_ratio_threshold"] = None
    return options


def _decode(model, source, profile: AsrProfile, language: Optional[str], decode_options: dict,
            job_id: str | None, offset: float = 0.0) -> tuple[list[TranscriptSegment], object]:
    """
    Run the decoder on *source* (path or audio array) and collect contract segments.
    *offset* shifts segment and word times, so a decoded region lands in whole-file time.
    """
    segments_generator, info = model.transcribe(
        source,
        task="transcribe",
        language=language,
        beam_size=profile.beam_size,
        word_timestamps=profile.word_timestamps,
        vad_filter=profile.vad_filter,
        vad_parameters=profile.vad_parameters,
        condition_on_previous_text=profile.condition_on_previous_text,
        language_detection_segments=profile.language_detection_segments,
        **decode_options,
    )
    total_duration = getattr(info, "duration", None)
    segments: list[TranscriptSegment] = []
    last_progress = None

    # Decoding happens lazily while iterating; keep it inside the caller's error boundary.
    for raw in segments_generator:
        if raw.start is not None and raw.end is not None:
            segments.append(_segment_from(raw, len(segments), profile.word_timestamps, offset))
        if job_id is not None:
            last_progress = _report_progress(job_id, raw.end, total_duration, last_progress)
    return segments, info


def prepare_audio(audio_path: str, probe_model, probe_count: int = 8,
                  job_id: str | None = None) -> PreparedAudio:
    """Decode audio once, measure speech regions and run language probes."""
    from faster_whisper import decode_audio
    from services.speech_regions import detect_speech_regions

    audio = decode_audio(str(audio_path), sampling_rate=16000)
    _raise_if_cancelled(job_id)
    speech = detect_speech_regions(audio)
    _raise_if_cancelled(job_id)
    probes = _probe_languages(probe_model, audio, speech, probe_count) if probe_count > 0 else []
    return PreparedAudio(audio=audio, speech=speech, probes=probes)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _non_default_decode_options(profile: AsrProfile) -> dict:
    """Only pass fallback settings that differ from faster-whisper's defaults."""
    defaults = AsrProfile(name="defaults")
    options = {}
    if profile.temperature != defaults.temperature:
        options["temperature"] = list(profile.temperature)
    if profile.compression_ratio_threshold != defaults.compression_ratio_threshold:
        options["compression_ratio_threshold"] = profile.compression_ratio_threshold
    return options


def _float(value) -> Optional[float]:
    return None if value is None else round(float(value), 4)


def _segment_from(raw, index: int, with_words: bool, offset: float = 0.0) -> TranscriptSegment:
    words = None
    if with_words:
        words = [
            Word(start=round(float(w.start) + offset, 3), end=round(float(w.end) + offset, 3), text=w.word,
                 probability=_float(getattr(w, "probability", None)))
            for w in (getattr(raw, "words", None) or [])
            if w.start is not None and w.end is not None
        ]
    tokens = getattr(raw, "tokens", None)
    return TranscriptSegment(
        id=index,
        start=round(float(raw.start) + offset, 3) if offset else float(raw.start),
        end=round(float(raw.end) + offset, 3) if offset else float(raw.end),
        text=(raw.text or "").strip(),
        avg_logprob=_float(getattr(raw, "avg_logprob", None)),
        compression_ratio=_float(getattr(raw, "compression_ratio", None)),
        no_speech_prob=_float(getattr(raw, "no_speech_prob", None)),
        temperature=_float(getattr(raw, "temperature", None)),
        token_count=len(tokens) if isinstance(tokens, (list, tuple)) else None,
        words=words,
    )


def _asr_record(profile: AsrProfile, language_mode: str, info, decode_options: dict,
                pre_detected: bool) -> dict:
    def pkg(name):
        try:
            return version(name)
        except PackageNotFoundError:
            return None

    options = getattr(info, "transcription_options", None)
    vad_options = getattr(info, "vad_options", None)
    return {
        "engine": "faster-whisper",
        "profile": profile.name,
        "settings": asdict(profile),
        "task": "transcribe",
        "language_mode": language_mode,
        "versions": {"faster-whisper": pkg("faster-whisper"), "ctranslate2": pkg("ctranslate2")},
        # What faster-whisper reports it actually used (defaults included).
        "effective_options": _plain(options),
        "effective_vad_options": _plain(vad_options),
        "duration_after_vad": _float(getattr(info, "duration_after_vad", None)),
        # Options ClipPods passed beyond the fixed ones above (e.g. the script-aware override).
        "decode_overrides": decode_options,
        "language_detection": "pre-decode detect_language on decoder input" if pre_detected
                              else ("forced" if language_mode != "auto" else "faster-whisper transcribe"),
    }


def _plain(obj):
    if obj is None:
        return None
    try:
        data = asdict(obj)
    except TypeError:
        data = getattr(obj, "_asdict", lambda: None)() or getattr(obj, "__dict__", None)
    if not isinstance(data, dict):
        return None
    return {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool, type(None), list, tuple))}


def _probe_languages(model, audio, speech, count: int) -> list[LanguageProbe]:
    """
    Run language detection on up to *count* ~30 s windows of speech spread across
    the file. Detection on the first 30 s alone (faster-whisper's default) is
    easily fooled by intros; the probes make disagreement visible.
    """
    import math
    import numpy as np

    sr = 16000
    window_s = 30.0
    regions = speech.regions if speech is not None and speech.regions else [(0.0, len(audio) / sr)]
    total_speech = sum(e - s for s, e in regions)
    if total_speech < 1.0:
        return []

    # Positions measured in seconds of *speech* (silence and music excluded).
    if total_speech <= window_s * count:
        anchors = [i * window_s for i in range(math.ceil(total_speech / window_s))]
    else:
        stride = (total_speech - window_s) / (count - 1) if count > 1 else 0.0
        anchors = [i * stride for i in range(count)]

    probes: list[LanguageProbe] = []
    for anchor in anchors:
        pieces, gathered, speech_before = [], 0.0, 0.0
        first_start = last_end = None
        for s, e in regions:
            length = e - s
            if speech_before + length <= anchor:
                speech_before += length
                continue
            start = s + max(0.0, anchor - speech_before)
            speech_before += length
            take = min(e - start, window_s - gathered)
            if take <= 0:
                break
            pieces.append(audio[int(start * sr):int((start + take) * sr)])
            gathered += take
            first_start = start if first_start is None else first_start
            last_end = start + take
            if gathered >= window_s:
                break
        if gathered < 1.0:
            continue
        language, probability, _ = model.detect_language(audio=np.concatenate(pieces))
        probes.append(LanguageProbe(start=round(first_start, 2), end=round(last_end, 2),
                                    language=language, probability=round(float(probability), 4)))
    return probes


def _raise_if_cancelled(job_id: str | None) -> None:
    if job_id is None:
        return
    from job_manager import is_job_cancelled
    if is_job_cancelled(job_id):
        raise HTTPException(status_code=499, detail="Job cancelled by user.")


def _report_progress(job_id: str, position: float | None, total: float | None,
                     last_progress: int | None) -> int | None:
    """Honour cancellation and publish progress. Returns the last published value."""
    from job_manager import update_job

    _raise_if_cancelled(job_id)
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
