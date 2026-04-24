# ClipPods Video Chopper

Premium SaaS application for video clipping — upload or import from YouTube, trim precisely, and download high-quality clips.

---

## Prerequisites

| Tool       | Required | How to get it |
|------------|----------|---------------|
| **Node.js 18+** | ✅ | https://nodejs.org or use `nvm` |
| **Docker Desktop** | ✅ | https://docker.com/products/docker-desktop |
| **FFmpeg**  | ✅ | https://ffmpeg.org/download.html — place in `D:\tools\ffmpeg` or add to PATH |
| **yt-dlp**  | ⚠️ Optional | https://github.com/yt-dlp/yt-dlp — place in `D:\tools\yt-dlp` or add to PATH |

> Run `.\scripts\setup-windows.ps1` to check which tools are installed.

---

## Quick Start

Open **4 terminals** in `D:\theclippods`:

### Terminal 1 — Start Redis
```powershell
docker-compose up -d
```

### Terminal 2 — Start Backend (port 4000)
```powershell
cd backend
npm install
npm run dev
```

### Terminal 3 — Start Worker
```powershell
cd worker
npm install
npm run dev
```

### Terminal 4 — Start Frontend (port 3000)
```powershell
cd frontend
npm install
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## Architecture

```
Frontend (Next.js :3000)
    ↓ HTTP
Backend (Express :4000)
    ↓ BullMQ
Redis (Docker :6379)
    ↓ Job claim
Worker (FFmpeg)
    ↓ Output
D:\theclippods\outputs\
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/upload` | Upload a local video file |
| POST | `/api/youtube/import` | Import a YouTube video via yt-dlp |
| POST | `/api/clip/create` | Create a clip processing job |
| GET  | `/api/job/:id/status` | Poll job status and progress |
| GET  | `/api/output/:id` | Download the finished clip |
| GET  | `/api/output/stream/:videoId` | Stream original video for editor playback |
| POST | `/api/waitlist` | Join the AI product waitlist |

---

## Directory Structure

```
D:\theclippods\
├── frontend/          Next.js App Router (UI)
├── backend/           Express API server
├── worker/            BullMQ worker (FFmpeg processing)
├── shared/            Shared types & constants
├── uploads/           Uploaded/imported source videos
├── outputs/           Generated clip files
├── temp/              Temporary upload staging
├── logs/              Application logs
├── scripts/           Windows setup scripts
├── docker-compose.yml Redis container
└── README.md
```

---

## Clip Processing Modes

- **Fast** — Stream copy (`-c copy`), instant but may have imprecise start frames
- **Accurate** — Full re-encode (libx264 + AAC), frame-precise but slower

---

## Future Product

**ClipPods Video Clipper** — AI-powered highlight detection, smart clipping, and content repurposing. Join the waitlist at the bottom of any page.

---

## License

Proprietary — ClipPods © 2026
