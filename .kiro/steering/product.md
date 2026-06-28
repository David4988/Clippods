# ClipPods — Product Overview

**Type:** Micro SaaS — Video Highlight Clipper

**Goal:** Automatically extract 3 viral-ready highlight clips from long-form video content (podcasts, interviews, talks).

**Core Value Proposition:** Turn long videos into viral clips without manual editing. Users provide a video URL or file upload, and the system returns exactly 3 short clips (20-25 seconds each) optimized for social media platforms.

## Key Features

- **Automatic highlight detection** — Uses speech transcription and density analysis to identify the most engaging segments
- **Smart clip selection** — Prioritizes high speech density, avoids intro/outro, prevents overlapping clips
- **Natural clip boundaries** — Extends clips to sentence endings when possible, avoiding abrupt cuts
- **Professional polish** — Auto-applies audio/video fade-in/out for smooth viewing experience
- **Viral scoring** — Each clip receives a "viral score" (75-98%) based on speech density and content quality
- **Dual input modes** — Accepts both video URLs (via yt-dlp) and direct file uploads

## User Flow

1. User submits video URL or uploads file
2. System downloads/processes video (max 2 hours)
3. Audio extraction → Transcription → Segment selection → Clip generation
4. User receives exactly 3 ready-to-post clips with metadata (filename, score, title, duration)

## Product Constraints

- **Strictly synchronous processing** — No async workers, queues, or multi-step APIs
- **Local processing only** — No external APIs except for video download
- **Exactly 3 clips always** — Fallback logic ensures consistent output
- **No LLM usage** — Pure algorithmic approach using FFmpeg, Whisper, and heuristics
- **Maximum video duration:** 2 hours
