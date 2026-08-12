# ClipPods — Production Contract v2

> **Status**: Active — reflects the current production implementation  
> **Supersedes**: `clippods_contracts.md` (original MVP contract)  
> **Last Updated**: 2026-07-14

---

## 1. Overview

### Product Purpose

ClipPods is a **video highlight clipper** — a Micro SaaS product that automatically extracts the most speech-dense, engaging segments from a video and produces short, polished MP4 clips ready for social media distribution.

### System Goals

| Goal | Description |
|---|---|
| **Automated highlight extraction** | Given a video URL or file upload, produce 3 high-quality highlight clips without human intervention |
| **Production reliability** | Handle concurrent users, long-running jobs, and infrastructure failures gracefully |
| **Observability** | Provide full instrumentation of the selection algorithm for developer debugging and heuristic tuning |
| **Resource safety** | Enforce upload limits, process timeouts, disk cleanup, and bounded concurrency to protect the host |

### Production Objectives

- Process videos up to **2 hours** in duration
- Support **concurrent job processing** with bounded worker threads
- Provide **real-time progress tracking** and **job cancellation**
- Clean up temporary files and expired outputs automatically
- Serve generated clips via direct download URLs

### Scope

| In Scope | Out of Scope |
|---|---|
| URL download (YouTube, direct links) | Multi-cloud distribution |
| File upload (MP4, MOV, MKV, WebM) | User authentication / accounts |
| Local ASR via Faster-Whisper | LLM-based content analysis |
| Heuristic speech-density scoring | ML/AI ranking models |
| FFmpeg-based clip generation | GPU acceleration |
| Algorithm Debugger dashboard | Database persistence |

### Technology Stack

| Component | Technology |
|---|---|
| Backend framework | Python 3.12+, FastAPI |
| ASR engine | Faster-Whisper (base model, CPU, int8) |
| Video processing | FFmpeg (libx264 + AAC) via `ffmpeg-python` |
| Video download | yt-dlp |
| Dashboard | React 19, Vite 8, Chart.js |
| Deployment | Render (VPS), Vercel (serverless fallback) |

---

## 2. Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                              │
│                                                                     │
│   ┌───────────────┐    ┌───────────────────┐    ┌───────────────┐  │
│   │  Web Client   │    │ Algorithm Debugger │    │  API Consumer │  │
│   │  (static UI)  │    │  (React Dashboard) │    │  (curl/SDK)   │  │
│   └──────┬────────┘    └────────┬──────────┘    └──────┬────────┘  │
└──────────┼──────────────────────┼──────────────────────┼────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          FastAPI APPLICATION                        │
│                                                                     │
│   ┌──────────────────────────┐   ┌──────────────────────────────┐  │
│   │    routers/video.py      │   │    routers/analysis.py       │  │
│   │  POST /process           │   │  GET /dev/analysis/jobs      │  │
│   │  POST /process/upload    │   │  GET /dev/analysis/{uuid}    │  │
│   │  GET  /status/{job_id}   │   │  GET /dev/analysis/{uuid}/   │  │
│   │  POST /cancel/{job_id}   │   │       summary               │  │
│   └──────────┬───────────────┘   │  GET /dev/video/{uuid}       │  │
│              │                   └──────────────────────────────┘  │
│              ▼                                                     │
│   ┌──────────────────────────┐                                     │
│   │      Job Manager         │  ← In-memory job state store       │
│   │  create / update / get   │    (dict + threading.Lock)          │
│   │  cancel / is_cancelled   │                                     │
│   └──────────┬───────────────┘                                     │
│              │                                                     │
│              ▼                                                     │
│   ┌──────────────────────────┐                                     │
│   │      Worker Pool         │  ← Bounded thread pool              │
│   │  queue.Queue(maxsize=20) │    (2 concurrent workers)           │
│   │  N daemon worker threads │                                     │
│   └──────────┬───────────────┘                                     │
│              │                                                     │
│              ▼                                                     │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │                  PROCESSING PIPELINE                      │     │
│   │                                                          │     │
│   │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐ │     │
│   │  │  Input   │→ │  Audio   │→ │Transcribe │→ │ Select │ │     │
│   │  │Processing│  │Extraction│  │  (Whisper) │  │Segments│ │     │
│   │  └──────────┘  └──────────┘  └───────────┘  └───┬────┘ │     │
│   │                                                  │      │     │
│   │  ┌──────────┐  ┌──────────────────┐              │      │     │
│   │  │ Generate │← │ Analysis         │←─────────────┘      │     │
│   │  │  Clips   │  │ Collector        │                     │     │
│   │  └────┬─────┘  └──────────────────┘                     │     │
│   │       │                                                  │     │
│   └───────┼──────────────────────────────────────────────────┘     │
│           ▼                                                        │
│   ┌──────────────────────────┐   ┌───────────────────────────┐    │
│   │    outputs/{run_uuid}/   │   │   GC Daemon Thread        │    │
│   │  ├── {uuid}_clip_0.mp4  │   │   Periodic temp/output    │    │
│   │  ├── {uuid}_clip_1.mp4  │   │   cleanup                 │    │
│   │  ├── {uuid}_clip_2.mp4  │   └───────────────────────────┘    │
│   │  └── analysis.json      │                                     │
│   └──────────────────────────┘                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Why Async Architecture

The original MVP used synchronous processing: the client blocked on `POST /process` until all 3 clips were generated. This caused:

1. **HTTP timeouts** — Video download + transcription + clip generation can take 30–120 seconds, exceeding typical gateway timeouts
2. **No user feedback** — The client had no visibility into progress during processing
3. **No cancellation** — A user couldn't abort a bad submission
4. **Resource starvation** — Long-running requests held web server threads, blocking new connections

The async job queue architecture solves all four problems while remaining **single-process** (no Redis, no Celery, no external queue). The `JobWorkerPool` uses Python's `threading` and `queue.Queue` to decouple request handling from processing, and the in-memory `_jobs` dict provides a lightweight state store.

---

## 3. API Contract

### Base URL

| Environment | URL |
|---|---|
| Local development | `http://127.0.0.1:8000` |
| Production (Render) | `https://<service-name>.onrender.com` |

All error responses use the shape `{ "error": "string" }`. The key `"detail"` is never exposed to clients (Pydantic 422 errors are intercepted and rewritten).

---

### `POST /process`

Submit a video URL for highlight extraction.

**Content-Type**: `application/json`  
**Status Code**: `202 Accepted`

**Request Body**:
```json
{
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Success Response**:
```json
{
  "job_id": "a3f8e2c9-1234-4567-8901-abcdef012345"
}
```

**Error Responses**:

| Code | Condition | Body |
|---|---|---|
| 400 | Empty `video_url` string | `{ "error": "Provide a video_url URL." }` |
| 422 | Missing `video_url` field | `{ "error": "No input provided" }` |
| 503 | Worker queue is full | `{ "error": "Server is busy. Please try again later." }` |

---

### `POST /process/upload`

Submit a video file for highlight extraction.

**Content-Type**: `multipart/form-data`  
**Status Code**: `202 Accepted`

**Request Body**: Form field `file` containing the video binary.

**Allowed file types**:

| Extension | MIME Type |
|---|---|
| `.mp4` | `video/mp4` |
| `.mov` | `video/quicktime` |
| `.mkv` | `video/x-matroska` |
| `.webm` | `video/webm` |

**Success Response**:
```json
{
  "job_id": "b4e9f3d0-5678-4abc-9012-fedcba987654"
}
```

**Error Responses**:

| Code | Condition | Body |
|---|---|---|
| 400 | Unsupported file extension | `{ "error": "Unsupported file extension '.avi'. Allowed: .mp4, .mov, .mkv, .webm" }` |
| 400 | Unsupported MIME type | `{ "error": "Unsupported content type 'text/plain'. Allowed: video/mp4, ..." }` |
| 400 | Empty file | `{ "error": "Uploaded file is empty." }` |
| 413 | File exceeds size limit | `{ "error": "Uploaded file exceeds maximum limit of 100MB." }` |
| 422 | No file field | `{ "error": "No input provided" }` |
| 503 | Worker queue is full | `{ "error": "Server is busy. Please try again later." }` |

---

### `GET /status/{job_id}`

Poll the current status of a submitted job.

**Path Parameter**: `job_id` — UUID string returned by `/process` or `/process/upload`.

**Success Response** (job in progress):
```json
{
  "status": "downloading",
  "progress": 22,
  "message": "Downloading video...",
  "elapsed_seconds": 8,
  "speed": "2.4 MB/s",
  "eta": "12s",
  "clips": null,
  "error": null,
  "run_uuid": null,
  "queue_position": null,
  "estimated_wait_seconds": null
}
```

**Success Response** (job completed):
```json
{
  "status": "completed",
  "progress": 100,
  "message": "Completed successfully",
  "elapsed_seconds": 47,
  "speed": null,
  "eta": null,
  "clips": [
    {
      "filename": "a1b2c3d4_clip_0.mp4",
      "score": 92,
      "title": "Clip 1",
      "duration": 14.5
    },
    {
      "filename": "a1b2c3d4_clip_1.mp4",
      "score": 88,
      "title": "Clip 2",
      "duration": 12.3
    },
    {
      "filename": "a1b2c3d4_clip_2.mp4",
      "score": 85,
      "title": "Clip 3",
      "duration": 15.1
    }
  ],
  "error": null,
  "run_uuid": "a1b2c3d4e5f6...",
  "queue_position": null,
  "estimated_wait_seconds": null
}
```

**Success Response** (job queued):
```json
{
  "status": "queued",
  "progress": 0,
  "message": "Queued",
  "elapsed_seconds": 3,
  "speed": null,
  "eta": null,
  "clips": null,
  "error": null,
  "run_uuid": null,
  "queue_position": 2,
  "estimated_wait_seconds": 90
}
```

**Status Values**:

| Status | Meaning | Progress Range |
|---|---|---|
| `queued` | Waiting in worker queue | 0 |
| `downloading` | yt-dlp downloading video | 5–35 |
| `extracting_audio` | FFmpeg audio extraction | 40 |
| `transcribing` | Faster-Whisper ASR | 60 |
| `selecting_segments` | Running selection heuristics | 75 |
| `generating_clips` | FFmpeg clip cutting | 80–98 |
| `completed` | All clips generated | 100 |
| `error` | Pipeline failed | — |
| `cancelled` | User cancelled the job | — |

**Error Responses**:

| Code | Condition | Body |
|---|---|---|
| 400 | Invalid UUID format | `{ "error": "Invalid job ID format" }` |
| 404 | Job ID not found | `{ "error": "Job not found" }` |

---

### `POST /cancel/{job_id}`

Cancel a queued or in-progress job. Kills any running FFmpeg/yt-dlp subprocess.

**Path Parameter**: `job_id` — UUID string.

**Success Response**:
```json
{
  "status": "cancelled",
  "message": "Job cancellation request sent successfully."
}
```

**Cancellable States**: `queued`, `downloading`, `extracting_audio`, `transcribing`, `selecting_segments`, `generating_clips`

**Error Responses**:

| Code | Condition | Body |
|---|---|---|
| 400 | Invalid UUID format | `{ "error": "Invalid job ID format" }` |
| 400 | Job in non-cancellable state | `{ "error": "Job is in 'completed' status and cannot be cancelled." }` |
| 404 | Job ID not found | `{ "error": "Job not found" }` |

---

### `GET /clips/{clip_name}`

Serve a generated clip file for download or streaming playback.

**Path Parameter**: `clip_name` — Filename in the format `{run_uuid}_clip_{index}.mp4`.

**Success Response**: `200 OK` with `Content-Type: video/mp4` binary stream.

**Error Responses**:

| Code | Condition | Body |
|---|---|---|
| 400 | Path traversal attempt or invalid format | `{ "error": "Invalid clip name format" }` |
| 404 | File not found | `{ "error": "{clip_name} not found" }` |

**Security**: Rejects names containing `..`, `/`, or `\`. Requires `_clip_` in name and `.mp4` extension.

---

### `GET /health`

Simple health check endpoint.

**Response**:
```json
{ "status": "ok" }
```

---

### Developer Analysis Endpoints

All developer endpoints live under the `/dev/` prefix and are **gated by the `ENABLE_DEBUGGER` configuration flag**. When disabled (default in production), all return `403 Forbidden`.

#### `GET /dev/analysis/jobs`

List all processed runs with analysis data.

**Response**:
```json
{
  "jobs": [
    {
      "run_uuid": "a1b2c3d4...",
      "job_id": "uuid-string",
      "filename": "video.mp4",
      "source": "youtube",
      "video_duration_seconds": 245.6,
      "timestamp": "2026-07-14T12:00:00+00:00",
      "algorithm_version": "adaptive_v2",
      "clips_count": 3,
      "candidates_count": 12
    }
  ],
  "count": 1
}
```

#### `GET /dev/analysis/{run_uuid}`

Full algorithm execution trace for a specific run. Returns the complete `analysis.json` payload containing: `meta`, `transcript`, `candidates`, `filtered_windows`, `decision_log`, `final_clips`, `stats`.

#### `GET /dev/analysis/{run_uuid}/summary`

Lightweight summary — only `meta` + `stats` + `final_clips_count`.

#### `GET /dev/video/{run_uuid}`

Serve the original video file for debugger playback. Only available when `KEEP_ORIGINAL_FOR_DEBUG=true`.

---

## 4. Job Lifecycle

### State Machine

```
                    ┌──────────────────────────────────────┐
                    │            Job Lifecycle              │
                    └──────────────────────────────────────┘

     create_job()
         │
         ▼
    ┌─────────┐    Worker picks up     ┌──────────────┐
    │ queued   │ ──────────────────────▶│ downloading   │
    └─────────┘                        └──────┬───────┘
         │                                    │
    POST /cancel                         Success│Fail/Timeout
         │                               ┌─────┴────────┐
         ▼                               ▼              ▼
    ┌───────────┐                 ┌──────────────┐  ┌───────┐
    │ cancelled │                 │extracting_   │  │ error │
    └───────────┘                 │  audio       │  └───────┘
                                  └──────┬───────┘
                                         │
                                    Success│Fail
                                    ┌─────┴────────┐
                                    ▼              ▼
                             ┌──────────────┐  ┌───────┐
                             │ transcribing │  │ error │
                             └──────┬───────┘  └───────┘
                                    │
                               Success│Fail
                               ┌─────┴────────┐
                               ▼              ▼
                        ┌──────────────┐  ┌───────┐
                        │ selecting_   │  │ error │
                        │  segments    │  └───────┘
                        └──────┬───────┘
                               │
                          Success│Fail
                          ┌─────┴────────┐
                          ▼              ▼
                   ┌──────────────┐  ┌───────┐
                   │ generating_  │  │ error │
                   │  clips       │  └───────┘
                   └──────┬───────┘
                          │
                     Success│Fail
                     ┌─────┴────────┐
                     ▼              ▼
              ┌───────────┐    ┌───────┐
              │ completed │    │ error │
              └───────────┘    └───────┘

    Note: POST /cancel can transition any active state → cancelled
```

### State Descriptions

| State | Description | Transitions To |
|---|---|---|
| `queued` | Job created, waiting in worker queue. Has `queue_position` and `estimated_wait_seconds`. | `downloading`, `cancelled` |
| `downloading` | yt-dlp downloading video from URL. Reports `speed` and `eta`. | `extracting_audio`, `error`, `cancelled` |
| `extracting_audio` | FFmpeg extracting 16kHz mono WAV. | `transcribing`, `error`, `cancelled` |
| `transcribing` | Faster-Whisper running ASR on extracted audio. | `selecting_segments`, `error`, `cancelled` |
| `selecting_segments` | Heuristic algorithm scoring and ranking candidate segments. | `generating_clips`, `error`, `cancelled` |
| `generating_clips` | FFmpeg cutting source video into individual clips. Per-clip progress 80–98%. | `completed`, `error`, `cancelled` |
| `completed` | All clips generated and persisted. `clips` array populated. | Terminal |
| `error` | Pipeline failed. `error` field contains the reason string. | Terminal |
| `cancelled` | User requested cancellation. Active subprocess killed if running. | Terminal |

### Cancellation Mechanics

1. `POST /cancel/{job_id}` sets job status to `cancelled` in the job store
2. If a subprocess (FFmpeg/yt-dlp) is registered via `set_active_process()`, it is killed with `proc.kill()`
3. Every pipeline stage checks `is_job_cancelled(job_id)` before and after its main operation
4. Cancelled jobs in terminal state cannot receive further updates (guard in `update_job`)

---

## 5. Processing Pipeline

### Pipeline Stages

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐
│  Input   │───▶│  Audio   │───▶│Transcribe │───▶│  Select  │───▶│ Generate │
│Processing│    │Extraction│    │           │    │ Segments │    │  Clips   │
└──────────┘    └──────────┘    └───────────┘    └──────────┘    └──────────┘
  5–35%           40%             60%              75%            80–98%
```

---

#### Stage 1: Input Processing

**Service**: `services/input_processing.py`

| Property | Value |
|---|---|
| **Purpose** | Acquire video file from URL or upload |
| **Inputs** | `video_url: str` OR `UploadFile` |
| **Outputs** | `Path` to local video file in `temp/` |
| **Timeout** | yt-dlp: `YT_DLP_TIMEOUT_SECONDS` (default 600s) |
| **Cancellation** | Checked in yt-dlp progress hooks |

**Sub-tasks**:
- **URL Handler** (`download_video_from_url`): Uses yt-dlp with format selection `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best`. Reports download speed and ETA via progress hooks.
- **Upload Handler** (`save_uploaded_file`): Streams upload chunks to disk (1MB default). Validates extension, MIME type, and enforces size limit.
- **Input Validator** (`get_video_input`): Ensures exactly one of URL/file is provided.

**Failure Modes**: Invalid URL, download timeout, unsupported format, corrupt file, oversized upload.

---

#### Stage 2: Validation

**Service**: `routers/video.py` (inline in `_run_pipeline`)

| Property | Value |
|---|---|
| **Purpose** | Verify video is processable |
| **Inputs** | Local video file path |
| **Outputs** | `video_duration: float` |

**Checks**:
- `ffmpeg.probe()` reads container metadata
- Duration must be ≤ 7200 seconds (2 hours)

**Failure Modes**: Corrupt container, missing format metadata, duration exceeds limit.

---

#### Stage 3: Audio Extraction

**Service**: `services/audio_extraction.py`

| Property | Value |
|---|---|
| **Purpose** | Extract speech audio track for ASR |
| **Inputs** | `video_path: str`, `job_id: str | None` |
| **Outputs** | `str` path to 16kHz mono PCM WAV file |
| **Timeout** | `FFMPEG_TIMEOUT_SECONDS` (default 300s) |
| **Cancellation** | Subprocess registered via `set_active_process()`, killed on cancel |

**FFmpeg Parameters**: `format=wav`, `acodec=pcm_s16le`, `ar=16000`, `ac=1`

**Guards**: File exists, has audio stream (via ffprobe), not already cancelled.

**Failure Modes**: No audio stream, corrupt video, FFmpeg timeout, process killed.

---

#### Stage 4: Transcription

**Service**: `services/transcription.py`

| Property | Value |
|---|---|
| **Purpose** | Speech-to-text using Faster-Whisper |
| **Inputs** | `audio_path: str` |
| **Outputs** | `TranscriptResult { segments: [{ start, end, text }] }` |
| **Model** | `base` model, CPU, int8 quantization |
| **Initialization** | Lazy-loaded with thread-safe singleton (`threading.Lock`) |

**Fallback**: If Faster-Whisper is not installed, returns a stub segment `[Transcription unavailable]`.

**Failure Modes**: Empty audio file, ASR engine failure (`502 Audio not clear enough`).

---

#### Stage 5: Segment Selection

**Service**: `services/segment_selection.py`

| Property | Value |
|---|---|
| **Purpose** | Score and rank transcript segments to find the best 3 highlight windows |
| **Inputs** | `timestamps: list[dict]`, `video_duration: float`, `max_clips: int`, `collect_analysis: bool` |
| **Outputs** | `list[Segment]` or `(list[Segment], analysis_dict)` |

See [Section 6: Selection Algorithm](#6-selection-algorithm) for full detail.

---

#### Stage 6: Clip Generation

**Service**: `services/clip_generation.py`

| Property | Value |
|---|---|
| **Purpose** | Cut source video into individual MP4 clips |
| **Inputs** | `video_path: str`, `segments: list[dict]`, `job_id: str | None` |
| **Outputs** | `list[str]` — absolute paths to generated clips |
| **Timeout** | `FFMPEG_TIMEOUT_SECONDS` per clip (default 300s) |
| **Cancellation** | Checked before each clip; subprocess registered per clip |
| **Output Directory** | `outputs/{run_uuid}/` |
| **Naming** | `{run_uuid}_clip_{index}.mp4` |

**FFmpeg Parameters**:
- `vcodec=libx264`, `acodec=aac`, `preset=fast`
- `movflags=faststart` (progressive download support)
- Audio: `volume=0.9`, fade-in 0.05s, fade-out 0.05s

**Failure Modes**: Source video missing, invalid segment boundaries, FFmpeg timeout, process killed, empty output file.

---

#### Stage 7: Metadata & Analysis Persistence

**Service**: `routers/video.py` (inline in `_run_pipeline`)

After clips are generated:
1. `analysis.json` is written to `outputs/{run_uuid}/` (when `collect_analysis=True`)
2. Original video is optionally copied for debugger playback (when `KEEP_ORIGINAL_FOR_DEBUG=true`)
3. `run_uuid` is stored in the job entry
4. Rich clip metadata (filename, score, title, duration) is built and stored as the job's `clips` value

---

## 6. Selection Algorithm

**Algorithm Version**: `adaptive_v2`  
**Default Output**: 3 clips

### Algorithm Flow

```
Raw Transcript Segments
    ↓
[1] Validate & filter (remove non-numeric, negative-duration)
    ↓
[2] Sliding window scan (step=5s, from MIN_START=5s)
    ↓
    For each window position:
      ├── Score stopping points within [MIN_DURATION, MAX_DURATION]
      ├── Apply energy filter (speech_ratio ≥ 0.6)
      └── Record candidate with metrics
    ↓
[3] Dedup (best score per unique start,end pair)
    ↓
[4] Rank by word density score (descending)
    ↓
[5] Select top N non-overlapping candidates
    ↓
[6] Apply _align_end extension (sentence boundary alignment)
    ↓
[7] Clamp overlapping adjacent ends
    ↓
[8] Sort by start time
    ↓
[9] Fallback: fill remaining slots from uniform distribution
    ↓
[10] Guarantee exactly max_clips via duplication if needed
```

### Heuristic Constants

| Constant | Value | Purpose |
|---|---|---|
| `MIN_DURATION` | 8.0s | Shortest acceptable clip duration. Clips shorter than this feel too abrupt. |
| `PREF_MIN_DURATION` | 12.0s | Preferred minimum — clips above this get a scoring bonus. |
| `PREF_MAX_DURATION` | 15.0s | Preferred maximum — target clip length for social media. |
| `MAX_DURATION` | 20.0s | Hard ceiling — no clip exceeds this before extension. |
| `BUFFER` | 3.0s | Extension allowance beyond preferred max to avoid abrupt cuts. |
| `MIN_START` | 5.0s | Skip intro content (logos, music, filler). |
| `PAUSE_THRESHOLD` | 0.8s | Gap between segments that indicates a natural break point. |
| `ENERGY_RATIO_THRESHOLD` | 0.6 | Minimum ratio of speech-to-clip duration. Filters out mostly-silent windows. |
| `STEP` | 5.0s | Sliding window stride. Balances granularity vs. computation. |

### Stopping Point Scoring (max 8 points)

Each potential clip end point is scored on multiple heuristics:

| Heuristic | Points | Rationale |
|---|---|---|
| Sentence completion (`.` `!` `?`) | +2 | Clips ending mid-sentence feel jarring |
| Pause after segment (≥ 0.8s) | +2 | Natural speech breaks make clean cut points |
| Speaker change | +2 | Topic transitions are natural clip boundaries |
| Duration ≥ preferred minimum | +1 | Longer clips are generally more engaging |
| Transcript segment boundary | +1 | Aligning to ASR segment boundaries improves quality |

### Why Each Heuristic Exists

- **Intro filtering** (`MIN_START=5s`): Most videos start with logos, music, or "hey guys" filler that makes poor highlight content.
- **Speech density scoring** (`_word_density`): Words-per-second is the strongest signal for "interesting content" without needing NLP/LLM analysis.
- **Energy filter** (`ENERGY_RATIO_THRESHOLD=0.6`): Prevents selecting mostly-silent windows where the speaker pauses for long stretches.
- **Overlap prevention** (`_windows_overlap`): Without this, the top 3 candidates would often be overlapping windows from the same high-density region.
- **Sentence boundary extension** (`_align_end`): Extending a clip by 1–2 seconds to reach a sentence ending dramatically improves perceived quality.
- **Fallback generation** (`_uniform_fallback`): When the video has sparse speech (e.g., music video), uniform distribution across the timeline guarantees output.
- **Duplication guarantee**: The system must always return exactly `max_clips` clips — duplicating the last clip is preferable to returning fewer.

---

## 7. Operational Constraints

All values are configurable via environment variables with sensible defaults.

### Concurrency & Queue

| Setting | Env Var | Default | Description |
|---|---|---|---|
| Max concurrent jobs | `MAX_CONCURRENT_JOBS` | 2 | Worker threads in the pool |
| Max queued jobs | `MAX_QUEUED_JOBS` | 20 | `queue.Queue` maxsize; rejects with 503 when full |

### Upload Validation

| Setting | Env Var | Default | Description |
|---|---|---|---|
| Max upload size | `MAX_UPLOAD_SIZE_MB` | 100 | Maximum file upload in megabytes |
| Chunk size | `UPLOAD_CHUNK_SIZE_BYTES` | 1,048,576 | Streaming write chunk size (1MB) |
| Allowed extensions | — | `.mp4`, `.mov`, `.mkv`, `.webm` | Hardcoded in `config.py` |
| Allowed MIME types | — | `video/mp4`, `video/quicktime`, `video/x-matroska`, `video/webm` | Hardcoded |

### Video Limits

| Setting | Value | Description |
|---|---|---|
| Max video duration | 7200 seconds (2 hours) | Hardcoded in `_run_pipeline` |
| Clip count | 3 (default) | Configurable via `max_clips` parameter |

### Process Timeouts

| Setting | Env Var | Default | Description |
|---|---|---|---|
| FFmpeg timeout | `FFMPEG_TIMEOUT_SECONDS` | 300 (5 min) | Per-subprocess timeout for audio extraction and clip generation |
| yt-dlp timeout | `YT_DLP_TIMEOUT_SECONDS` | 600 (10 min) | Download timeout checked in progress hooks |

### Garbage Collection

| Setting | Env Var | Default | Description |
|---|---|---|---|
| Cleanup interval | `CLEANUP_INTERVAL_SECONDS` | 3600 (1 hour) | How often the GC daemon sweeps |
| Temp file max age | `TEMP_FILE_MAX_AGE_HOURS` | 4.0 | Delete temp files older than this |
| Output dir max age | `OUTPUT_DIR_MAX_AGE_HOURS` | 24.0 | Delete run output directories older than this |

### Developer Features

| Setting | Env Var | Default | Description |
|---|---|---|---|
| Enable debugger | `ENABLE_DEBUGGER` | `false` | Gates all `/dev/*` endpoints |
| Keep original video | `KEEP_ORIGINAL_FOR_DEBUG` | `false` | Copy source video into outputs for debugger playback (requires `ENABLE_DEBUGGER=true`) |

---

## 8. Error Contract

All error responses use the schema `{ "error": "string" }`. The `"detail"` key is never exposed.

### Client Errors (4xx)

| Code | Error | Source | Recovery Strategy |
|---|---|---|---|
| 400 | `Provide a video_url URL.` | `POST /process` with empty string | Provide a non-empty URL |
| 400 | `Unsupported file extension '...'` | Upload validation | Use .mp4, .mov, .mkv, or .webm |
| 400 | `Unsupported content type '...'` | Upload validation | Set correct Content-Type header |
| 400 | `Uploaded file is empty.` | Upload validation | Upload a non-empty file |
| 400 | `Video file not found: ...` | Audio extraction / clip gen | Internal error — report bug |
| 400 | `Video file contains no audio track.` | Audio extraction | Provide a video with audio |
| 400 | `Could not read video duration: ...` | Duration guard | Provide a valid video file |
| 400 | `Video too long (max 2 hours)` | Duration guard | Trim video before submission |
| 400 | `Invalid job ID format` | Status / cancel endpoints | Use the UUID returned by /process |
| 400 | `Invalid clip name format` | Clip serving | Use exact filename from job status |
| 404 | `Job not found` | Status / cancel endpoints | Job ID expired or never existed |
| 404 | `{clip_name} not found` | Clip serving | Clips may have been garbage-collected |
| 408 | `Audio extraction timed out after ...s` | Audio extraction | Retry or use shorter video |
| 408 | `FFmpeg generation timed out after ...s` | Clip generation | Retry or use shorter video |
| 408 | `Video download timed out.` | Input processing | Retry or check URL accessibility |
| 413 | `Uploaded file exceeds maximum limit of ...MB.` | Upload validation | Compress or trim video |
| 422 | `No input provided` | Pydantic validation | Provide `video_url` or `file` |

### Server Errors (5xx)

| Code | Error | Source | Recovery Strategy |
|---|---|---|---|
| 499 | `Job cancelled by user.` | Any pipeline stage | User-initiated — not an error |
| 500 | `clip_N.mp4 was not produced by FFmpeg.` | Clip generation | Report bug — FFmpeg produced empty output |
| 500 | `Audio extraction produced no output file.` | Audio extraction | Report bug |
| 502 | `Audio not clear enough` | Transcription | Audio quality too low for ASR |
| 503 | `Server is busy. Please try again later.` | Job submission | Wait and retry |

---

## 9. Observability

### Logging

The application uses Python's `logging` module with structured format:

```
%(asctime)s [%(levelname)s] %(name)s: %(message)s
```

**Logger namespaces**:
- `__main__` — FastAPI app lifecycle
- `routers.video` — Pipeline orchestration
- `services.*` — Individual pipeline stages
- `instrumentation` — Resource metrics
- `garbage_collector` — GC sweep results

### Instrumentation (`log_instrumentation`)

Called at the start and end of each pipeline stage. Logs:
- **Process RSS** (resident memory in MB)
- **Virtual Memory** (total, available, percent, used, free)
- **Temp Disk Free** (available disk space in GB)
- **Elapsed Time** per stage

### Analysis Collector

When `collect_analysis=True` (default in pipeline), the `AnalysisCollector` records:

| Data | Description |
|---|---|
| `meta` | Algorithm version, schema version, video metadata, processing time, config snapshot |
| `transcript` | Full transcript with per-segment word count and duration |
| `candidates` | Every candidate window with full execution trace, metrics, start/end analysis, stopping points |
| `filtered_windows` | Windows rejected before becoming candidates (no speech, no stopping point, failed energy filter) |
| `decision_log` | Global pipeline decisions (scan, filter, dedup, rank, select, extend, clamp) |
| `final_clips` | Selected clips with selection explanation, start/end reasoning, key strengths |
| `stats` | Aggregate statistics: duration distribution, word density, speech ratio, stop scores, rejection breakdown |

### Debug Dashboard

The Algorithm Debugger is a React application (`dashboard/`) that visualizes `analysis.json` data:

| Tab | Purpose |
|---|---|
| **Timeline** | Interactive timeline showing candidate positions, selections, and overlaps |
| **Clips** | Final clip details with scores and reasoning |
| **Candidates** | Full candidate explorer with side-by-side comparison |
| **Transcript** | Full transcript with segment highlighting |
| **Stats** | Aggregate statistics with Chart.js visualizations |

---

## 10. Non-Goals

These are intentionally excluded from the current system and should **not** be added without explicit architectural review.

| Non-Goal | Rationale |
|---|---|
| **No distributed workers** | The thread-based worker pool is sufficient for current scale. Adding Redis/Celery introduces operational complexity without proportional benefit. |
| **No database persistence** | Jobs are ephemeral. The in-memory dict is wiped on restart. This is acceptable because clips are the durable output, not job metadata. |
| **No cloud storage dependency** | All storage is local filesystem. No S3, GCS, or CDN. Keeps deployment simple and avoids cloud vendor lock-in. |
| **No LLM/AI scoring** | Speech density heuristics are fast, deterministic, and transparent. LLMs add latency, cost, and non-determinism without significant quality improvement at current scale. |
| **No GPU requirement** | Faster-Whisper `base` model on CPU with int8 quantization provides acceptable latency. GPU would help for `large` model but isn't needed for MVP. |
| **No user authentication** | Single-tenant deployment. Authentication adds middleware complexity. If needed, deploy behind a reverse proxy with auth. |
| **No real-time streaming** | Clips are generated and served as files, not streamed. WebSocket-based live processing is out of scope. |
| **No multi-language optimization** | Faster-Whisper's `base` model handles multilingual input but isn't optimized for any specific language. |

---

## 11. Future Evolution

These are **documented possibilities**, not commitments. Each requires an architecture decision record (ADR) before implementation.

### Near-Term (Low Complexity)

| Enhancement | Impact | Prerequisite |
|---|---|---|
| **Configurable clip count** | Allow clients to request 1–10 clips via API parameter | Already supported internally via `max_clips` |
| **Webhook notifications** | POST to a callback URL when job completes instead of polling | Add `callback_url` to request body |
| **Improved fade timings** | Increase audio/video fade to 1–2 seconds for smoother UX | Update FFmpeg filter parameters in `clip_generation.py` |
| **Video fade filters** | Add `fade=t=in/out` video filter synchronized with audio | Add vf parameter to FFmpeg stream builder |

### Medium-Term (Moderate Complexity)

| Enhancement | Impact | Prerequisite |
|---|---|---|
| **Redis job queue** | Replace in-memory dict with Redis for persistence across restarts | Add `redis` dependency, refactor `job_manager.py` |
| **PostgreSQL metadata** | Store job history, analytics, and user data | Add `sqlalchemy`/`asyncpg`, create migration system |
| **S3/GCS clip storage** | Upload generated clips to cloud storage with signed URLs | Add cloud SDK, modify `generate_clips` output handling |
| **Rate limiting** | Per-IP or per-API-key throttling | Add middleware (e.g., `slowapi`) |

### Long-Term (High Complexity)

| Enhancement | Impact | Prerequisite |
|---|---|---|
| **ML-based ranking** | Train a model on user engagement data to replace heuristic scoring | Requires labeled dataset, inference pipeline |
| **Horizontal scaling** | Multiple backend instances with shared queue and storage | Requires Redis/RabbitMQ + shared filesystem or object storage |
| **User accounts & billing** | Multi-tenant SaaS with usage-based pricing | Requires auth, database, Stripe integration |
| **GPU ASR** | Use Faster-Whisper `large-v3` on GPU for better accuracy | Requires GPU instance, CUDA setup |

---

## Appendix: File Inventory

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI app, CORS, lifecycle hooks, GC daemon, static mount |
| `backend/config.py` | Centralized env-var configuration |
| `backend/job_manager.py` | In-memory job store, state machine, cancellation, subprocess tracking |
| `backend/utils.py` | Temp paths, file cleanup, instrumentation logging, GC sweeper |
| `backend/routers/video.py` | `/process`, `/process/upload`, `/status`, `/cancel` endpoints |
| `backend/routers/analysis.py` | `/dev/analysis/*` debugger endpoints |
| `backend/services/input_processing.py` | URL download (yt-dlp), file upload validation, input routing |
| `backend/services/audio_extraction.py` | FFmpeg audio extraction with subprocess tracking |
| `backend/services/transcription.py` | Faster-Whisper ASR with lazy model loading |
| `backend/services/segment_selection.py` | Selection algorithm, sliding window, scoring, analysis collection |
| `backend/services/clip_generation.py` | FFmpeg clip cutting with subprocess tracking |
| `backend/services/job_worker.py` | Bounded thread pool with `queue.Queue` |
| `backend/services/analysis_collector.py` | Execution trace collector for debugger |
| `backend/services/analysis_constants.py` | Algorithm and schema version strings |
