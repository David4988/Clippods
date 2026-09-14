"""
Fetch audio for the real-world ASR validation videos (product-owner selection).

    python -m evaluation.experiments.realworld_fetch

Downloads the best audio-only stream with yt-dlp and converts it to 16 kHz mono
PCM WAV in <eval_dir>/realworld/audio/<key>.wav. Media stays outside git.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evaluation.storage import eval_dir

VIDEOS = {
    "ta1": ("-9j_l9TaLCI", "ta"), "ta2": ("gWEQYyScQ5E", "ta"), "ta3": ("05vaB0DUMm0", "ta"),
    "en1": ("SJKr7BPOXY0", "en"), "en2": ("7ARBJQn6QkM", "en"), "en3": ("4Vz6L8B73i4", "en"),
    "hi1": ("9g_O05YEKQs", "hi"), "hi2": ("71xri_SCszU", "hi"), "hi3": ("XwawXRaNfzM", "hi"),
}


def main() -> int:
    import yt_dlp

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = eval_dir() / "realworld" / "audio"
    out.mkdir(parents=True, exist_ok=True)
    for key, (video_id, _) in VIDEOS.items():
        wav = out / f"{key}.wav"
        if wav.exists():
            print(f"{key}: exists")
            continue
        opts = {"format": "bestaudio", "outtmpl": str(out / f"{key}.src.%(ext)s"), "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            src = Path(ydl.prepare_filename(info))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
        src_info = {"format": info.get("format"), "abr": info.get("abr"), "acodec": info.get("acodec"),
                    "source_bytes": src.stat().st_size}
        src.unlink()
        (out / f"{key}.source.json").write_text(json.dumps(src_info), encoding="utf-8")
        print(f"{key}: {wav.stat().st_size / 2**20:.0f} MB wav from {src_info}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
