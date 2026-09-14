"""
Generates the transcript fixtures used by the legacy_v2 characterization tests.

The generated JSON files are committed. Goldens are pinned to those files, not to
this script, so re-running it is only needed when a new fixture is added.
Run from backend/:  python -m tests.legacy.generate_fixtures

The transcripts are synthetic but shaped like faster-whisper output: segment
lengths of a few seconds, uneven gaps, mixed terminal punctuation, and the
failure shapes the master plan calls out (Hindi danda, Tamil, silence with
hallucination-like repeats, malformed entries, a very short input).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"

EN_SENTENCES = [
    "So the real reason nobody talks about this is money.",
    "I actually think that's completely wrong",
    "Why would anyone build a company that way?",
    "Here's the thing nobody tells you about hiring.",
    "And then we lost everything in about three weeks!",
    "you know, it's kind of like",
    "That was the moment I realised the product was the problem.",
    "What would you do differently if you started today?",
    "Honestly, most advice on the internet is useless.",
    "We tried that, and it failed twice,",
]

HI_SENTENCES = [
    "असली वजह यह है कि कोई इसके बारे में बात नहीं करता।",
    "मुझे लगता है कि यह पूरी तरह गलत है",
    "आप आज शुरू करते तो क्या अलग करते?",
    "सबसे बड़ी गलती हमने पहले साल में की।",
    "तो बात यह है कि",
    "लोग सोचते हैं कि पैसा ही सब कुछ है।",
]

TA_SENTENCES = [
    "இதைப் பற்றி யாரும் பேசுவதில்லை.",
    "நான் அது முற்றிலும் தவறு என்று நினைக்கிறேன்",
    "இன்று தொடங்கினால் நீங்கள் என்ன மாற்றுவீர்கள்?",
    "அதனால தான் நாங்கள் எல்லாவற்றையும் இழந்தோம்.",
    "முதல் வருடத்தில் பெரிய தவறு செய்தோம்.",
]


def _speech(rng: random.Random, sentences: list[str], duration: float,
            seg_len=(1.8, 7.5), gap=(0.05, 1.6), start=0.4) -> list[dict]:
    segments = []
    t = start
    while True:
        length = round(rng.uniform(*seg_len), 2)
        if t + length > duration - 0.5:
            break
        segments.append({"start": round(t, 2), "end": round(t + length, 2),
                         "text": rng.choice(sentences)})
        t += length + rng.uniform(*gap)
    return segments


def build() -> dict[str, dict]:
    fixtures: dict[str, dict] = {}

    fixtures["empty_120s"] = {"video_duration": 120.0, "segments": []}

    fixtures["short_12s"] = {
        "video_duration": 12.0,
        "segments": [
            {"start": 0.3, "end": 3.9, "text": "Welcome back to the show."},
            {"start": 4.2, "end": 8.1, "text": "Today we talk about failure."},
            {"start": 8.4, "end": 11.6, "text": "Let's get into it."},
        ],
    }

    fixtures["english_podcast_10min"] = {
        "video_duration": 600.0,
        "segments": _speech(random.Random(101), EN_SENTENCES, 600.0),
    }

    fixtures["hindi_danda_5min"] = {
        "video_duration": 300.0,
        "segments": _speech(random.Random(202), HI_SENTENCES, 300.0),
    }

    fixtures["tamil_5min"] = {
        "video_duration": 300.0,
        "segments": _speech(random.Random(303), TA_SENTENCES, 300.0, seg_len=(2.5, 9.0)),
    }

    # Speech, then a long music/silence stretch where Whisper-like hallucinated
    # repeats appear, then speech again.
    rng = random.Random(404)
    music = []
    t = 125.0
    while t < 235.0:
        music.append({"start": round(t, 2), "end": round(t + 2.0, 2),
                      "text": "Thank you for watching."})
        t += rng.uniform(6.0, 14.0)
    fixtures["music_gap_hallucination_6min"] = {
        "video_duration": 360.0,
        "segments": (_speech(random.Random(405), EN_SENTENCES, 120.0)
                     + music
                     + [{**s, "start": round(s["start"] + 240.0, 2), "end": round(s["end"] + 240.0, 2)}
                        for s in _speech(random.Random(406), EN_SENTENCES, 115.0)]),
    }

    fixtures["malformed_entries_120s"] = {
        "video_duration": 120.0,
        "segments": [
            {"text": "no timing at all"},
            {"start": "not_a_number", "end": 5.0, "text": "bad type"},
            {"start": 10.0, "end": 8.0, "text": "end before start"},
            {"start": 20.0, "end": 26.0, "text": "One valid sentence here."},
        ],
    }

    fixtures["long_podcast_90min"] = {
        "video_duration": 5400.0,
        "segments": _speech(random.Random(505), EN_SENTENCES, 5400.0),
    }

    return fixtures


def main() -> None:
    FIXTURE_DIR.mkdir(exist_ok=True)
    for name, data in build().items():
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {path.name}: {len(data['segments'])} segments")


if __name__ == "__main__":
    main()
