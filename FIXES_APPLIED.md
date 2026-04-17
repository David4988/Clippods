Fixes applied to resolve 502 transcription error:

1. Fixed Sarvam model value in services/transcription.py:
   - Changed "model": "saarika:v2.5" to "model": "saarika"

2. Added required audio codec field in services/transcription.py:
   - Added "input_audio_codec": "pcm_s16le" to API request data

3. Limited audio duration in services/audio_extraction.py:
   - Added t=30 parameter to FFmpeg output to cap audio at 30 seconds

All changes are minimal and focused only on resolving the transcription API 502 error.
Pipeline structure remains unchanged per clippods_contracts.md requirements.