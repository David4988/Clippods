import os
import math
import time
import random
import tempfile
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Segment
from config import CHUNK_DURATION_MIN

CHUNK_DURATION_SEC = CHUNK_DURATION_MIN * 60
MAX_RETRIES = 3


def transcribe(audio_path: str) -> list[Segment]:
    total_sec = _get_audio_duration(audio_path)

    if total_sec <= CHUNK_DURATION_SEC:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            subprocess.run([
                "ffmpeg", "-y", "-i", audio_path,
                "-ar", "16000", "-ac", "1", tmp_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)

            raw_segments = _call_sarvam(tmp_path)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        segments = _parse_segments(raw_segments, offset=0.0)

        if not segments:
            raise RuntimeError(f"No segments for {audio_path}")

        return segments

    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            chunks = _split_audio(audio_path, temp_dir)

            def process_chunk(chunk_info):
                try:
                    raw = _call_sarvam(chunk_info["path"])
                    return chunk_info["offset_sec"], _parse_segments(raw, chunk_info["offset_sec"])
                except Exception:
                    # fail-safe: skip chunk instead of killing full job
                    return chunk_info["offset_sec"], []

            results = []

            max_workers = min(2, len(chunks))  # 🔥 capped to match backend semaphore

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(process_chunk, c) for c in chunks]

                for future in as_completed(futures):
                    results.append(future.result())

            results.sort(key=lambda x: x[0])

            all_segments = []
            for _, segs in results:
                all_segments.extend(segs)

            if not all_segments:
                raise RuntimeError(f"No segments for {audio_path}")

            return all_segments


# ---------------- SARVAM ---------------- #

def _call_sarvam(file_path: str) -> list:
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": os.getenv("SARVAM_API_KEY")}

    # 🔴 RETRY ONLY FOR JOB CREATION
    for attempt in range(MAX_RETRIES):
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    url,
                    headers=headers,
                    files={"file": f},
                    data={"language_code": "ta-IN", "model": "saaras:v3"},
                    timeout=(5, 30)
                )
                response.raise_for_status()

            job_id = response.json().get("job_id")
            if not job_id:
                raise RuntimeError("Missing job_id")

            break

        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Job submission failed: {e}")
            time.sleep(5 * (attempt + 1))

    # 🔴 POLLING (NO RETRY LOOP HERE)
    status_url = f"{url}/{job_id}"
    start_poll = time.time()

    while True:
        if (time.time() - start_poll) > 1800:
            raise RuntimeError(f"Timeout for job {job_id}")

        time.sleep(20 + random.uniform(0, 5))

        res = requests.get(status_url, headers=headers, timeout=(5, 30))
        res.raise_for_status()

        data = res.json()
        status = data.get("status", "").lower()

        if status == "completed":
            break
        if status in ["failed", "error"]:
            raise RuntimeError(f"Job failed: {data}")

    # 🔴 SAFE PARSING
    if "error" in data:
        raise RuntimeError(f"Sarvam error: {data['error']}")

    segments = data.get("segments")
    if segments is None:
        raise RuntimeError(f"Missing segments: {data.keys()}")

    if segments:
        first = segments[0]
        if not ("start_time_seconds" in first or "start" in first):
            raise RuntimeError("Missing timestamps")

    return segments


# ---------------- HELPERS ---------------- #

def _parse_segments(raw, offset):
    return [
        Segment(
            start_sec=round(seg.get("start_time_seconds", seg.get("start")) + offset, 2),
            end_sec=round(seg.get("end_time_seconds", seg.get("end")) + offset, 2),
            text=seg["text"].strip()
        )
        for seg in raw if seg["text"].strip()
    ]


def _get_audio_duration(path):
    res = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], capture_output=True, text=True, check=True)

    return float(res.stdout.strip())


def _split_audio(path, temp_dir):
    total_sec = _get_audio_duration(path)
    num_chunks = math.ceil(total_sec / CHUNK_DURATION_SEC)

    chunks = []

    for i in range(num_chunks):
        start = i * CHUNK_DURATION_SEC
        out = os.path.join(temp_dir, f"chunk_{i}.wav")

        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(CHUNK_DURATION_SEC),
            "-i", path,
            "-ar", "16000",
            "-ac", "1",
            out
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)

        chunks.append({
            "path": out,
            "offset_sec": start
        })

    return chunks