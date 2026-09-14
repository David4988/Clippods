"""
Listening sheet for the prev-text comparison: 30 s audio clips at sections where
the configs disagree, with each config's transcript and signal-level evidence.

    python -m evaluation.experiments.realworld_listening_sheet

Writes <eval_dir>/realworld/compare_prevtext/listen/<key>_<mm-ss>.wav and
listening_sheet.md. For each section: VAD speech seconds in the clip, and per
config the words inside the section, how many fall inside measured speech, and
which segments are flagged.
"""
from __future__ import annotations

import json
import sys

from evaluation.experiments.realworld_asr import cut
from evaluation.storage import eval_dir

CONFIGS = ("base_rich_v1", "large_v3_fix", "large_v3_prevtext_off")
SECTIONS = [  # (key, absolute start seconds, why)
    ("ta1", 2007, "large_v3_fix skips 33:27→33:55; prevtext_off has continuous text"),
    ("ta1", 2190, "late part of window: prevtext_off 'missing speech' flag near window end"),
    ("ta2", 2245, "prevtext_off gap 37:25→37:53; is speech really missing?"),
    ("ta2", 2380, "large_v3_fix 'ஐயா ஐயா' loop from 39:40; prevtext_off region"),
    ("hi1", 5263, "prevtext_off correct English lines 87:43–88:10"),
    ("hi1", 5292, "prevtext_off Devanagari nonsense + 'सब्सक्राइब' burst 88:12–88:38"),
    ("hi2", 2556, "fix: mixed script; prevtext_off: English written in Devanagari, gap 42:42→43:06"),
    ("hi2", 2602, "prevtext_off gap 43:22→43:52"),
]
SECTION_S = 30.0


def load(config: str, key: str) -> tuple[dict, float] | None:
    root = eval_dir() / "realworld" / "compare_prevtext" / config
    for name in (f"{key}.body_middle.r1.transcript.json", f"{key}.body_middle.transcript.json"):
        path = root / name
        if path.exists():
            meta = json.loads(path.with_name(name.replace(".transcript.json", ".json")).read_text(encoding="utf-8"))
            return json.loads(path.read_text(encoding="utf-8")), meta["start"]
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = eval_dir() / "realworld"
    listen = root / "compare_prevtext" / "listen"
    listen.mkdir(parents=True, exist_ok=True)
    lines = ["# Listening sheet: large-v3 previous-text ON vs OFF", "",
             "Each clip is 30 s from the podcast body. Listen, then compare with the transcripts below.",
             "`speech` = seconds of VAD-measured speech in the clip. Per config: words in the section, how many sit",
             "inside measured speech, and flags on the overlapping segments.", ""]
    for key, abs_start, why in SECTIONS:
        clip = listen / f"{key}_{int(abs_start // 60):02d}-{int(abs_start % 60):02d}.wav"
        cut(root / "audio" / f"{key}.wav", abs_start, SECTION_S, clip)
        lines += [f"## {key} {int(abs_start // 60)}:{int(abs_start % 60):02d}–{int((abs_start + SECTION_S) // 60)}:"
                  f"{int((abs_start + SECTION_S) % 60):02d}  (`{clip.name}`)", "", f"Why: {why}", ""]
        speech_noted = False
        for config in CONFIGS:
            loaded = load(config, key)
            if loaded is None:
                continue
            transcript, window_start = loaded
            s0, s1 = abs_start - window_start, abs_start - window_start + SECTION_S
            if not speech_noted and transcript.get("speech_regions"):
                speech = sum(max(0.0, min(e, s1) - max(s, s0)) for s, e in transcript["speech_regions"]["regions"])
                lines += [f"speech: {speech:.1f} s of {SECTION_S:.0f} s", ""]
                speech_noted = True
            words = [w for seg in transcript["segments"] for w in (seg["words"] or [])
                     if s0 <= (w["start"] + w["end"]) / 2 < s1]
            segs = [seg for seg in transcript["segments"] if seg["end"] > s0 and seg["start"] < s1]
            flags = sorted({f for seg in segs for f in seg["flags"]})
            text = " ".join(seg["text"] for seg in segs)
            lines += [f"**{config}** — {len(words)} words, {sum(1 for w in words if w['in_speech'])} in speech, "
                      f"flags: {', '.join(flags) or 'none'}", "", f"> {text[:600]}", ""]
    (listen / "listening_sheet.md").write_text("\n".join(lines), encoding="utf-8")
    print(listen / "listening_sheet.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
