"""
Step 1 of the real-world ASR validation: inspect each video's structure.

    python -m evaluation.experiments.realworld_structure [--keys ta1 en1 ...]

For each <eval_dir>/realworld/audio/<key>.wav:
  * whole-file profile in 30 s windows: VAD speech ratio, speech-region count,
    overall loudness, loudness of the non-speech parts (a loud non-speech bed
    suggests music under the audio), processed in 10-minute chunks
  * base/rich_v1 transcript of the opening section (through the likely intro)
    so a human can read where the continuous conversation starts
  * chapters and SponsorBlock segments from metadata

Writes <eval_dir>/realworld/structure/<key>.json and <key>.opening.txt.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

from evaluation.storage import eval_dir, write_json

SR = 16000
WINDOW_S = 30
CHUNK_S = 600


def read_wav(path: Path, start_s: float, duration_s: float) -> np.ndarray:
    with wave.open(str(path)) as w:
        w.setpos(min(int(start_s * SR), w.getnframes()))
        frames = w.readframes(int(duration_s * SR))
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def db(x: np.ndarray) -> float | None:
    if x.size == 0:
        return None
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    return round(20 * math.log10(rms), 1) if rms > 1e-9 else -120.0


def profile(path: Path) -> list[dict]:
    from services.speech_regions import detect_speech_regions

    total = wav_seconds(path)
    rows = []
    for chunk_start in range(0, math.ceil(total), CHUNK_S):
        audio = read_wav(path, chunk_start, CHUNK_S)
        regions = detect_speech_regions(audio).regions
        mask = np.zeros(audio.size, dtype=bool)
        for s, e in regions:
            mask[int(s * SR):int(e * SR)] = True
        for w0 in range(0, math.ceil(audio.size / SR), WINDOW_S):
            a, b = w0 * SR, min(audio.size, (w0 + WINDOW_S) * SR)
            if b - a < SR:
                continue
            seg, seg_mask = audio[a:b], mask[a:b]
            n_regions = sum(1 for s, e in regions if s < w0 + WINDOW_S and e > w0)
            rows.append({
                "start": chunk_start + w0,
                "speech_ratio": round(float(seg_mask.mean()), 2),
                "regions": n_regions,
                "level_db": db(seg),
                "nonspeech_db": db(seg[~seg_mask]),
            })
    return rows


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", nargs="*")
    args = ap.parse_args(argv)

    from dataclasses import replace
    from services import transcription

    root = eval_dir() / "realworld"
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    sponsorblock = json.loads((root / "sponsorblock.json").read_text(encoding="utf-8"))
    out_dir = root / "structure"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_base = replace(transcription.PROFILES["rich_v1"], name="realworld_structure_base")

    for key, info in meta.items():
        if args.keys and key not in args.keys:
            continue
        wav = root / "audio" / f"{key}.wav"
        if not wav.exists():
            print(f"{key}: audio missing, skipped")
            continue
        rows = profile(wav)
        chapters = [(round(c["start_time"]), round(c["end_time"]), c["title"]) for c in (info["chapters"] or [])]
        sb = [(s["category"], round(s["segment"][0]), round(s["segment"][1])) for s in sponsorblock.get(key) or []]

        # Opening transcript through the likely intro (+ margin), capped.
        hints = [e for cat, s, e in sb if cat in ("preview", "intro", "sponsor", "selfpromo") and s < 600]
        intro_chapter = [e for s, e, t in chapters[:1] if s == 0 and e < 600]
        opening_end = min(480, max(hints + intro_chapter + [150]) + 150)
        windows = [(0, opening_end)]
        if key == "ta1":
            windows.append((900, 1140))  # around the owner-provided 16:44 start

        texts = []
        for start, end in windows:
            clip = out_dir / f"{key}.{start}-{end}.wav"
            with wave.open(str(clip), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((read_wav(wav, start, end - start) * 32767).astype(np.int16).tobytes())
            t = transcription.transcribe_rich(str(clip), profile=profile_base, language_mode="auto")
            clip.unlink()
            texts.append(f"### {key} {start}-{end}s  language={t.language.language} p={t.language.probability} "
                         f"probes={[(round(p.start + start), p.language) for p in t.language.probes]}")
            for s in t.segments:
                texts.append(f"[{start + s.start:7.1f}-{start + s.end:7.1f}] {s.text}")
        (out_dir / f"{key}.opening.txt").write_text("\n".join(texts), encoding="utf-8")
        write_json(out_dir / f"{key}.json", {"key": key, "duration": info["duration"], "chapters": chapters,
                                              "sponsorblock": sb, "windows": rows, "opening_windows": windows})
        print(f"{key}: profiled {len(rows)} windows; opening transcript {windows}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
