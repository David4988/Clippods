"""
services/audio_features.py — loudness envelope from the canonical 16 kHz mono WAV.

A 100 ms RMS envelope in dB, read in chunks so a 2-hour file never sits in memory
as floats. Used for the energy features of boundary_v1, z-scored within each
video so a quiet speaker isn't compared against a loud one in absolute terms.
Computed while the WAV still exists (pipeline: before temp cleanup; evaluation:
the cached audio.wav). No new dependency: `wave` + numpy.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

FRAME_S = 0.1
FLOOR_DB = -80.0
_CHUNK_FRAMES = 600          # 60 s of envelope frames per read


@dataclass
class LoudnessEnvelope:
    frame_s: float
    db: np.ndarray           # one value per frame

    def frames(self, start: float, end: float) -> slice:
        return slice(max(0, int(start / self.frame_s)), max(0, int(np.ceil(end / self.frame_s))))

    def speech_mask(self, regions: list[tuple[float, float]]) -> np.ndarray:
        """True for frames whose centre lies inside a speech region (computed once per video)."""
        mask = np.zeros(len(self.db), dtype=bool)
        for r_start, r_end in regions:
            mask[self.frames(r_start, r_end)] = True
        return mask

    def values(self, start: float, end: float, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """Envelope values in [start, end]; only speech frames when a mask is given (if any)."""
        idx = self.frames(start, end)
        vals = self.db[idx]
        if mask is None or not len(vals):
            return vals
        selected = vals[mask[idx][:len(vals)]]
        return selected if len(selected) else vals


def loudness_envelope(wav_path: str | Path) -> Optional[LoudnessEnvelope]:
    """RMS envelope in dB, or None when the file is missing or not 16-bit mono PCM."""
    path = Path(wav_path)
    if not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                return None
            hop = int(round(w.getframerate() * FRAME_S))
            out = []
            while True:
                raw = w.readframes(hop * _CHUNK_FRAMES)
                if not raw:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                n = len(samples) // hop
                if n == 0:
                    break
                frames = samples[:n * hop].reshape(n, hop)
                rms = np.sqrt(np.mean(frames * frames, axis=1))
                out.append(np.maximum(20 * np.log10(np.maximum(rms, 1e-9)), FLOOR_DB))
    except (wave.Error, EOFError):
        return None
    return LoudnessEnvelope(frame_s=FRAME_S, db=np.concatenate(out) if out else np.zeros(0))
