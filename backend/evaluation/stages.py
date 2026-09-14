"""
Cached pipeline stages for evaluation.

Phase 0 stages reuse the production functions unchanged, so the cached artifacts
are exactly what the legacy pipeline would have produced:

    probe       ffprobe metadata of the source media
    audio       16 kHz mono PCM WAV via services.audio_extraction.extract_audio
    transcript  services.transcription.transcribe (legacy "base" configuration)

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
# transcript (legacy ASR configuration)
# ---------------------------------------------------------------------------

TRANSCRIPT_LEGACY_VERSION = "1"
# Mirrors services/transcription.py as of Phase 0. The legacy function takes no
# language argument, so a manifest's language_mode is NOT honoured here.
LEGACY_ASR_CONFIG = {
    "impl": "services.transcription.transcribe",
    "engine": "faster-whisper",
    "model": "base",
    "device": "cpu",
    "compute_type": "int8",
    "beam_size": 5,
    "language": None,
    "vad_filter": False,
    "word_timestamps": False,
}


def run_transcript_legacy(cache: StageCache, audio: CacheResult, audio_duration_s: float) -> CacheResult:
    def build(work: Path) -> dict:
        from services import transcription

        # The production function silently returns a stub transcript when the
        # model cannot load. Never let that be cached as a real result.
        if transcription.get_model() is None:
            raise StageError("Faster-Whisper model is unavailable; refusing to record a stub transcript.")

        with Measure() as m:
            result = transcription.transcribe(str(audio.path / "audio.wav"))
        write_json(work / "transcript.json", result)
        segments = result["segments"]
        return {
            **m.as_dict(),
            "segment_count": len(segments),
            "speech_s": round(sum(s["end"] - s["start"] for s in segments), 3),
            "real_time_factor": round(m.wall_s / audio_duration_s, 4) if audio_duration_s else None,
        }

    config = {**LEGACY_ASR_CONFIG,
              "faster_whisper": _package_version("faster-whisper"),
              "ctranslate2": _package_version("ctranslate2")}
    return cache.get_or_build("transcript_legacy", TRANSCRIPT_LEGACY_VERSION,
                              {"audio_key": audio.key}, config, build)


def load_transcript(result: CacheResult) -> dict:
    return read_json(result.path / "transcript.json")
