# ClipPods — SaaS Hackathon MVP

Automatically transform long podcasts or YouTube videos into viral, translated, high-energy clips.

## Features
- **Smart Transcription**: Powered by faster-whisper/Sarvam AI.
- **Multimodal Auto-Highlighting**: Designed for SmolVLM2 to extract semantic highlights, with audio-energy fallback.
- **Instant Extraction & Chunking**: Automatic clip cutting (FFmpeg with GPU acceleration) and sentence-boundary chunking.
- **Dubbing & Translation**: Designed to integrate SeamlessM4T v2 for end-to-end Speech-to-Speech translation, with Sarvam API as fallback.
- **YouTube Support**: Accept direct YouTube URLs using yt-dlp.
- **Modern UI**: Clean, responsive dashboard.

## Advanced Pipeline Architecture
1. **Input Acquisition**: Upload local files or paste YouTube URLs (`yt-dlp`).
2. **Preprocessing**: Zero-copy GPU processing with FFmpeg (NVDEC/NVENC) to `mp4`.
3. **Highlight Extraction**: VLM-based detection (SmolVLM2/WhisperX + LLM). 
4. **Chunking**: Sentence boundary and length alignment.
5. **Translation/Dubbing**: SeamlessM4T v2 for state-of-the-art prosody-preserving dubbed audio.
6. **Output**: Mux clip video with generated audio.


## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install static-ffmpeg
   ```

2. **Configuration**:
   Create a `.env` file in the root directory:
   ```env
   SARVAM_API_KEY=your_key_here
   ```

3. **Start the Backend**:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

4. **Start the Frontend**:
   Open `index.html` in your browser (or use a Live Server).

## Tech Stack
- **Backend**: FastAPI, Celery (Upcoming), yt-dlp, FFmpeg (CUDA HWAccel).
- **ML Services**: Sarvam STT/TTS (MVP), SmolVLM2 (Highlighting), SeamlessM4T v2 (S2ST).
- **Frontend**: Vanilla JS, CSS.
- **Storage**: Local filesystem (MVP), transitioning to S3.

## Roadmap
- [ ] Migrate completely to SmolVLM2 for semantic highlight extraction on GPU.
- [ ] Implement SeamlessM4T v2 pipeline for scalable offline S2ST.
- [ ] Docker + GPU (NVIDIA CUDA) configuration.
- [ ] Cloud storage (S3) integration.