"""
ClipPods — Translation Service
Uses Sarvam AI translate API to convert text between Indian regional languages.

Fixed: proper API endpoint, batch handling, robust error handling.
"""

import os
import time
import requests

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models import Segment
from config import SARVAM_API_KEY


def translate_segments(segments: list[Segment], source_lang: str, target_lang: str) -> list[Segment]:
    """Translate all segment texts from source_lang to target_lang."""
    if not target_lang or source_lang == target_lang:
        return segments

    if not segments:
        return segments

    print(f"INFO Translating {len(segments)} segments: {source_lang} -> {target_lang}")

    # Mock mode
    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_api_key_here":
        print("WARNING SARVAM_API_KEY missing — using MOCK translation")
        for seg in segments:
            seg.text = f"[{target_lang}] {seg.text}"
        return segments

    translated = []
    for seg in segments:
        try:
            translated_text = _translate_text(seg.text, source_lang, target_lang)
            translated.append(Segment(
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                text=translated_text
            ))
        except Exception as e:
            print(f"WARNING Translation failed for segment at {seg.start_sec}s: {e}")
            translated.append(seg)  # Keep original on failure

    return translated


def _translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate a single text string using Sarvam AI translate endpoint."""
    if not text.strip():
        return text

    url = "https://api.sarvam.ai/translate"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "speaker_gender": "Male",
        "mode": "formal",
        "model": "mayura:v1",
        "enable_preprocessing": True
    }

    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("translated_text", text)
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Translation API failed: {e}")
            time.sleep(2 * (attempt + 1))

    return text
