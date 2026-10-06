"""
services/transcript.py — the typed transcript contract.

A Transcript is the canonical, source-language result of ASR. It keeps what
faster-whisper reports (language, probabilities, per-segment confidence fields,
word timings) plus what ClipPods measures around it (speech regions, quality
flags), so later stages can make informed decisions instead of trusting raw
text.

Timing semantics (important for later stages):
  * segment start/end  — decoder predictions; can run into silence or past the
                          end of the audio (EV-0.1). Never cut on them directly.
  * word start/end     — approximate text↔time mapping from cross-attention
                          alignment. Not acoustic ground truth.
  * speech regions     — measured by Silero VAD on the audio itself; the only
                          acoustic evidence of where speech is.

Confidence scope (measured, EV-2.2): faster-whisper computes avg_logprob,
compression_ratio, no_speech_prob and temperature once per ~30 s decoding
window and copies them onto every segment produced from that window. They are
window-level evidence; per-word `probability` is the fine-grained signal.

Not stored: decoder token ids (no downstream use; `token_count` is kept) and
`seek` offsets (internal to the decoder loop).

The legacy_v2 selector consumes `legacy_segments()`, which is exactly the
`{"start", "end", "text"}` list the pipeline has always produced.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA = "clippods-transcript/1"
SUPPORTED_LANGUAGES = ("en", "hi", "ta")
LANGUAGE_MODES = ("auto",) + SUPPORTED_LANGUAGES
# What a user can select for the adaptive pipeline: "mixed" means code-switched
# speech (e.g. Hinglish/Tanglish) decoded with the conservative mixed profile.
LANGUAGE_SELECTIONS = LANGUAGE_MODES + ("mixed",)


@dataclass
class Word:
    start: float
    end: float
    text: str
    probability: Optional[float]
    in_speech: Optional[bool] = None       # word midpoint inside a VAD speech region


@dataclass
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    avg_logprob: Optional[float]           # decode-window level (see module docstring)
    compression_ratio: Optional[float]     # decode-window level
    no_speech_prob: Optional[float]        # decode-window level
    temperature: Optional[float]           # decode-window level
    token_count: Optional[int]
    words: Optional[list[Word]]            # None when word timestamps were not requested
    speech_overlap: Optional[float] = None # fraction of [start, end] inside speech regions
    scripts: dict[str, float] = field(default_factory=dict)  # letter share per script
    flags: list[str] = field(default_factory=list)
    hallucination_suspect: bool = False    # the TEXT may not have been spoken
    timing_suspect: bool = False           # the text may be real but its start/end are not trustworthy
    low_confidence: bool = False
    attempt: int = 1                       # which AsrAttempt produced this text (Transcript.attempts)

    @property
    def usable(self) -> bool:
        """Text is safe to use as candidate content downstream (timing checked separately)."""
        return bool(self.text) and not self.hallucination_suspect


@dataclass
class SpeechRegions:
    method: str                            # e.g. "silero-vad (faster-whisper 1.2.1)"
    params: dict[str, Any]
    regions: list[tuple[float, float]]     # seconds, sorted, non-overlapping
    audio_duration: float

    @property
    def speech_seconds(self) -> float:
        return round(sum(end - start for start, end in self.regions), 3)


@dataclass
class LanguageProbe:
    start: float
    end: float
    language: str
    probability: float


@dataclass
class LanguageInfo:
    mode: str                              # auto | en | hi | ta
    language: str                          # language the decoder used
    probability: Optional[float]           # None when forced
    top: list[tuple[str, float]]           # top candidates from detection (auto only)
    probes: list[LanguageProbe]            # detection on windows spread across the speech
    uncertain: bool
    reasons: list[str]


@dataclass
class TranscriptQuality:
    status: str                            # ok | degraded  (failures raise, never a status)
    reasons: list[str]
    thresholds: dict[str, float]
    segment_count: int
    word_count: int
    flag_counts: dict[str, int]
    hallucination_suspect_segments: int
    timing_suspect_segments: int
    low_confidence_segments: int
    speech_seconds: Optional[float]
    transcribed_speech_seconds: Optional[float]   # speech covered by usable segments
    speech_coverage: Optional[float]
    text_outside_speech_seconds: Optional[float]  # word spans when available, else segment spans
    mixed_script_segments: int


@dataclass
class SuspiciousSpan:
    """A stretch of the transcript the quality gate does not trust."""
    start: float
    end: float
    reasons: list[str]
    segment_ids: list[int]                 # ids at the time the gate ran


@dataclass
class AsrAttempt:
    """
    One decode that contributed to a transcript. `segment.attempt` points here,
    so "which model/config produced this text, and why was it retried" is
    answered by Transcript.attempts[segment.attempt - 1].
    """
    attempt: int
    scope: str                             # full | region
    model: str
    profile: str
    condition_on_previous_text: bool
    language: str                          # language passed to the decoder
    region: Optional[tuple[float, float]]  # region attempts only (seconds, whole-file time)
    retry_reasons: list[str]               # why the region was retried (region attempts only)
    trigger_spans: list[SuspiciousSpan]    # gate spans that produced this region
    quality_status: str                    # full: gate status; region: resolved | still_suspicious
    outcome: Optional[str]                 # region: accepted | rejected; full: None
    segment_count: int                     # segments this attempt decoded
    decode_s: float
    metrics: dict[str, Any] = field(default_factory=dict)
    replaced: list[dict[str, Any]] = field(default_factory=list)  # attempt-1 text an accepted region replaced


@dataclass
class Transcript:
    schema: str
    asr: dict[str, Any]                    # profile, model, decode options, library versions
    audio_duration: float
    language: LanguageInfo
    segments: list[TranscriptSegment]
    speech_regions: Optional[SpeechRegions]
    quality: TranscriptQuality
    timings: dict[str, float]
    # Adaptive pipeline only (empty for single-decode profiles).
    attempts: list[AsrAttempt] = field(default_factory=list)
    suspicious_spans: list[SuspiciousSpan] = field(default_factory=list)  # final gate result

    # -- views -------------------------------------------------------------

    def legacy_segments(self) -> list[dict]:
        """The pre-contract `{"start", "end", "text"}` list consumed by legacy_v2."""
        return [{"start": s.start, "end": s.end, "text": s.text} for s in self.segments]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> dict:
        """Compact ASR record for analysis.json (the full transcript is stored separately)."""
        return {
            "schema": self.schema,
            "asr": self.asr,
            "audio_duration": self.audio_duration,
            "language": asdict(self.language),
            "quality": asdict(self.quality),
            "attempts": [
                {k: v for k, v in asdict(a).items() if k not in ("replaced", "trigger_spans")}
                for a in self.attempts
            ],
            "suspicious_spans": [asdict(span) for span in self.suspicious_spans],
            "speech_regions": None if self.speech_regions is None else {
                "method": self.speech_regions.method,
                "params": self.speech_regions.params,
                "count": len(self.speech_regions.regions),
                "speech_seconds": self.speech_regions.speech_seconds,
            },
            "timings": self.timings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transcript":
        if data.get("schema") != SCHEMA:
            raise ValueError(f"unsupported transcript schema {data.get('schema')!r}")
        lang = data["language"]
        regions = data.get("speech_regions")
        return cls(
            schema=data["schema"],
            asr=data["asr"],
            audio_duration=data["audio_duration"],
            language=LanguageInfo(
                mode=lang["mode"], language=lang["language"], probability=lang["probability"],
                top=[tuple(t) for t in lang["top"]],
                probes=[LanguageProbe(**p) for p in lang["probes"]],
                uncertain=lang["uncertain"], reasons=list(lang["reasons"]),
            ),
            segments=[
                TranscriptSegment(**{**s, "words": None if s["words"] is None else [Word(**w) for w in s["words"]]})
                for s in data["segments"]
            ],
            speech_regions=None if regions is None else SpeechRegions(
                method=regions["method"], params=regions["params"],
                regions=[tuple(r) for r in regions["regions"]], audio_duration=regions["audio_duration"],
            ),
            quality=TranscriptQuality(**data["quality"]),
            timings=data["timings"],
            attempts=[_attempt_from(a) for a in data.get("attempts", [])],
            suspicious_spans=[SuspiciousSpan(**span) for span in data.get("suspicious_spans", [])],
        )


def _attempt_from(data: dict) -> AsrAttempt:
    return AsrAttempt(**{
        **data,
        "region": None if data["region"] is None else tuple(data["region"]),
        "trigger_spans": [SuspiciousSpan(**span) for span in data["trigger_spans"]],
    })
