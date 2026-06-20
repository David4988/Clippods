# ClipPods — MVP Contract & Data Contracts (LOCKED)

---

## Overview

| Field           | Value                                            |
| --------------- | ------------------------------------------------ |
| Project         | ClipPods                                         |
| Product type    | Micro SaaS — Highlight Clipper                   |
| Goal            | Video → auto highlight clips                     |
| Stack           | Python, FastAPI, ffmpeg, yt-dlp, Faster-Whisper (local) |
| Win condition   | `POST /process` returns 3 usable clips           |
| Processing type | Fully synchronous                                |
| Storage         | Local only                                       |

---

## MVP Contract

### Input

| Field              | Value                        |
| ------------------ | ---------------------------- |
| Accepted params    | `video_url` OR `file`        |
| Rule               | Exactly ONE must be provided |
| Max video duration | 10–120 minutes               |

Invalid:

* both inputs → reject
* no input → reject

---

## Output

```json
{
  "clips": ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]
}
```

---

## Clip Constraints

* EXACTLY 3 clips
* Base duration = 20 seconds
* Allowed extension up to ~25 seconds
* Clips must contain speech
* Clips must be playable (no corruption)

---

## Processing Pipeline (LOCKED)

```
video_url OR file
    ↓
get_video_input()
    ↓
extract_audio()
    ↓
transcribe()  [Faster-Whisper]
    ↓
select_segments()
    ↓
generate_clips()
    ↓
return clips
```

No:

* user selection
* multi-step API
* async processing

---

## Selection Rules

* Ignore segments with NO speech
* Ignore intro (~first 5 seconds)
* Prioritize speech density
* Avoid overlapping clips
* Always produce exactly 3 segments (fallback if needed)

---

## Clipping Rules

FFmpeg MUST:

* use accurate cutting (seek AFTER input)
* use re-encoding:

```bash
libx264 + aac
```

---

## UX Rules (MANDATORY)

To avoid abrupt cuts:

* Audio fade:

  * fade-in: 1–1.5 sec
  * fade-out: 2–2.5 sec

* Video fade:

  * same timing as audio
  * must be synchronized

---

## Failure Handling

Only allowed:

| Condition      | Response                                |
| -------------- | --------------------------------------- |
| Invalid input  | `{ "error": "Invalid input" }`          |
| ASR failure    | `{ "error": "Audio not clear enough" }` |
| Video too long | `{ "error": "Video too long" }`         |

No new error types allowed.

---

## Non-Goals (Strictly Forbidden)

* No LLM usage
* No external APIs
* No queues / Redis
* No async workers
* No scaling logic
* No optimization for production
* No feature expansion

---

## Data Contracts

### API

```json
POST /process
```

Request:

```json
{
  "video_url": "string"
}
```

OR multipart:

```
file: video
```

Response:

```json
{
  "clips": ["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]
}
```

---

### extract_audio

```python
extract_audio(video_path: str) -> str
```

Output:

```
audio.wav
```

---

### transcribe

```python
transcribe(audio_path: str) -> dict
```

Output:

```json
{
  "segments": [
    { "start": float, "end": float, "text": "string" }
  ]
}
```

---

### select_segments

```python
select_segments(segments: list, video_duration: float) -> list
```

Output:

```json
[
  { "start": float, "end": float },
  { "start": float, "end": float },
  { "start": float, "end": float }
]
```

Rules:

* must return exactly 3 segments
* must include speech
* must respect duration constraints

---

### generate_clips

```python
generate_clips(video_path: str, segments: list) -> list
```

Output:

```json
["clip_0.mp4", "clip_1.mp4", "clip_2.mp4"]
```

---

## Implementation Rules

| Rule       | Value                |
| ---------- | -------------------- |
| ASR        | Faster-Whisper (local only) |
| Processing | synchronous only     |
| Storage    | local only           |
| Clip count | always 3             |
| Async      | forbidden            |
| DB         | none                 |
| Queues     | none                 |
| Logging    | minimal only         |

---

## Success Condition

A valid system:

Input (URL/file)
→ system runs
→ returns 3 clips
→ clips contain speech
→ clips feel natural (no abrupt cuts)
→ no crash

Nothing else matters.
