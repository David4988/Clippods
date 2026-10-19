"""
Cached pipeline stages for evaluation.

Phase 0 stages reuse the production functions unchanged, so the cached artifacts
are exactly what the legacy pipeline would have produced:

    probe       ffprobe metadata of the source media
    audio       16 kHz mono PCM WAV via services.audio_extraction.extract_audio
    transcript  services.transcription.transcribe_rich (ASR profile + language mode)

Each stage declares STAGE_VERSION and a config dict; both feed the cache key.
If a production function's behaviour changes, bump the stage version (or its
config) so stale cache entries are not reused.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from evaluation.cache import CacheResult, StageCache
from evaluation.resources import Measure
from evaluation.storage import read_json, write_json


class StageError(RuntimeError):
    pass


def _package_version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return None


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

PROBE_VERSION = "1"


def run_probe(cache: StageCache, media_path: Path, media_sha256: str) -> CacheResult:
    def build(work: Path) -> dict:
        import ffmpeg
        with Measure() as m:
            probe = ffmpeg.probe(str(media_path))
        write_json(work / "probe.json", probe)
        streams = probe.get("streams", [])
        return {
            **m.as_dict(),
            "duration_s": float(probe["format"]["duration"]),
            "size_bytes": int(probe["format"].get("size", 0)),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "has_video": any(s.get("codec_type") == "video" for s in streams),
        }

    return cache.get_or_build("probe", PROBE_VERSION, {"media_sha256": media_sha256}, {}, build)


# ---------------------------------------------------------------------------
# audio
# ---------------------------------------------------------------------------

AUDIO_VERSION = "1"
AUDIO_CONFIG = {"format": "wav", "codec": "pcm_s16le", "sample_rate": 16000, "channels": 1,
                "impl": "services.audio_extraction.extract_audio"}


def run_audio(cache: StageCache, media_path: Path, media_sha256: str) -> CacheResult:
    def build(work: Path) -> dict:
        from services.audio_extraction import extract_audio
        with Measure() as m:
            tmp_wav = Path(extract_audio(str(media_path)))
        shutil.move(str(tmp_wav), work / "audio.wav")
        return {**m.as_dict(), "size_bytes": (work / "audio.wav").stat().st_size}

    config = {**AUDIO_CONFIG, "ffmpeg_python": _package_version("ffmpeg-python")}
    return cache.get_or_build("audio", AUDIO_VERSION, {"media_sha256": media_sha256}, config, build)


# ---------------------------------------------------------------------------
# transcript (rich contract; profile + language mode are part of the key)
# ---------------------------------------------------------------------------

TRANSCRIPT_VERSION = "3"


def run_transcript(cache: StageCache, audio: CacheResult, profile_name: str, language_mode: str) -> CacheResult:
    """
    services.transcription.transcribe_rich with the given ASR profile.

    The "legacy" profile decodes exactly like the original pipeline, so
    legacy_v2 fed `legacy_segments()` reproduces historical selections.
    """
    from dataclasses import asdict
    from services import transcription

    adaptive = profile_name == "adaptive_v1"
    profile = None if adaptive else transcription.get_profile(profile_name)

    def build(work: Path) -> dict:
        # Both entry points raise on an unavailable model; nothing fake is ever cached.
        with Measure() as m:
            if adaptive:
                from services.asr_pipeline import transcribe_adaptive
                transcript = transcribe_adaptive(str(audio.path / "audio.wav"), language=language_mode)
            else:
                transcript = transcription.transcribe_rich(
                    str(audio.path / "audio.wav"), profile=profile, language_mode=language_mode)
        write_json(work / "transcript.json", transcript.to_dict())
        quality = transcript.quality
        return {
            **m.as_dict(),
            "segment_count": quality.segment_count,
            "word_count": quality.word_count,
            "language": transcript.language.language,
            "language_probability": transcript.language.probability,
            "language_uncertain": transcript.language.uncertain,
            "quality_status": quality.status,
            "hallucination_suspect_segments": quality.hallucination_suspect_segments,
            "low_confidence_segments": quality.low_confidence_segments,
            "speech_coverage": quality.speech_coverage,
            "real_time_factor": round(m.wall_s / transcript.audio_duration, 4) if transcript.audio_duration else None,
        }

    if adaptive:
        from services import asr_pipeline
        config = {"impl": "services.asr_pipeline.transcribe_adaptive",
                  "pipeline": asr_pipeline.PIPELINE_VERSION,
                  "profiles": {name: asdict(transcription.PROFILES[name])
                               for name in sorted(set(asr_pipeline.LANGUAGE_PROFILE.values()))},
                  "region_params": asr_pipeline.REGION_PARAMS,
                  "accept_params": asr_pipeline.ACCEPT_PARAMS,
                  "retry_budget_fraction": asr_pipeline.RETRY_BUDGET_FRACTION}
    else:
        config = {"impl": "services.transcription.transcribe_rich", "profile": asdict(profile)}
    config.update({"language_mode": language_mode,
                   "faster_whisper": _package_version("faster-whisper"),
                   "ctranslate2": _package_version("ctranslate2")})
    return cache.get_or_build("transcript", TRANSCRIPT_VERSION, {"audio_key": audio.key}, config, build)


def load_transcript(result: CacheResult):
    from services.transcript import Transcript
    return Transcript.from_dict(read_json(result.path / "transcript.json"))
