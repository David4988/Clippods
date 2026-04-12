"""
ClipPods — Transcription Service
Uses the official Sarvam AI SDK for synchronous REST transcription.
Splits audio into small chunks, gets word-level timestamps, returns proper Segments.
"""

import os
import math
import time
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import static_ffmpeg
static_ffmpeg.add_paths()

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Segment
from config import SARVAM_API_KEY

# Sarvam REST API limit: ~30 seconds of audio per call.
# We use 25-second chunks to stay safely within limits.
CHUNK_DURATION_SEC = 25
MAX_RETRIES = 3


def transcribe(audio_path: str, language_code: str = "ta-IN") -> list[Segment]:
    """
    Main entry point: transcribes audio at audio_path.
    Splits into 25-second chunks, sends each to Sarvam, merges results.
    """
    total_sec = _get_audio_duration(audio_path)
    print(f"INFO Audio duration: {total_sec:.1f}s, language: {language_code}")

    with tempfile.TemporaryDirectory() as temp_dir:
        chunks = _split_audio(audio_path, temp_dir, total_sec)
        print(f"INFO Split into {len(chunks)} chunk(s)")

        all_segments = []

        # Process chunks sequentially to avoid rate limits
        for chunk_info in chunks:
            try:
                segs = _call_sarvam(chunk_info["path"], language_code, chunk_info["offset_sec"])
                all_segments.extend(segs)
                print(f"  OK Chunk at {chunk_info['offset_sec']:.0f}s -> {len(segs)} segments")
            except Exception as e:
                print(f"  WARNING Chunk at {chunk_info['offset_sec']:.0f}s failed: {e}")
                # Fallback: create a placeholder segment so we don't lose the time range
                all_segments.append(Segment(
                    start_sec=round(chunk_info["offset_sec"], 2),
                    end_sec=round(chunk_info["offset_sec"] + chunk_info["duration_sec"], 2),
                    text="[transcription unavailable]"
                ))

        if not all_segments:
            raise RuntimeError("No transcript segments produced. Check the audio file and API key.")

        # Filter out empty-text segments
        all_segments = [s for s in all_segments if s.text.strip()]
        if not all_segments:
            raise RuntimeError("All transcript segments were empty. The audio may not contain speech.")

        print(f"INFO Total segments: {len(all_segments)}")
        return all_segments


# ---- Sarvam API Call ---- #

def _call_sarvam(file_path: str, language_code: str, offset_sec: float) -> list[Segment]:
    """
    Calls the Sarvam AI speech-to-text REST endpoint using the official SDK.
    Returns a list of Segments with timestamps adjusted by offset_sec.
    """
    # Mock mode when no API key
    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_api_key_here":
        print("WARNING SARVAM_API_KEY missing — using MOCK transcription")
        time.sleep(0.5)
        # Return multiple small segments for realistic chunking
        dur = _get_audio_duration(file_path)
        seg_len = 10  # 10-second mock segments
        segs = []
        t = 0.0
        mock_texts = [
            "Welcome to the SaaS Hackathon podcast.",
            "Today we are building incredible AI agents.",
            "Our product helps you find the best clips automatically.",
            "This is a high energy segment to test our highlighting algorithm.",
            "Thank you for listening, hope you enjoy the demo.",
            "We are working on cutting-edge technology.",
            "This segment has important information to share.",
            "The future of podcasting is AI-powered.",
        ]
        idx = 0
        while t < dur:
            end = min(t + seg_len, dur)
            segs.append(Segment(
                start_sec=round(offset_sec + t, 2),
                end_sec=round(offset_sec + end, 2),
                text=mock_texts[idx % len(mock_texts)]
            ))
            t = end
            idx += 1
        return segs

    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

    for attempt in range(MAX_RETRIES):
        try:
            with open(file_path, "rb") as f:
                response = client.speech_to_text.transcribe(
                    file=f,
                    model="saarika:v2.5",
                    language_code=language_code,
                )

            # Try to use word-level timestamps for precise segments
            timestamps = getattr(response, "timestamps", None)
            transcript = getattr(response, "transcript", "") or ""

            if timestamps and hasattr(timestamps, "words") and timestamps.words:
                return _parse_word_timestamps(timestamps, offset_sec)

            # Fallback: return the full transcript as a single segment
            if transcript.strip():
                chunk_dur = _get_audio_duration(file_path)
                # Split long transcripts into sentence-level segments
                return _split_transcript_into_segments(
                    transcript.strip(), offset_sec, chunk_dur
                )

            return []

        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Sarvam API failed after {MAX_RETRIES} attempts: {e}")
            wait = 3 * (attempt + 1)
            print(f"WAIT Sarvam attempt {attempt + 1} failed, retrying in {wait}s: {e}")
            time.sleep(wait)

    return []


def _parse_word_timestamps(timestamps, offset_sec: float) -> list[Segment]:
    """
    Convert word-level timestamps into sentence-level Segments (~10s each).
    Groups words together until we hit punctuation or ~10 seconds.
    """
    words = timestamps.words
    starts = timestamps.start_time_seconds
    ends = timestamps.end_time_seconds

    if not words:
        return []

    segments = []
    current_words = []
    seg_start = starts[0]

    for i, (word, s, e) in enumerate(zip(words, starts, ends)):
        current_words.append(word)
        elapsed = e - seg_start

        # Break on sentence-ending punctuation or ~10 second boundary
        is_sentence_end = word.rstrip().endswith(('.', '?', '!', '।', '。'))
        is_long = elapsed >= 10.0
        is_last = i == len(words) - 1

        if is_sentence_end or is_long or is_last:
            text = " ".join(current_words).strip()
            if text:
                segments.append(Segment(
                    start_sec=round(offset_sec + seg_start, 2),
                    end_sec=round(offset_sec + e, 2),
                    text=text
                ))
            current_words = []
            if i + 1 < len(starts):
                seg_start = starts[i + 1]

    return segments


def _split_transcript_into_segments(
    transcript: str, offset_sec: float, chunk_dur: float
) -> list[Segment]:
    """
    Split a flat transcript string into multiple smaller segments
    by distributing evenly over the chunk_dur.
    """
    # Split by sentence-ending punctuation
    import re
    sentences = re.split(r'(?<=[.?!।。])\s+', transcript)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [Segment(start_sec=round(offset_sec, 2),
                        end_sec=round(offset_sec + chunk_dur, 2),
                        text=transcript)]

    # Distribute time evenly across sentences
    time_per_sentence = chunk_dur / len(sentences)
    segments = []
    for i, sent in enumerate(sentences):
        s = offset_sec + i * time_per_sentence
        e = offset_sec + (i + 1) * time_per_sentence
        segments.append(Segment(
            start_sec=round(s, 2),
            end_sec=round(e, 2),
            text=sent
        ))

    return segments


# ---- Audio Helpers ---- #

def _get_audio_duration(path: str) -> float:
    import shutil
    ffprobe_path = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffprobe_path:
        raise RuntimeError("ffprobe not found in PATH. Ensure static_ffmpeg is installed.")
    res = subprocess.run([
        ffprobe_path, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def _split_audio(path: str, temp_dir: str, total_sec: float) -> list[dict]:
    """Split audio into CHUNK_DURATION_SEC-sized WAV chunks for the API."""
    num_chunks = max(1, math.ceil(total_sec / CHUNK_DURATION_SEC))
    chunks = []

    for i in range(num_chunks):
        start = i * CHUNK_DURATION_SEC
        actual_duration = min(CHUNK_DURATION_SEC, total_sec - start)
        if actual_duration <= 0:
            break
        out = os.path.join(temp_dir, f"chunk_{i:03d}.wav")

        import shutil
        ffmpeg_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg not found in PATH. Ensure static_ffmpeg is installed.")
        subprocess.run([
            ffmpeg_path, "-y",
            "-ss", str(start),
            "-t", str(CHUNK_DURATION_SEC),
            "-i", path,
            "-ar", "16000",
            "-ac", "1",
            "-vn",  # Strip video track (important for MP4 input)
            out
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)

        chunks.append({
            "path": out,
            "offset_sec": start,
            "duration_sec": actual_duration,
        })

    return chunks