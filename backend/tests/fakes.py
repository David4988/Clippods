"""Test doubles shared across test modules."""
from __future__ import annotations

from services import transcript_quality
from services.transcript import SCHEMA, LanguageInfo, Transcript, TranscriptSegment


def transcript_from_segments(segments: list[dict], language: str = "en") -> Transcript:
    """A valid Transcript carrying only start/end/text, as a mocked ASR result."""
    segs = [
        TranscriptSegment(id=i, start=float(s["start"]), end=float(s["end"]), text=s.get("text", ""),
                          avg_logprob=None, compression_ratio=None, no_speech_prob=None,
                          temperature=0.0, token_count=None, words=None)
        for i, s in enumerate(segments)
    ]
    duration = max((s.end for s in segs), default=0.0)
    info = LanguageInfo(mode="auto", language=language, probability=1.0, top=[(language, 1.0)],
                        probes=[], uncertain=False, reasons=[])
    transcript_quality.flag_segments(segs, language, duration, None)
    return Transcript(
        schema=SCHEMA,
        asr={"engine": "fake", "profile": "test"},
        audio_duration=duration,
        language=info,
        segments=segs,
        speech_regions=None,
        quality=transcript_quality.summarise(segs, info, None),
        timings={},
    )
