"""Test doubles shared across test modules."""
from __future__ import annotations

from services import transcript_quality
from services.transcript import SCHEMA, LanguageInfo, SpeechRegions, Transcript, TranscriptSegment, Word


def transcript_with_words(segments: list[tuple[float, float, str]], *, language: str = "en",
                          speech: list[tuple[float, float]] | None = None,
                          duration: float | None = None, suspect: tuple[int, ...] = (),
                          with_words: bool = True) -> Transcript:
    """
    A Transcript with word timings spread evenly across each (start, end, text)
    segment, optional VAD speech regions, and the listed segment indices forced
    to be hallucination suspects (so the quality gate distrusts them).
    """
    segs = []
    for i, (start, end, text) in enumerate(segments):
        tokens = text.split()
        step = (end - start) / max(len(tokens), 1)
        words = [Word(round(start + k * step, 3), round(start + (k + 1) * step, 3), tok, 0.9)
                 for k, tok in enumerate(tokens)] if with_words else None
        segs.append(TranscriptSegment(id=i, start=start, end=end, text=text, avg_logprob=-0.2,
                                      compression_ratio=1.3, no_speech_prob=0.01, temperature=0.0,
                                      token_count=len(tokens), words=words))
    duration = duration if duration is not None else max((s.end for s in segs), default=0.0)
    regions = None if speech is None else SpeechRegions(method="test", params={}, regions=list(speech),
                                                        audio_duration=duration)
    info = LanguageInfo(mode=language, language=language, probability=None, top=[], probes=[],
                        uncertain=False, reasons=[])
    transcript_quality.flag_segments(segs, language, duration, regions)
    for i in suspect:
        segs[i].flags = sorted(set(segs[i].flags) | {"repeated_text"})
        segs[i].hallucination_suspect = True
    return Transcript(schema=SCHEMA, asr={"engine": "fake", "profile": "test"}, audio_duration=duration,
                      language=info, segments=segs, speech_regions=regions,
                      quality=transcript_quality.summarise(segs, info, regions), timings={})


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
