# 🎬 ClipPods

> **Automated video highlight clipper** — Extract the most engaging segments from any video and produce short, polished MP4 clips ready for social media.

ClipPods takes a video (YouTube URL or file upload) and automatically produces **3 short highlight clips** by analyzing speech density, without requiring any LLM/AI inference — making it fast, deterministic, and free of API costs.

The shipping clip-selection engine (`legacy_v2`) is unchanged and pinned by golden
tests. Work since then has gone into the layer underneath it: a typed transcript
contract, measured speech regions, quality flags, and an adaptive ASR pipeline for
Hindi and Tamil. Everything new is opt-in, so the demo path behaves as before.

---

## 📍 Project status (as of 2026-10-06)

Work follows the phased plan in [docs/plan/master-engineering-plan.md](docs/plan/master-engineering-plan.md).
Phases completed so far:

| Phase | Scope | Status |
| ----- | ----- | ------ |
| **0 — Safety net & measurement harness** | `backend/evaluation/` runner with a content-hash stage cache; `backend/tests/legacy/` golden + characterisation tests; tests isolated from real `temp/`/`outputs/` | ✅ Complete |
| **1 — Backend correctness** | UTF-8 atomic analysis writes, `.env` load order, no stub transcripts, real error messages, cancellation + progress during transcription, GC exemption for active jobs, job-record TTL, per-stage timings, analysis for failed runs | ✅ Complete |
| **2 — Dataset assembly & baseline** | Manifest/label tooling (`add`, `label templates`, `check`, `freeze`) and automatic metrics are built; owner labelling and the frozen `v1` dataset are human work still outstanding | 🟡 Tooling complete, labelling open |
| **3 — Rich transcription contract** | `services/transcript.py` contract, Silero VAD speech regions, word timestamps, language probes, quality flags; `legacy` decode byte-identical to the pre-contract reference | ✅ Complete |
| **4 — ASR experiment matrix** | `base` vs `large-v3`, forced vs auto language, VAD, and `condition_on_previous_text` measured on 9 real podcasts (English/Hindi/Tamil); evidence EV-2.x/EV-3.x in the plan | ✅ Measurements complete |
| **ASR stage — adaptive pipeline (`adaptive_v1`)** | Per-language decode profiles, quality gate, one region-scoped retry, safe merge, full per-segment provenance; validated on real podcasts including a 74-minute end-to-end run | ✅ Implemented (opt-in), limits below |

Not started: **Phase 5** (units & cut points), **Phase 6** (`boundary_v1` engine),
**Phase 7–8** (local Qwen semantic judge via Ollama), **Phase 9** (Debugger v2),
**Phase 10** (docs/repo hygiene), **Phase 11** (legacy retirement). No LLM/SLM is
integrated yet, by decision D11.

---

## ✨ Features

- **YouTube URL & File Upload** — Submit a YouTube link or upload MP4, MOV, MKV, WebM files
- **Automatic Highlight Detection** — Scores transcript windows by speech density to find the best segments
- **3 Optimized Clips** — Generates 3 ready-to-share MP4 clips per video
- **Real-time Progress Tracking** — Poll job status while processing runs in the background
- **Job Cancellation** — Cancel in-progress jobs at any time
- **Algorithm Debugger Dashboard** — React-based debugger UI for heuristic tuning and analysis
- **Automatic Cleanup** — Garbage collection for temp files and expired outputs
- **Source-language ASR** — Explicit `auto | en | hi | ta` language choice (plus `mixed` on the adaptive pipeline); speech is transcribed, never translated
- **Typed transcript contract** — Segment and word timings, confidence fields, Silero VAD speech regions and visible quality flags, saved as `transcript.json` per run
- **Adaptive ASR with bounded retry** — Opt-in `adaptive_v1`: picks a decode profile per language, gates transcript quality, re-decodes only suspicious regions once, and records which model produced every segment
- **Offline evaluation harness** — Runs the pipeline on local 1–2 hour files with a stage cache, and stores comparable run artifacts

---

## 🏗️ Architecture

```
User → Submit URL or Upload File
       → Backend creates a job (returns job_id)
       → Worker thread picks up job from queue
       → Pipeline: download → extract audio → transcribe → select → clip
       → Clips saved to outputs/{run_uuid}/
       → User polls GET /status/{job_id} until completed
       → User downloads clips via GET /clips/{filename}
```

### Transcription stage

Three ASR profiles, chosen with `ASR_PROFILE`:

| Profile | Decode | Use |
| ------- | ------ | --- |
| `legacy` (default) | `base`, no word timestamps, no VAD filter | Byte-identical to the original pipeline; `legacy_v2` clip output unchanged |
| `rich_v1` | `legacy` + word timestamps + VAD filter + script-aware compression-ratio fallback | Boundary-aware work on one fixed decode |
| `adaptive_v1` | Per-language profile, quality gate, one region-scoped retry | Hindi/Tamil podcasts where a single decode is unreliable |

`adaptive_v1` runs:

```
audio → Silero VAD + language probes (measured once)
      → profile selection   en_v1 (base) · hi_v1 / ta_v1 (large-v3) · mixed_v1 (large-v3, conservative)
      → attempt 1 (whole file)
      → quality gate        ok | degraded | hard_fail  + suspicious spans
      → retry regions       merged, padded, snapped to VAD silence gaps
      → ONE retry per region (base → large-v3; large-v3 → previous-text flipped)
      → accept only if that region gains trusted speech, then merge in place
      → re-flag + gate again → ok | degraded | still_degraded | hard_fail
```

Guarantees that matter downstream: a manual language choice is never silently
overridden (probe disagreement is recorded as a reason), each region is retried at
most once, merges never duplicate text or reorder segments, and every segment
carries an `attempt` pointing at the model, profile and retry reason that produced it.

### Tech Stack

| Component          | Technology                                |
| ------------------ | ----------------------------------------- |
| Backend Framework  | Python 3.12+, FastAPI                     |
| ASR Engine         | Faster-Whisper, CPU/int8 — `base` (English) and `large-v3` (Hindi/Tamil/mixed) |
| Speech detection   | Silero VAD (bundled with faster-whisper)  |
| Video Processing   | FFmpeg (libx264 + AAC) via `ffmpeg-python`|
| Video Download     | yt-dlp                                    |
| Dashboard          | React 19, Vite 8, Chart.js               |
| Deployment         | Render (VPS) + Cloudflare Tunnel          |

---

## 📁 Project Structure

```
SaaS_Hackathon/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Centralized configuration
│   ├── job_manager.py          # In-memory job tracking
│   ├── utils.py                # Shared utilities & garbage collection
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example            # Environment variable template
│   ├── routers/
│   │   ├── video.py            # Video upload & processing endpoints
│   │   └── analysis.py         # Algorithm debugger endpoints
│   ├── services/
│   │   ├── input_processing.py # URL download & file upload handling
│   │   ├── audio_extraction.py # Audio track extraction via FFmpeg
│   │   ├── transcription.py    # Faster-Whisper decode + ASR profiles
│   │   ├── transcript.py       # Typed transcript contract (segments, words, attempts)
│   │   ├── transcript_quality.py # Quality flags + the adaptive quality gate
│   │   ├── speech_regions.py   # Silero VAD speech regions
│   │   ├── asr_pipeline.py     # adaptive_v1: profile choice, retry, merge, provenance
│   │   ├── segment_selection.py# Speech-density scoring & selection (legacy_v2)
│   │   ├── clip_generation.py  # Final clip cutting via FFmpeg
│   │   ├── job_worker.py       # Worker pool management
│   │   └── analysis_collector.py # Debugger data collection
│   ├── evaluation/             # Offline harness: runner, stages, cache, datasets, experiments
│   └── tests/                  # Pytest test suite (+ tests/legacy golden files)
├── dashboard/                  # React + Vite algorithm debugger UI
│   ├── src/
│   │   ├── App.jsx             # Main application component
│   │   ├── components/         # UI components (TabNav, Clips, etc.)
│   │   ├── api/                # API client layer
│   │   └── utils/              # Frontend utilities
│   ├── package.json
│   └── vite.config.js
├── docs/plan/                  # Master engineering plan, decisions and evidence log
├── eval_data/                  # Offline evaluation data & experiment artifacts (git-ignored)
├── static/                     # Static assets
├── vercel.json                 # Vercel deployment config (unsupported — see Deployment)
└── README.md                   # ← You are here
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12 or 3.13.** Not 3.14 — the `av` dependency (pulled in by
  `faster-whisper`) has no wheels for 3.14 and fails to build from source. Without
  `faster-whisper`, every job fails at the transcription step with
  "Transcription is unavailable".
- **Node.js 18+** and **npm** (only needed for the Algorithm Debugger dashboard)
- **FFmpeg** — `ffmpeg` and `ffprobe` on `PATH`
- **cloudflared** — the tunnel is already configured in `~/.cloudflared/config.yml`
  and maps `api.theclippods.com` → `http://127.0.0.1:8000`

### 1. Clone the Repository

```bash
git clone <repo-url>
cd SaaS_Hackathon
```

### 2. Backend Setup

The virtual environment lives at the **repository root**, not inside `backend/`.
`.venv312` is the development environment: run the server, tests and the
evaluation harness with its interpreter. `backend/requirements.lock.txt` pins the
exact versions (including the ASR stack), so transcripts are reproducible.

**macOS / Linux:**

```bash
# From the repository root. Pin the interpreter — see Prerequisites.
python3.12 -m venv .venv312
source .venv312/bin/activate

pip install -r backend/requirements.txt -c backend/requirements.lock.txt
```

**Windows (PowerShell):**

```powershell
# From the repository root. Pin the interpreter — see Prerequisites.
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1

pip install -r backend\requirements.txt -c backend\requirements.lock.txt
```

> If `py -3.12` isn't found, install Python 3.12 or 3.13 from python.org
> (not the Microsoft Store version — it's often missing or aliased) and make
> sure "Add python.exe to PATH" is checked during setup.
>
> Use the `.\` prefix when running `Activate.ps1` — PowerShell treats a bare
> `.venv312\Scripts\Activate.ps1` as a module name, not a relative script path,
> and errors with "The module '.venv312' could not be loaded". If you instead
> hit "running scripts is disabled on this system", the execution policy is
> blocking it; run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
> in that terminal session and retry.

Verify that transcription is actually available before demoing — this must print
`ok`, otherwise every job fails at transcription:

```bash
# macOS/Linux
.venv312/bin/python -c "import faster_whisper; print('ok')"
```

```powershell
# Windows
.venv312\Scripts\python.exe -c "import faster_whisper; print('ok')"
```

### 3. Environment Variables

All settings have working defaults — **no `.env` file is required to run the app.**
Settings are read from real environment variables and from `backend/.env`
(real environment variables win). `SARVAM_API_KEY` in `backend/.env.example` is a
leftover: no code reads it, and transcription runs locally on Faster-Whisper.

```bash
cp backend/.env.example backend/.env   # optional
```

| Variable                   | Description                        | Default       |
| -------------------------- | ---------------------------------- | ------------- |
| `APP_ENV`                  | Application environment            | `development` |
| `ENABLE_DEBUGGER`          | Enable algorithm debugger          | `false`       |
| `MAX_CONCURRENT_JOBS`      | Worker thread pool size            | `2`           |
| `MAX_QUEUED_JOBS`          | Maximum queued jobs                | `20`          |
| `MAX_UPLOAD_SIZE_MB`       | Max upload file size (MB)          | `100`         |
| `FFMPEG_TIMEOUT_SECONDS`   | FFmpeg subprocess timeout          | `300`         |
| `YT_DLP_TIMEOUT_SECONDS`   | yt-dlp download timeout            | `600`         |
| `MAX_VIDEO_DURATION_SECONDS` | Longest accepted video (seconds) | `7200`        |
| `ASR_PROFILE`              | `legacy` (original decode), `rich_v1` (word timestamps + VAD filtering) or `adaptive_v1` (per-language profiles + one region-scoped retry) | `legacy` |
| `ASR_MODEL_DIR`            | Folder holding the Faster-Whisper models (a Hugging Face hub cache); unset = `~/.cache/huggingface/hub` | unset |
| `TEMP_FILE_MAX_AGE_HOURS`  | Temp file age before cleanup (files of running jobs are never removed) | `4` |
| `OUTPUT_DIR_MAX_AGE_HOURS` | Output run folder age before cleanup | `24`        |
| `DEBUG_RUN_MAX_AGE_HOURS`  | With `ENABLE_DEBUGGER=true`: age before runs with `analysis.json` are removed (`0` = keep) | `0` |
| `JOB_RECORD_TTL_HOURS`     | How long finished jobs stay queryable via `/status` | `24` |
| `CLIPPODS_EVAL_DIR`        | Offline evaluation data directory  | `<repo>/eval_data` |

### 4. Dashboard Setup

```bash
cd dashboard
npm install
```

---

## ▶️ Running the Project

The backend serves **both** the API and the landing/upload UI (`static/index.html`),
so the demo needs the backend and the tunnel — nothing else.

### 1. Start the Backend Server

Must be run from `backend/`, because `main.py` imports `config`, `routers`, and
`services` as top-level modules.

**macOS / Linux:**

```bash
cd backend
../.venv312/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Windows (PowerShell):**

```powershell
cd backend
..\.venv312\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- UI: `http://127.0.0.1:8000/`
- API: `http://127.0.0.1:8000/health`

Bind to `127.0.0.1`, not `0.0.0.0` — the Cloudflare Tunnel connects over loopback,
and there is no authentication on these endpoints.

> **Windows note:** if only Python 3.11 is available on the machine (no 3.12/3.13
> install), the app still runs — `faster-whisper`'s `av` dependency ships prebuilt
> wheels for 3.11 too. Just make sure the `faster_whisper` import check above
> prints `ok`; only Python 3.14 is known to break the build.

### 2. Start the Cloudflare Tunnel

In a separate terminal. `~/.cloudflared/config.yml` already pins the tunnel ID and
the ingress rule, so no arguments are needed:

```bash
cloudflared tunnel run
```

Public URL: `https://api.theclippods.com` — this serves the full app, not just the API.

> Cloudflare's free plan rejects request bodies over **100 MB** at the edge, before
> they reach the app. Keep demo uploads under that; the UI now checks the size
> client-side and says so.

### 3. Start the Dashboard (optional — Algorithm Debugger only)

The debugger is a separate developer tool and is **not** part of the demo flow. Its
endpoints return 403 unless `ENABLE_DEBUGGER=true`.

```bash
cd dashboard
npm install
npm run dev            # http://localhost:5173
```

Start the backend with `ENABLE_DEBUGGER=true` if you want it to return data.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `POST` | `/process` | Submit a video URL. JSON body `{"video_url": "...", "language": "auto"}` → `202 {"job_id"}` |
| `POST` | `/process/upload` | Upload a video file (multipart fields `file`, optional `language`) → `202 {"job_id"}` |
| `GET`  | `/status/{job_id}` | Job status, progress, clips, error and `warnings` |
| `POST` | `/cancel/{job_id}` | Cancel a queued or running job |
| `GET`  | `/clips/{filename}` | Download a generated clip |
| `GET`  | `/health` | Health check |
| `GET`  | `/dev/analysis/jobs` | Debugger: list runs with `analysis.json` (403 unless `ENABLE_DEBUGGER=true`) |
| `GET`  | `/dev/analysis/{run_uuid}` | Debugger: full analysis for a run (`run_uuid` is on the job record) |
| `GET`  | `/dev/analysis/{run_uuid}/summary` | Debugger: meta and stats only |
| `GET`  | `/dev/video/{run_uuid}` | Debugger: original video (requires `KEEP_ORIGINAL_FOR_DEBUG=true`) |

`language` is the spoken language: `auto` (default, detected), `en`, `hi` or `ta`.
With `ASR_PROFILE=adaptive_v1` the value `mixed` is also accepted, for code-switched
speech such as Hinglish or Tanglish; other profiles reject it with a 400.
Speech is always transcribed in its own language, never translated.

Errors are returned as `{"error": "..."}`. Each run folder holds `analysis.json`
(with an `asr` summary: language decision, quality status, flags) and
`transcript.json` (the full source-language transcript: segments, confidence
fields, word timings when enabled, speech regions, quality flags). On
`adaptive_v1`, `transcript.json` also carries `attempts` (model, profile,
`condition_on_previous_text`, region, retry reasons, before/after metrics, outcome)
and `suspicious_spans`, and each segment records the `attempt` that produced it.
Failed and cancelled runs also write `analysis.json` recording the stage that
stopped and why.

---

## 🧪 Running Tests

```bash
cd backend
../.venv312/bin/python -m pytest          # Windows: ..\.venv312\Scripts\python.exe -m pytest
```

308 tests pass. They never write to `backend/temp` or `backend/outputs` — the run
fails if they do. Legacy clip-selection behaviour is pinned by golden files in
`backend/tests/legacy/`, and ASR behaviour by `tests/test_asr_contract.py` and
`tests/test_asr_pipeline.py` (profile selection, quality-gate decisions, region
construction and VAD-gap padding, the one-retry cap, model fallbacks, merge safety
and provenance). Faster-Whisper is mocked in tests; Silero VAD runs for real on
synthetic audio.

## 📏 Offline Evaluation

`backend/evaluation/` runs the pipeline on local files of any size, caches the
expensive stages and writes comparable run artifacts. See
[backend/evaluation/README.md](backend/evaluation/README.md).

Experiment scripts live in `backend/evaluation/experiments/` and never touch the
production path: real-world audio fetch and structure inspection, the `base` vs
`large-v3` matrix, the `condition_on_previous_text` ON/OFF comparison, and
`adaptive_asr_validation` for the adaptive pipeline. Artifacts and logs are written
under `eval_data/` (outside git), and findings are recorded as evidence rows in the
master plan.

### Measured ASR findings (real podcasts, CPU int8)

| Finding | Evidence |
| ------- | -------- |
| `base` is good on English podcasts and unusable on Tamil; it never produced Devanagari for Hindi | EV-3.1, EV-3.4 |
| Hindi-labelled podcasts are really Hinglish, and `base` translated Hindi speech into English text | EV-3.4 |
| `large-v3` with `condition_on_previous_text=False` is much better on 3 of 4 Hindi/Tamil windows, but **regresses** the one where ON worked: it drops speech and loses the code-switch script convention | EV-3.11 – EV-3.13 |
| Repetition loops and dropped speech are both common; segment spans stretch over dropped audio, so word density — not segment coverage — exposes it | EV-3.7, EV-3.12 |
| Word timestamps stay monotonic, but zero-length and >2 s words cluster in loop/fallback output | EV-3.9 |
| Runtime: `base` ≈ 0.1× real time at ~0.5 GB; `large-v3` ≈ 1.1–3.0× real time at 3.3–5.0 GB | EV-3.10 |

That ON/OFF conflict is exactly why `adaptive_v1` retries per region instead of
flipping the setting globally.

### Adaptive pipeline validation

Five-minute podcast-body windows, trusted words per minute of detected speech:

| Window | Previous-text ON only | OFF only | `adaptive_v1` | Loop seconds (ON / OFF / adaptive) |
| ------ | --------------------: | -------: | ------------: | ---------------------------------- |
| Tamil 1 | 44 | 138 | **139** | 178 / 32 / **15** |
| Tamil 2 | 15 | 87 | 87 | 166 / 71 / 71 |
| Hindi 1 | 19 | **125** | 72 | 245 / 82 / 113 |
| Hindi 2 | 228 | 142 | **236** | 0 / 41 / **0** |
| English | 241 (no retry, gate `ok`) | — | 241 | 0 |

Hindi 2 is the regression case: the pipeline kept the good ON transcript for 215 of
300 seconds, retried only 85 seconds, and one retry recovered ~13 s of speech that
ON had silently dropped. Merge boundaries showed no overlaps and no duplicated text
in any run.

One end-to-end long run (74-minute Tamil podcast, manual `ta`):

| Measure | Result |
| ------- | ------ |
| Wall-clock | 3 h 52 min (≈ 3.1× the audio length) |
| First pass | 70 min → `hard_fail`, 1,785 suspicious spans |
| Retries | 13 regions, one retry each (11 accepted, 2 rejected), 2 h 41 min |
| Audio re-decoded | 4,344 s of 4,439 s (98 %) |
| Final status | `still_degraded` — 1,802 s of loop-flagged text remains |
| Peak RAM | 5.8 GB |

---

## ⚙️ Configuration

All configuration is centralized in [config.py](backend/config.py) and driven by environment variables. Key settings:

- **Worker Pool**: 2 concurrent threads, 20 max queued jobs
- **Upload Limits**: 100 MB max file size, 1 MB chunk streaming
- **Supported Formats**: `.mp4`, `.mov`, `.mkv`, `.webm`
- **Timeouts**: FFmpeg 5 min, yt-dlp 10 min
- **Cleanup**: Temp files after 4 hours, output dirs after 24 hours

---

## ⚠️ Known limitations

- **Tamil long-form ASR is not solved.** With `ta_v1` (previous-text ON) the first
  pass collapses on a full-length file, so "regional" retries covered 98 % of the
  audio and the result is still degraded. Whether Tamil's first attempt should run
  with previous-text OFF, and whether a `hard_fail` first pass should cap region
  building, are open decisions.
- **`large-v3` is slow on CPU**: budget roughly 2–4× the audio length and ~3–6 GB
  RAM, so a 1–2 hour podcast is hours of processing, not minutes.
- **Retry side effects seen in validation**: one accepted region replaced correct
  Hinglish with English written in Devanagari; some retried regions start a few
  seconds late, leaving untranscribed speech at the edge; tiny weak-signal segments
  can trigger a region retry.
- **Clip selection is still `legacy_v2`**: fixed 3 clips, a 5-second start grid, and
  the cosmetic 75–98 "viral score". Boundary engineering is Phase 5–6.
- **Deployment**: only local uvicorn + Cloudflare Tunnel is supported. `vercel.json`
  and `render-build.sh` remain in the tree but cannot work with background worker
  threads, in-memory job state and local disk (decision D20).
- **Job state is in memory**: a backend restart loses queued and running jobs.

---

## 📄 License

This project was built for the SaaS Hackathon.
