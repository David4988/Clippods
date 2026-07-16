# 🎬 ClipPods

> An asynchronous AI-powered video highlight extraction platform that transforms long-form videos into short, social-media-ready clips using local speech recognition and heuristic ranking.
> **Designed and built a production-style asynchronous media processing pipeline featuring background job orchestration, heuristic ranking algorithms, observability tooling, and developer analysis dashboards.**

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![React](https://img.shields.io/badge/React-Dashboard-blue)
![Status](https://img.shields.io/badge/Status-Production%20Prototype-orange)

---

## ✨ Features

### Video Processing

* YouTube URL ingestion
* Direct video uploads
* Support for MP4, MOV, MKV, WebM
* Up to 2-hour videos

### Highlight Extraction

* Local Faster-Whisper transcription
* Speech-density ranking heuristics
* Adaptive segment selection
* Automatic sentence-boundary alignment
* Non-overlapping clip generation

### Async Processing

* Background worker pool
* Queue-based job processing
* Real-time progress tracking
* Job cancellation support
* Concurrent request handling

### Developer Tooling

* Algorithm Debugger Dashboard
* Full execution traces
* Candidate visualization
* Timeline analysis
* Performance instrumentation
* Automatic cleanup daemon

---

## 🏗 Architecture

```text
Client
   ↓
FastAPI API
   ↓
Job Manager
   ↓
Worker Pool
   ↓
Processing Pipeline

Input
 ↓
Audio Extraction
 ↓
Faster Whisper
 ↓
Adaptive Segment Selection
 ↓
Clip Generation
 ↓
Analysis Persistence
```

---

## 📸 System Architecture

*(Insert architecture image here)*

---

## ⚡ Processing Pipeline

```text
Video URL / Upload
        ↓
Input Processing
        ↓
Audio Extraction
        ↓
Speech Transcription
        ↓
Candidate Generation
        ↓
Adaptive Ranking
        ↓
Clip Generation
        ↓
Analysis Storage
```

---

## 🚀 API Workflow

```text
POST /process
        ↓
returns job_id
        ↓
GET /status/{job_id}
        ↓
completed
        ↓
GET /clips/{clip_name}
```

---

## 📡 API Endpoints

| Method | Endpoint             | Purpose           |
| ------ | -------------------- | ----------------- |
| POST   | `/process`           | Submit URL        |
| POST   | `/process/upload`    | Upload file       |
| GET    | `/status/{job_id}`   | Track progress    |
| POST   | `/cancel/{job_id}`   | Cancel processing |
| GET    | `/clips/{clip_name}` | Download clip     |
| GET    | `/health`            | Health check      |
| GET    | `/dev/analysis/*`    | Debugger APIs     |

---

## 🧠 Selection Algorithm

Algorithm Version:

```text
adaptive_v2
```

Pipeline:

```text
Transcript
     ↓
Sliding Window Scan
     ↓
Speech Density Scoring
     ↓
Sentence Boundary Detection
     ↓
Overlap Filtering
     ↓
Ranking
     ↓
Clip Selection
```

Selection considers:

* Word density
* Pause detection
* Sentence completion
* Speaker transitions
* Speech ratio
* Natural stopping points

---

## 📊 Algorithm Debugger

ClipPods ships with an internal debugger dashboard for heuristic tuning.

Features:

* Timeline visualization
* Candidate explorer
* Transcript inspection
* Statistical analysis
* Final clip reasoning
* Full execution traces

---

## 🛠 Tech Stack

### Backend

* Python 3.12
* FastAPI
* Faster-Whisper
* FFmpeg
* yt-dlp

### Frontend

* React 19
* Vite
* Chart.js

### Infrastructure

* Render
* Vercel
* Local filesystem storage

---

## 📈 Production Features

* Bounded worker pool
* Queue management
* Process cancellation
* Automatic garbage collection
* Resource instrumentation
* Timeout protection
* Thread-safe state management

---

## 🚫 Non Goals

* No LLM dependencies
* No Redis/Celery
* No database persistence
* No GPU requirement
* No external AI APIs

---

## 🏃 Local Development

```bash
git clone https://github.com/<username>/ClipPods.git
cd ClipPods

pip install -r requirements.txt

uvicorn main:app --reload
```

API Docs:

```text
http://localhost:8000/docs
```

---

## 📂 Project Structure

```text
backend/
├── routers/
├── services/
├── dashboard/
├── outputs/
├── uploads/
├── temp/
├── job_manager.py
├── config.py
└── main.py
```

---

## 🎯 Why ClipPods?

Most automatic clipping tools rely heavily on expensive LLM pipelines.

ClipPods explores a different approach:

* deterministic heuristics
* local AI inference
* transparent ranking logic
* lower infrastructure cost
* easier debugging and explainability

---

## 📌 Current Status

```text
Production Prototype
Architecture Version: v2
Selection Algorithm: adaptive_v2
Deployment: Render + Vercel
```

---

Built during late-night debugging sessions, excessive coffee consumption, and a questionable amount of FFmpeg logs.

---
