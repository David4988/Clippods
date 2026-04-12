"""
ClipPods — Text-to-Speech Service
Uses the official Sarvam AI SDK to synthesize translated text into spoken audio.
"""

import os
import time
import base64

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import SARVAM_API_KEY


def generate_clip_audio(text: str, target_lang: str, output_path: str):
    """
    Generate audio for a translated clip using Sarvam TTS.
    Saves the output MP3 file to output_path.
    """
    if not text.strip():
        raise ValueError("Cannot synthesize empty text.")

    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_api_key_here":
        print("WARNING SARVAM_API_KEY missing - using MOCK TTS")
        # In mock mode, we just skip generating and let it fail gracefully 
        # or we could make a dummy file, but for now we expect the real key
        raise RuntimeError("Missing Sarvam API Key for TTS")

    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

    try:
        # We use bulbul:v3 for best quality. It has a 2500 character limit.
        # Ensure we don't exceed the limit
        safe_text = text[:2400]

        # Call Sarvam TTS
        print(f"INFO Synthesizing audio for {target_lang}...")
        response = client.text_to_speech.convert(
            text=safe_text,
            target_language_code=target_lang,
            model="bulbul:v3",
            speaker="shubh", # Default speaker
        )

        # The response is base64 encoded audio string
        audio_base64 = getattr(response, "audios", [None])[0] 
        if not audio_base64:
            raise RuntimeError("TTS API returned empty audio.")

        # Decode base64 to MP3 file
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(audio_base64))
            
    except Exception as e:
        print(f"WARNING TTS Generation failed: {e}")
        raise
