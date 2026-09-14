# ClipPods — Master Engineering Plan

**Backend cleanup, transcription reliability, clip selection and boundary quality**

Status: **Checkpoint 1 approved 2026-09-14 · Phase 0 in review**
Investigation date: 2026-09-14 · Investigated at `bf7b0c9` (main)

> This document is the approved plan. The **Decision Record** below is authoritative. Where it differs from the original proposals later in the document, the Decision Record wins. Sections 1–19 are otherwise kept as reviewed at Checkpoint 1, so the reasoning stays traceable.

## Decision Record (Checkpoint 1, 2026-09-14)

**Core invariant (non-negotiable):** audio/VAD/code owns temporal boundaries · words provide the semantic index · the model judges candidate quality · the model never invents or modifies timestamps.

| ID | Decision |
|---|---|
| D1 | **Option A** approved: boundary-first deterministic pipeline + LLM re-ranker. Option C only as a data-triggered extension if candidate recall proves insufficient. |
| D2 | Measurement-only spikes approved, isolated from production. Every spike states exactly what is downloaded, approximate disk/RAM, and the question it answers; unnecessary models/dependencies are not silently retained; results are reported before the next architectural decision. |
| D3 | Language modes `auto \| en \| hi \| ta`, default `auto`. Never force translation to English. The source-language transcript is canonical for timing and semantics. |
| D4 | Code-switching policy **not decided**. Test real Hinglish/Tanglish examples first and show results (native script / romanised / mixed) before deciding. |
| D5 | ASR model chosen **only** from the measurement matrix on real Hindi/Tamil/English results. Quality over latency in this stage. |
| D6 | VAD and boundary parameters tuned from evaluation data; proposed thresholds aren't constants. Goal: natural speech boundaries. |
| D7 | No return to 8–20 s behaviour. Natural thought duration is primary. 25–60 s target and 90 s hard max stay **experimental** until clips are reviewed; longer clips are acceptable when the moment is much stronger. |
| D8 | Open loops approved conceptually (strong question, unresolved setup, provocative statement, curiosity moment). `intentional_open_loop` must be distinguished from `truncated`; `truncated` is never accepted as a quality clip. |
| D9 | Exactly 5 clips for accepted long-form inputs. Never duplicate a clip to meet the count. Tiered fallback without manufacturing garbage. For extremely short inputs where 5 distinct valid clips are impossible, surface the product conflict for a decision before implementation locks behaviour in. |
| D10 | The cosmetic "viral score" isn't exposed as real quality. Internal normalised score + reason breakdown during development; the user-facing display is decided later. |
| D11 | No SLM integration yet. Deterministic/boundary baseline + evaluation first, then an offline spike with the local Qwen3.5-9B. Smaller models compared only with a real reason. |
| D12 | Qwen thinking disabled initially; tested only if data shows a meaningful quality benefit worth the latency. |
| D13 | Single heavy-inference slot unless measurement proves higher concurrency safe and beneficial. |
| D14 | Local long-form ingestion approved: the offline evaluation runner accepts local 1–2 h files regardless of the public 100 MB limit. Public uploads not redesigned yet. |
| D15/D16 | Frozen evaluation approach approved; the product owner labels data and performs blind A/B. Media outside git; manifests/labels/results versioned. |
| D17 | Engine selection via environment/config flag; dev-only override allowed for debugging. |
| D18 | Evaluation/debug runs aren't subject to the 24 h production GC. |
| D19 | Legacy engine and its characterization tests kept; legacy behaviour isn't rewritten to look cleaner. |
| D20 | Unsupported deployment paths marked clearly; no work making Vercel/Render valid. |
| D21 | Confirmed junk removed during cleanup; anything possibly containing evidence is checked first. |
| D22 | This plan lives at `docs/plan/master-engineering-plan.md`. |
| D23 | Both legacy comparisons kept: `legacy_v2@3` (historical) and `legacy_v2@5` (fair 5-clip comparison). |
| D24 | Fake 64-byte test output folder deleted (done in Phase 0). |

**Process rule:** one phase at a time: implement → test → measure → report → STOP for approval. Evidence contradicting a plan assumption is brought back before any architectural change. Dubbing/voice translation remains an extension point only.

**Implementation notes recorded during Phase 0** (don't change decisions):
- The evaluation harness lives in `backend/evaluation/` (not `eval/`), because it imports backend modules and `eval` reads like the Python builtin. Datasets: `backend/evaluation/datasets/<name>/<version>/`; promoted results: `backend/evaluation/results/`; media/cache/runs: `<repo>/eval_data/` (git-ignored, override `CLIPPODS_EVAL_DIR`).

## Evidence Log

Observations recorded as they are found. Each entry states its source and its limits. **These are evidence, not conclusions about real-world ASR or clip quality**; those require the frozen real dataset.

| ID | Phase | Observation | Source | Limits |
|---|---|---|---|---|
| EV-0.1 | 0 | Whisper (`base`, legacy config) reported a final segment ending at **127.92 s** in a **123.36 s** file. | Smoke run `20260914T112148-adhoc-unversioned-e98618`, local synthetic English TTS audio | One file, synthetic speech. Shows segment timestamps *can* exceed the audio; frequency on real content unknown. |
| EV-0.2 | 0 | **6 of 10** legacy_v2@5 clip boundaries (starts + ends) fell inside a Whisper segment (active speech per ASR). | Same smoke run | Measured against Whisper segments, not VAD or a reference aligner; clean TTS speech. |
| EV-0.3 | 0 | Whisper segments contained **two sentences** (≈ 6–9 s segments), so segment ends ≠ sentence ends. | Same smoke run | Synthetic speech with regular pauses; real conversational segmentation may differ. |
| EV-0.4 | 0 | In synthetic fixtures, Tamil clips scored 86–94 while English and Hindi saturated at the 98 cap. | `backend/tests/legacy/golden/*` | Fixture text is synthetic and repeated; a hint of language sensitivity in the density score, not proof. |
| EV-0.5 | 0 | `select_segments(..., collect_analysis=True)` (the mode the pipeline uses) raises `TypeError` on malformed segments; the existing test only covered `collect_analysis=False`. | `tests/legacy` fixture `malformed_entries_120s` | Real `transcribe()` output never contains these shapes; low practical impact. |
| EV-0.6 | 0 | Legacy ASR on the synthetic clip ran at RTF ≈ 0.05 with 328 MB peak RSS. | Smoke run `stages.json` | Clean TTS; **not** representative of real podcast latency. |
| EV-0.7 | 0 | Audio cache costs ≈ 115 MB per hour of media (16 kHz mono PCM). | Arithmetic, confirmed by smoke run file size | Planning estimate for dataset disk usage. |
| EV-1.1 | 1 | Legacy transcript (sha256 `d171aeff…`), legacy_v2@3/@5 selections, analysis traces and rendered clip durations were **identical** across: Microsoft Store Python (Phase 0), `.venv312` before Phase 1 code, and `.venv312` after Phase 1 code (`--no-cache` rebuilds). | Runs `…112148-e98618`, `…120634-8848b6`, `…121631-45378a` | One synthetic file; complements the 16 golden fixtures, which also pass. |
| EV-1.2 | 1 | The pytest-only synchronous route bypass reports a cancelled job as `error`; the real threaded worker reports `cancelled`. | `test_late_cancel_removes_rendered_clips_and_records_cancellation` | Test-harness divergence (P-REL-7), not a production bug. |
| EV-1.3 | 1 | `update_job` dropped **all** updates on cancelled jobs, so a cancelled run could never be linked to its analysis record. Fixed: `run_uuid` is still stored. | Same test | — |
| EV-1.4 | 1 | Real server run: transcription was 6.2 s of 7.3 s stage time; cancel during transcription stopped the job ~2 s after starting it (previously it ran to completion). | Local uvicorn run, smoke file | Short synthetic file; cancel latency scales with segment length, not file length. |
| EV-1.5 | 1 | faster-whisper's decoded audio duration (≈ 122 s, "2:02") is shorter than the container duration ffprobe reports (123.36 s). | Progress messages in the real server run | Relevant when clamping cut points to the audio end in boundary work. |
| EV-2.1 | ASR | A correctly transcribed final English sentence carried an end time 5 s past the audio and overlapped measured speech by only 28 %. Its text was real; only the timing was wrong. Led to a separate `timing_suspect` flag class instead of treating it as a hallucination. | Smoke file, `legacy` profile | One file. |
| EV-2.2 | ASR | faster-whisper's `avg_logprob`, `compression_ratio`, `no_speech_prob` and `temperature` are per ~30 s decode window and copied onto every segment in it (27 segments shared 5 value tuples). Segment-level confidence flags are coarse; word probabilities are the fine signal. | Smoke file, both profiles; confirmed in faster-whisper source | Structural property of the library. |
| EV-2.3 | ASR | **`base` never produced Devanagari for Hindi.** Clean studio Hindi read speech came out as Latin transliteration (`legacy` decode) or Urdu script (`rich_v1`, and forced `hi`). Language was detected correctly (p ≈ 0.98). A Devanagari `initial_prompt` made it worse (romanised output or "पूर। पूर। …" loops). `script_mismatch` flagged every segment. | IndicTTS Hindi read-speech clips (6, ~33 s speech) | Studio read speech, not podcasts; one speaker style. Script failure is consistent across every setting tried. |
| EV-2.4 | ASR | **Tamil failures on clean speech were a decoding-configuration problem, not model size.** Whisper's compression ratio is gzip over UTF-8 bytes; clean Tamil text scores 2.5–3.1 per ~30 s window (English 1.3, Hindi ≈ 2.2), above Whisper's 2.4 fallback trigger. Default decoding fell back to temperature 1.0: CER 0.33 → 0.76 between two identical runs (non-deterministic). With fallback disabled (`temperature=[0]`, no compression threshold), `base` reached CER 0.10–0.12, identical across runs, ~4× faster, 99 % speech coverage. | IndicTTS Tamil read-speech clips (6, ~38 s speech), `rich_v1` and `legacy` decodes | Clean read speech; disabling fallback also removes Whisper's escape from repetition loops (seen with the Hindi prompt test), so the right fix is script-aware, not "always off". |
| EV-2.5 | ASR | Mixed Hindi→English→Tamil file: language probes detected both `hi` and `ta` and marked the language uncertain. With `legacy` decode the Tamil portion was not transcribed at all (coverage 73 %); with `rich_v1` it was romanised. | Synthetic concatenation of the clips above + English TTS | Utterance-level switching, not real intra-sentence code-switching. |
| EV-2.6 | ASR | The `legacy` profile's `legacy_segments()` is byte-identical to the pre-Phase-1 reference transcript (sha256 `d171aeff…`), and legacy_v2 clips are unchanged, while it now also records language probes, speech regions and quality flags. | Smoke file | — |
| EV-2.7 | ASR exp. | **`large-v3` fixes Hindi script and sharply improves Tamil on clean read speech.** Hindi: Devanagari, CER 0.074 (base: Urdu/Latin script, CER ≥ 1.0). Tamil: CER 0.021 (base with the script-aware fix: 0.131; base default rich decode: 0.73–0.75; base legacy decode: 0.599). Both deterministic across repeats, auto and forced language identical. | `asr_model_compare` run `20260914T133519` | IndicTTS studio read speech, ~33–38 s each; not podcast audio. |
| EV-2.8 | ASR exp. | **`large-v3` hallucinates fluent sentences on the English TTS file**: CER 0.02–0.14 vs base 0.006, with inserted phrases that were never spoken ("we tried to solve the issue with the help of a few people", "okay so this was the first time I realized"), temperature fallback, run-to-run differences, and 12–33 zero-duration words. Only 0–1 segments were flagged: insertions inside real speech are invisible to VAD-overlap checks. | Same run, English smoke file (script looped twice, TTS) | Synthetic speech with an audio loop seam; real English podcast behaviour unmeasured. |
| EV-2.9 | ASR exp. | **Single-language decoding of the mixed file**: `large-v3` (decoded as `hi`) silently **dropped the 22 s English portion** and wrote the Tamil speech in **Devanagari** (coverage 0.59). `base` kept English but romanised/dropped Tamil. Only signal: language probes disagreed (`uncertain`). | Same run, mixed file | Utterance-level switching; real code-switching unmeasured. |
| EV-2.10 | ASR exp. | **Script-aware compression fix** (rich_v1): base Tamil CER 0.73–0.75 → 0.131, coverage 0.41–0.45 → 1.00, non-deterministic → deterministic, 4–5× faster. large-v3 Tamil CER 0.021–0.027 → 0.021, non-deterministic → deterministic, decode 396–426 s → 93 s. No effect on Hindi or English (no override applied); English differences between fixed/unfixed large-v3 runs are sampling noise. | Same run | Clean speech. |
| EV-2.11 | ASR exp. | **CPU cost**: base RTF 0.05–0.10, peak RSS 0.36–0.48 GB. large-v3 (int8, default CTranslate2 threads) RTF 1.5–2.7 (slower than real time), model load 5–6 s, RSS after load 1.6 GB, peak 5.0 GB; the worker averaged ~4 busy cores of 16. A 2 h podcast would take roughly 3–5 h at this RTF. `cpu_threads` / batched inference untested. | Same run; process sampling | Short files; long-file RTF and threading headroom unmeasured. |
| EV-2.12 | ASR exp. | Word timestamps: monotonic for all groups; base 97–100 % of words inside measured speech, large-v3 91–98 %. large-v3 produced zero-duration words only on the hallucinating English runs. | Same run | — |

Experiment record (EV-2.7–2.12): model `Systran/faster-whisper-large-v3`, revision
`edaa852ec7e145841d8ffdb056a99866b5f0a478`, 3,090,835,702 bytes (`model.bin`
3,087,284,237), stored in `C:\Users\maste\.cache\huggingface\hub\models--Systran--faster-whisper-large-v3`
(2.9 GiB on disk; files stored directly, Windows symlinks unavailable). Environment:
Python 3.12.10 (`.venv312`), Windows 11, Ryzen 7 5800X (16 logical CPUs), 31.9 GB RAM,
faster-whisper 1.2.1, ctranslate2 4.8.2, onnxruntime 1.29.0, numpy 2.5.3; CPU int8.
Reproduce: `python -m evaluation.experiments.asr_model_compare` then
`python -m evaluation.experiments.asr_model_compare_report <results.json>`.
Production defaults unchanged (`ASR_PROFILE=legacy`, both profiles on `base`).

### Real-world validation (9 owner-selected YouTube podcasts, 2026-09-14)

Material: 3 Tamil, 3 English, 3 Hindi-labelled videos (61–175 min); podcast-body
windows (3 × 5 min each, early/middle/late after a verified body start) plus
separately labelled pre-body/sponsor regions. rich_v1 path, word timestamps, VAD,
auto language. No references: judgements come from reading transcripts plus
reference-free metrics. Scripts: `evaluation/experiments/realworld_*.py`; data in
`eval_data/realworld/` (not in git).

| ID | Observation | Limits |
|---|---|---|
| EV-3.1 | **English podcasts: `base` is good.** Detection p ≥ 0.99, readable accurate text, 0–3 suspect segments per 5 min, coverage 0.80–0.99, RTF 0.07–0.10, peak RSS 0.44–0.54 GB. `large-v3` agreed on 94–95 % of words, fixed some names/phrases, but also dropped an 11-word clause base caught, added fillers and a repeated clause; RTF 1.4–1.9, peak 5.0 GB. | 3 English videos (base), 1 (large-v3). |
| EV-3.2 | **The rich_v1 script-aware compression fix (EV-2.10) causes catastrophic repetition loops on real Tamil and Hindi audio**, with both `base` and `large-v3` (e.g. "செல்லாம்," / "வருகிறது இன்னும் கொஞ்சம்" / "सब्सक्राइब" / "लुट लुट" for minutes; 90–100 % suspect segments, coverage 0–0.39). Clean read speech (EV-2.10) never showed this. **EV-2.10's conclusion does not hold for podcast audio.** | All Tamil/Hindi body windows tested. |
| EV-3.3 | Loop diagnostic on `large-v3` (ta1 & hi1 early body): **A** fix off → no loops but temperature fallback to 1.0 on most windows, word salad with foreign tokens, RTF 4.8–8.7; **B** fix on + `condition_on_previous_text=False` → readable, deterministic (all T=0), RTF 1.1–2.1, coverage 0.57 (ta) / 0.70 (hi), only a few contained loop bursts. `base` with B stays poor (ta coverage 0.13; hi2 0.34, romanised; hi1 decoded as English). | 2 windows (large-v3), 3 windows (base); 5 min each. |
| EV-3.4 | **Hindi-labelled podcasts are Hinglish.** `base` auto-detected `en` on hi1/hi3 (p 0.55–0.87, probes alternating hi/en) and produced **English text for Hindi speech (translation-like)**, even when it decoded as `hi` (hi1 late: "The recovery in your body automatically happens when you're sleeping", all segments `script_mismatch`). hi2 produced Urdu script, romanised Hindi or loops. No `base` Hindi window was in Devanagari. | 3 videos. |
| EV-3.5 | **`large-v3` + B on Hinglish produces the desired code-switched form**: Hindi in Devanagari, English in Latin ("So, जो birth place effect कहता है", "हर्याना में you will find lot of wrestlers coming out"). With the fix + conditioning it instead wrote English phonetically in Devanagari before looping. `large-v3` + B on Tamil kept Tanglish naturally ("good actor imageயே marketல் அடுத்த levelக்கு"). | 1 window each. |
| EV-3.6 | `script_mismatch` fires on correctly transcribed English inside Hindi/Tamil speech; it cannot distinguish code-switching from wrong-script output. `repeated_text` reliably catches the loops. | — |
| EV-3.7 | The "untranscribed speech" metric (VAD regions without words) under-reports failures during loops, because loop words carry timestamps spread across real speech; usable-segment coverage is the reliable signal. | Measurement limit. |
| EV-3.8 | Every video had pre-body material: highlight montages (28–160 s), subscribe/Spotify promos, narrated intros, title-sponsor reads (en3 154–191 s, hi1 179–234 s), music beds (non-speech level −15…−25 dB vs −40…−55 dB in conversation). `base` handled English intros and sponsor reads well; Tamil and hi2 intros looped over music. | Body starts for ta3/hi2 are estimates (chapters/SponsorBlock/audio level). |
| EV-3.9 | Word timestamps stayed monotonic everywhere. Zero-length words and >2 s words cluster in loop/fallback output (e.g. base hi2 late: 191 zero-length words; large-v3 ta1 late: 47 zero-length, 41 > 2 s); clean English has ≤ 16 zero-length and ≤ 5 long words per 5 min. Segments on en2 reach ~30 s. | — |
| EV-3.10 | Resources on real audio: `base` RTF 0.07–0.16, peak RSS 0.42–0.54 GB. `large-v3` RTF 1.1–3.0 (fixed decode), up to 8.7 with fallback; peak RSS 3.3–5.0 GB. | CPU int8, default threads. |

Synthetic fixtures are for **regression testing only**. All ASR, boundary and semantic-quality decisions must be validated on the frozen real dataset.

---

## 1. Executive Summary

ClipPods today is a working prototype that **reliably produces files but not reliably good clips**. The investigation confirmed almost every previously reported issue and found about 30 more.

The most important findings:

1. **Clip boundaries are not based on speech at all.** Starts are fixed 5-second grid points (5, 10, 15 s…). The end the scorer chose is **thrown away** and replaced with `start + 18 s`, nudged to the nearest Whisper segment end within +2 s. A final clamp can then cut the end to the next clip's start. None of these steps looks at audio. Mid-word starts and ends are expected by construction.
2. **"Interesting" means "dense transcript".** The ranking score is the *sum* of words-per-second over the Whisper segments in a window. The "energy filter" is transcript coverage, not acoustic energy. The "viral score" (75–98) is a cosmetic mapping of that density. Speaker-change scoring can never fire. Hindi's sentence terminator `।` is not recognised as a sentence end.
3. **The ASR is configured for the easiest case only.** It runs Faster-Whisper **`base`**, CPU/int8, beam 5, with no VAD, no word timestamps and no language hint. Language is auto-detected from the **first 30 seconds only**, then applied to the whole file. Detected language, confidence, `no_speech_prob`, `avg_logprob` and `compression_ratio` are all discarded. If the model fails to load, a **fake 30-second transcript** is used and the job still reports success.
4. **The debugger loses its data on every run on this Windows machine, not just for Indic text.** `analysis.json` is written with the platform default encoding (cp1252). The decision log always contains `→`/`≥`, so the write raises `UnicodeEncodeError` and leaves a **0-byte file**. The error is logged as a warning and swallowed. I reproduced this in the scratchpad.
5. **Long-form ingestion contradicts the product goal.** Uploads are capped at 100 MB, and Cloudflare's free tier also caps request bodies at 100 MB. A 1–2 hour podcast is typically well over 1 GB. URL downloads have no size or resolution cap at all.
6. **Several useful building blocks already exist locally:**
   - Faster-Whisper 1.2.1 ships Silero VAD (onnxruntime is installed), word timestamps, per-segment confidence fields and a batched pipeline. **VAD and word timing need no new dependency.**
   - **Qwen3.5-9B (Q4_K_M, 6.6 GB GGUF) is already pulled in Ollama.** Its bundled defaults (temperature 1.0, presence_penalty 1.5) are wrong for scoring and would have to be overridden.
   - Only the `base` Whisper model is cached. Any larger model is a download that needs your approval.
7. **The documented environment is not the one in use.** `.venv312` contains only `pip`. The dependencies live in the Microsoft Store Python 3.12 user site-packages, which the README advises against. The 105 existing tests pass there (7.8 s), but they lock in legacy behaviour (3 clips, identical duplicate clips for short videos) and bypass the real worker path.

**Recommended direction** (you decide at Checkpoint 2): make **audio (VAD) the temporal authority** and **words the semantic index**.
- Build variable-length candidates from *thought units* and cut only inside measured silence gaps.
- Rank with deterministic, per-video-normalised features first.
- Then add Qwen as a **judge of pre-computed candidates**. It never produces timestamps.
- Keep the legacy engine as a permanent baseline behind a versioned engine flag.
- Build an offline evaluation runner with stage caching *before* changing selection, so every step is measured.

Two things must be settled before implementation, because the plan depends on them:

- **(a)** Several decisions (ASR model size, Qwen viability) can't be made responsibly without measurements. That needs your approval to run **measurement-only spikes** before those checkpoints (Decision D2).
- **(b)** The exact-5 requirement needs an explicit fallback policy for videos too short to contain 5 distinct moments (Decision D9).

---

## 2. Current Architecture

### 2.1 Runtime topology (what actually runs)

```text
Browser (static/index.html, same origin)
   │  POST /process {video_url}      POST /process/upload (multipart)
   │  GET /status/{job_id} (poll)    POST /cancel/{job_id}   GET /clips/{name}
   ▼
Cloudflare Tunnel (api.theclippods.com → 127.0.0.1:8000, per README; 100 MB edge body limit)
   ▼
uvicorn + FastAPI (single process)  ── backend/main.py
   ├── StaticFiles "/" → static/ (landing UI + /dev-debugger/ bundle)
   ├── routers/video.py   → creates job in in-memory dict, submits to worker pool
   ├── routers/analysis.py → /dev/analysis/* (403 unless ENABLE_DEBUGGER=true)
   ├── GC daemon thread (hourly: temp >4h, outputs >24h deleted)
   └── JobWorkerPool: 2 daemon threads, queue.Queue(maxsize=20)
          └── each job: asyncio.run(_run_pipeline(...)) inside the worker thread
                ├── yt-dlp download (sync, in-thread)    or   saved upload (temp/<uuid>.<ext>)
                ├── ffprobe duration guard (≤ 2 h)
                ├── ffmpeg → 16 kHz mono PCM WAV (subprocess, cancellable)
                ├── Faster-Whisper "base" cpu/int8 (shared global model, NOT cancellable)
                ├── select_segments(max_clips=3)  → clips + analysis dict
                ├── ffmpeg libx264/aac re-encode per clip → outputs/<run_uuid>/<run_uuid>_clip_i.mp4
                └── write analysis.json (fails on Windows, see P-OBS-1) ; cleanup temp
```

### 2.2 Stage-by-stage (verified in code)

| Stage | File | What it really does |
|---|---|---|
| Routes | `backend/routers/video.py` | `POST /process` (JSON), `POST /process/upload`, `GET /status/{id}`, `POST /cancel/{id}`. `GET /clips/{name}`, `GET /health` in `main.py`. |
| Upload | `services/input_processing.py:174-241` | Extension whitelist, tolerant MIME check, 1 MB streamed chunks, 100 MB cap, 0-byte rejection. |
| YouTube | `services/input_processing.py:49-167` | yt-dlp `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best`, 30 s socket timeout, timeout/cancel only checked **inside progress hooks**. |
| Duration guard | `routers/video.py:89-98` | ffprobe; rejects > 7200 s (hard-coded, not in config). |
| Audio | `services/audio_extraction.py` | Probes again for an audio stream, extracts 16 kHz mono s16le WAV, 300 s timeout, registered for cancel. |
| ASR | `services/transcription.py` | `WhisperModel("base", device="cpu", compute_type="int8")`, `transcribe(audio, beam_size=5)`, returns only `{start,end,text}`. |
| Selection | `services/segment_selection.py` | 5 s-stride sliding windows, stop-point scoring, density ranking, uniform fallback, duplication, `start+18` end rewrite, overlap clamp. |
| Rendering | `services/clip_generation.py` | `-ss` input seek + libx264 (preset fast, default CRF) + AAC, 50 ms audio fades, volume 0.9. (Docstring says "stream-copy", which is wrong.) |
| Jobs | `backend/job_manager.py` | Global dict + lock; never evicted; queue position; ETA = 45 s × position. |
| Worker | `services/job_worker.py` | 2 threads; synchronous mode auto-enabled when `pytest` is imported; terminal-state safety net. |
| Cleanup | `utils.py` | Per-job temp cleanup (UUID-prefix sweep), GC by mtime. |
| Debugger | `services/analysis_collector.py`, `routers/analysis.py`, `dashboard/` | Trace of selection only; React/Vite app built to `static/dev-debugger`. |
| Config | `backend/config.py` | Env-var driven; **read before `.env` is loaded** (see P-REL-1). |

### 2.3 Environment actually present on this machine [CONFIRMED]

- CPU Ryzen 7 5800X, 32 GB RAM, **Radeon RX 580 2048SP** (treat as not usable for ML).
- `.venv312` → **only pip installed.** Working deps are in the MS Store Python 3.12.10 user site: faster-whisper 1.2.1, ctranslate2 4.8.2, onnxruntime 1.29.0, av 18.1.0, yt-dlp 2026.8.19, fastapi 0.137.2, starlette 1.6.0.
- FFmpeg 8.1.1 (winget). Ollama and LM Studio CLIs are installed; neither daemon was running.
- Hugging Face cache: only `models--Systran--faster-whisper-base`.
- Ollama: `qwen3.5:9b` → GGUF, family `qwen35`, 9.7B, **Q4_K_M**, 6.59 GB; params `temperature 1, top_k 20, top_p 0.95, presence_penalty 1.5`; requires Ollama ≥ 0.17.1.
- `backend/outputs/` was **empty**, so there were **no historical artifacts or debugger data to inspect**. The 24 h GC and the encoding bug together mean there probably never were any on this machine.

---

## 3. Confirmed Current Problems

IDs are referenced from later sections. Severity: **S1** breaks correctness or trust · **S2** degrades quality or reliability · **S3** hygiene.

### 3.1 Verification of the previously reported issues

| # | Reported issue | Verdict | Evidence / nuance |
|---|---|---|---|
| 1 | Fixed 5 s grid starts | **CONFIRMED** S1 | `MIN_START=5.0`, `STEP=5.0`; `t` advances by 5 s regardless of speech (`segment_selection.py:17-19, 366-514`). |
| 2 | Arbitrary clip starts | **CONFIRMED** S1 | The clip starts at grid time `ws`, never snapped. Segments are counted if their *midpoint* ≥ `ws`, so a clip routinely starts inside a segment. Nothing before 5.0 s is ever eligible, so a cold-open hook can't be selected. |
| 3 | Final ends overwritten after scoring | **CONFIRMED** S1 | The best-scored `we` is used for ranking and overlap checks, then replaced (`:638-653`). |
| 4 | `start + 18 s` behaviour | **CONFIRMED** S1 | `default_end = min(start+15+3, start+20, dur)`. `_align_end` returns the first punctuated segment end in `[start+18, start+20]`, else the last segment end in that range, else **exactly `start+18`** (mid-speech). An adjacent-clip clamp (`:672-679`) can then cut the end to the next clip's start. |
| 5 | No audio-aware boundaries | **CONFIRMED** S1 | After WAV extraction, audio is never analysed. All timing comes from Whisper segment timestamps. |
| 6 | No real VAD | **CONFIRMED** S2 | `vad_filter` defaults to `False` and isn't passed. **New:** Silero VAD is already bundled in installed faster-whisper 1.2.1. |
| 7 | No word timestamps | **CONFIRMED** S2 | `word_timestamps` defaults to `False`. |
| 8 | No forced alignment | **CONFIRMED** (probably not needed, see §13.4) | — |
| 9 | Simplistic sentence segmentation | **CONFIRMED** S2 | `text.endswith((".", "!", "?"))` on Whisper *segments*, which are not sentences. **New:** Hindi danda `।` (and `॥`) is never treated as a sentence end. |
| 10 | Speech-density ranking | **CONFIRMED** S1 | Score = **sum** of per-segment words/sec (`:394-397`), so it rewards windows that Whisper split into more segments. Viral score = `75 + min(4·score, 23)` (`:570`). |
| 11 | Language bias in word density | **MECHANISM CONFIRMED** S2 | Whitespace token count; agglutinative Tamil yields fewer "words"/s. Size of the effect [EXPERIMENT]. |
| 12 | Duplicate clip fallback | **CONFIRMED** S1 | `while len(selected) < max_clips: selected.append(dict(selected[-1]))` (`:613-615`). Videos ≤ 15 s get N identical `[0, dur]` clips (`:801-808`). A test asserts this. The debugger hard-codes `duplicated: False`, so **duplicates are invisible**. Uniform fallback windows ignore speech entirely. |
| 13 | Dead speaker-change logic | **CONFIRMED** S3 | No stage produces `speaker`, so the +2 is unreachable. The dashboard shows stop scores "/8" but the achievable maximum is 6. |
| 14 | Fake "energy" | **CONFIRMED** S2 | `ENERGY_RATIO_THRESHOLD` compares summed segment durations to window length. Segments extending outside the window can push the ratio above 1. |
| 15 | Silent/fake transcription fallback | **CONFIRMED** S1 | Load failure → stub segment `0–30 s` "[Transcription unavailable…]". The job **completes successfully**. The failure flag is cached for the life of the process. |
| 16 | Whisper hallucination on non-speech | **MECHANISM CONFIRMED** S1 | No VAD, no filtering on `no_speech_prob`/`avg_logprob`/`compression_ratio`, `condition_on_previous_text=True`. Hallucinated text counts as dense speech and can be *preferred* by the ranker. Rate [EXPERIMENT]. |
| 17 | Detected language discarded | **CONFIRMED** S1 | `segments_generator, _info = …` and `_info` is never used. Detection uses `language_detection_segments=1` (first 30 s) and applies one language to the whole file. |
| 18 | Debugger data loss on Windows | **CONFIRMED — worse than reported** S1 | `analysis_path.write_text(json.dumps(..., ensure_ascii=False))` without `encoding=` (`routers/video.py:174-176`). The locale encoding here is `cp1252` (UTF-8 mode off). Reproduced: `→`, Hindi and Tamil strings all raise `UnicodeEncodeError` and leave a 0-byte file. `→`/`≥` appear in every run's decision log, so **essentially every run fails**, not only Indic ones. The exception is swallowed and `run_uuid` is never stored on the job. `AnalysisCollector.save()` has the same bug (unused). |
| 19 | Concurrency around shared Whisper model | **PARTIAL** S2 | Model load is lock-protected and safe. Two workers share one `WhisperModel(num_workers=1)`, so concurrent transcriptions queue inside CTranslate2 rather than run in parallel [ASSUMPTION from faster-whisper docs; EXPERIMENT]. `cpu_threads=0` uses CTranslate2's default thread count, likely well below the 16 available [EXPERIMENT]. Not a crash risk; a throughput issue, and a future contention problem with a local LLM. |
| 20 | In-memory job state | **CONFIRMED** S2 | Lost on restart (polls get 404). Entries are never evicted. |
| 21 | Deployment mismatch | **CONFIRMED** S2 | See P-DEP-1…4. |
| 22 | Local-only storage | **CONFIRMED** (acceptable now) | — |
| 23 | Upload size limitations | **CONFIRMED** S1 for the product goal | 100 MB default and Cloudflare free-plan edge limit vs 1–2 h podcasts. |

### 3.2 Newly found problems

**Reliability / backend**

| ID | Sev | Problem | Evidence |
|---|---|---|---|
| P-REL-1 | S1 | **`.env` is ignored by config.** `main.py` imports `config` (and `services.job_worker`, which imports config) *before* `load_dotenv()`. `ENABLE_DEBUGGER` etc. from `.env` never take effect. | `main.py:18-22`, `config.py:19` |
| P-REL-2 | S1 | **Transcription is not cancellable and reports no progress.** Cancel marks the job but the worker keeps transcribing until done; progress sits at 60 %. Tolerable with `base`; with larger models it means many minutes of wasted CPU and a blocked slot. (Easy seam: the segment generator is lazy.) | `transcription.py:101-124`, `video.py:116` |
| P-REL-3 | S1 | **ASR errors are masked or leak.** Exceptions from `model.transcribe()` become "Audio not clear enough" (502). Exceptions raised *while iterating* the lazy generator (where decoding actually happens) are not wrapped. | `transcription.py:100-124` |
| P-REL-4 | S2 | **GC can delete a running job's source video.** Temp files older than 4 h (by mtime) are deleted hourly. A quality-first pipeline (large ASR + LLM on CPU, 2 h input) can plausibly run past 4 h [ASSUMPTION]. | `utils.py:112-123`, `config.py:59` |
| P-REL-5 | S2 | **Empty or silent transcripts produce "successful" jobs.** Music-only video → no segments → uniform fallback clips from arbitrary positions, with no flag to the user. | `segment_selection.py:598-617` |
| P-REL-6 | S2 | Services raise FastAPI `HTTPException` (with non-standard 499) as domain errors. Cancellation is detected by substring `"cancelled" in str(exc)`. | across services, `video.py:250,273` |
| P-REL-7 | S2 | Production code contains test hooks: MagicMock detection inside `audio_extraction.py:98-115` and `clip_generation.py:146-162`; a test-only event-loop branch in `_run_background_job`; auto-synchronous pool when `pytest` is imported. **The real worker path is not covered by tests.** | cited files |
| P-REL-8 | S3 | Upload jobs use status `processing`, which isn't in `cancellable_states` (brief window). | `video.py:357`, `job_manager.py:144` |
| P-REL-9 | S2 | yt-dlp timeout is enforced only inside progress hooks (a stall without callbacks never times out). No filesize/resolution cap (may download 4K multi-GB). Upload path is capped at 100 MB, URL path is not: an inconsistent policy. | `input_processing.py:85-144` |
| P-REL-10 | S3 | `asyncio.run()` per worker thread wraps code that is entirely synchronous; it adds complexity without concurrency. | `video.py:268` |
| P-REL-11 | S3 | Queue ETA hard-coded to 45 s per job; wrong by 1–2 orders of magnitude for podcasts. | `job_manager.py:101` |
| P-REL-12 | S3 | Max duration (2 h) hard-coded in the router, not config. Duration probed twice. | `video.py:95`, `audio_extraction.py:69` |
| P-REL-13 | S3 | `@app.on_event` deprecated (warnings in test run). | `main.py:69,80` |
| P-REL-14 | S2 | Cancel after clips are rendered but before completion leaves orphaned clip folders until GC. | `video.py:147-149` |

**Selection (additional)**

| ID | Sev | Problem |
|---|---|---|
| P-SEL-1 | S2 | "Dedup" keys on exact `(ws, we)`. `ws` is unique per step, so it is a no-op. With a 5 s stride and ≤ 20 s windows, neighbouring candidates overlap heavily and the greedy overlap filter decides what survives. |
| P-SEL-2 | S2 | Ties in stop score keep the **earliest** stopping point (strict `>`), biasing toward shorter clips. |
| P-SEL-3 | S3 | `_extend_end` is dead code. `BUFFER`/`PREF_*` constants are partly unused or overridden. |
| P-SEL-4 | S2 | Filler-word check is English-only and debugger-only (not used in scoring). |
| P-SEL-5 | S1 | `DEFAULT_NUM_CLIPS = 3`; router doesn't pass `max_clips`. Tests, docs, `.kiro` steering and landing-page copy all say 3. |
| P-SEL-6 | S2 | No diversity notion beyond non-overlap: two clips 21 s apart about the same point are both allowed. |

**ASR / language (additional)**

| ID | Sev | Problem |
|---|---|---|
| P-ASR-1 | S1 | No way to pass a language (API or config). Code-switching (`multilingual`) not enabled. |
| P-ASR-2 | S2 | Transcript *script* is never checked. If Tamil audio is detected as English, Whisper tends to emit English or romanised text [ASSUMPTION, well known; EXPERIMENT]. There is no Unicode-block check to catch this. |
| P-ASR-3 | S3 | The Faster-Whisper model name/size is not configurable. |

**Observability**

| ID | Sev | Problem |
|---|---|---|
| P-OBS-1 | S1 | analysis.json write failure (issue 18). |
| P-OBS-2 | S2 | analysis.json has **no ASR metadata, no audio/VAD info, no per-stage timings** (`processing_time_ms` covers selection only), no post-clamp reasons, no failure-run analysis (only written when clips exist). |
| P-OBS-3 | S2 | Misleading debugger fields: `transcript_preview` is the text of the first segment starting *after* `ws`, not the clip's text; `stats.unique_after_dedup` equals total candidates; duration histogram buckets hard-coded to 8–20 s; "/8" max score; `duplicated` always false. |
| P-OBS-4 | S2 | Output folders (and so debugger history and evaluation runs) are deleted after 24 h. |
| P-OBS-5 | S3 | `KEEP_ORIGINAL_FOR_DEBUG` copies the full source video (GBs for podcasts). |
| P-OBS-6 | S3 | `run_uuid` (hex) differs from `job_id` (dashed UUID); linking relies on a field that is never set on Windows (P-OBS-1). |

**Deployment / docs / repository hygiene**

| ID | Sev | Problem |
|---|---|---|
| P-DEP-1 | S2 | `vercel.json` routes omit `/status`, `/cancel`, `/dev`. Serverless can't host worker threads, FFmpeg or Whisper. `config.py` does `mkdir` at import. Vercel is effectively non-functional but still documented. |
| P-DEP-2 | S2 | `render-build.sh` puts ffmpeg in `./bin` but nothing adds it to `PATH`; no start command; ephemeral disk. |
| P-DEP-3 | S2 | README API table is wrong: documents `/api/process-url`, `/api/upload`, `/api/status`, `/api/analysis/{job_id}`. Real paths are `/process`, `/process/upload`, `/status`, `/cancel`, `/clips`, `/dev/analysis/{run_uuid}`. |
| P-DEP-4 | S2 | Docs claim: "Render (VPS)" deployment; "speaker changes" heuristic; energy filter; 20–25 s clips (`.kiro/steering/product.md`); "viral score based on … content quality"; stream-copy. None are true. |
| P-DEP-5 | S2 | No auth, `CORS *`, public tunnel; debugger bundle served at `/dev-debugger/` regardless of the flag (API still 403). Acceptable for local validation; a blocker for any public use. |
| P-DEP-6 | S3 | Tracked junk: `cloudflared_run.log` (tunnel ID, LAN and IPv6 addresses), `temp_chunk.wav`, root `__pycache__/segment_selection.cpython-311.pyc`, empty `segment_selection/`, `backend/services/test_select.py` (broken import), `SARVAM_API_KEY` in `.env.example`. |
| P-DEP-7 | S2 | Documented venv (`.venv312`) is empty; the app runs on a different interpreter. |
| P-TEST-1 | S2 | Tests encode legacy behaviour (3 clips, identical short-video clips), have misleading names (`test_ffmpeg_uses_stream_copy` checks libx264), and **write into the real `backend/outputs/`**. My read-only test run created `backend/outputs/7cc1c22523d5408aac33d6badf200503/` with three 64-byte fake clips. I tried to delete it and was blocked by the permission system, so it's still there. |

---

## 4. Root-Cause Analysis

The core diagnosis: **the pipeline throws away the signals needed to make good decisions, and then makes decisions with proxies.** Each category below states the root cause, not just the symptom.

### 4.1 ASR problems (accuracy: *what* was said)

| Symptom | Root cause(s) | Confidence |
|---|---|---|
| Poor Hindi/Tamil transcripts | (1) `base` model, which is small for low-resource languages; (2) one language guess from the first 30 s (intros are often music or English); (3) no explicit language option; (4) no VAD, so music/silence is fed to the decoder; (5) `condition_on_previous_text=True` lets errors and loops propagate. | Each mechanism CONFIRMED; relative contribution [EXPERIMENT]. The Phase 4 factorial experiment is designed to separate them. |
| English output for Tamil/Hindi speech | Wrong or forced language plus Whisper's translation tendency; no script validation. | [ASSUMPTION → EXPERIMENT] |
| Code-switched speech garbled | Single file-level language; `multilingual=False`. Also a genuine product question: what script should Hinglish/Tanglish be written in? | CONFIRMED config; quality [EXPERIMENT] |
| Hallucinated text in silence/music | No VAD; confidence fields discarded; no `hallucination_silence_threshold`. | CONFIRMED mechanism |
| Invisible failures | Stub fallback; masked exceptions; language info discarded. | CONFIRMED |

### 4.2 Timestamp problems (timing: *when* it was said)

- **Segment timestamps** come from Whisper's timestamp tokens (20 ms quantisation). In practice they are *decoder predictions*, not acoustic measurements: ends often run into trailing silence or stop early, and drift after long pauses or hallucinations [ASSUMPTION, widely observed; EXPERIMENT for magnitude on our content]. The current pipeline treats them as ground truth for clip ends.
- **Word timestamps** are available (faster-whisper aligns via cross-attention DTW) but unused. They are useful but imperfect. Expected failure modes: errors at segment edges; stretched words next to pauses; multi-token Indic words; hallucinated words get timestamps too [ASSUMPTION; EXPERIMENT].
- **Translated text has no acoustic alignment.** If the decoder emits English for Tamil audio, word times are attached to tokens that were never spoken. Enforcing *transcription in the source language* is a precondition for trustworthy word timing, not just a quality nicety.
- **VAD regions** are an independent acoustic signal. They don't know about words, but they reliably tell where speech energy starts and stops, which is exactly what a safe cut point needs.

### 4.3 Speech-boundary problems

Root cause: **four different concepts are collapsed into one** ("Whisper segment end"):

| Concept | Signal that should define it | Currently |
|---|---|---|
| Speech start/end | VAD onset/offset | not computed |
| Pause | gap between VAD regions or between words (≥ ~150–300 ms) | segment gap ≥ 0.8 s, debugger/stop-score only |
| Silence / non-speech | VAD non-speech ≥ longer threshold (may contain music) | not computed |
| Sentence boundary | terminal punctuation per language (`. ? ! ।` …) + pause | `endswith(. ! ?)` on segments |
| Thought boundary | sentence boundaries + discourse cues + semantic completeness | not modelled |

Cut placement is then done with fixed arithmetic (`grid`, `+18 s`, clamp) instead of choosing a *safe gap* at a *meaningful* boundary.

### 4.4 Candidate-generation problems

- Candidates come from time arithmetic (grid × window length), not from content units, so good moments that don't line up with a 5 s grid and an 8–20 s span can't be represented.
- The duration bound (8–20 s, effectively ≤ 20 s) prevents "complete thought" clips.
- There is no representation of boundary *variants* (end after sentence k vs k+1), which is exactly the choice needed for intentional open loops.

### 4.5 Semantic-selection problems

- There is **no semantic signal at all**. Word density is a proxy for talkativeness, not for hooks, controversy, questions or curiosity.
- The score is an unnormalised sum, so it depends on Whisper's segmentation granularity and on language morphology.
- No diversity or redundancy model. No notion of context dependency ("as he said…").
- The fallback optimises for *count* (always 3) over *meaning*, and hides that it did so.

### 4.6 Backend reliability problems

- Job lifecycle is split across the router (status transitions), worker pool (safety net), job_manager (cancel semantics) and services (HTTP exceptions). There is no single state machine.
- Long CPU stages (ASR, later LLM) have no cancellation, progress or time budget.
- Config loading order bug; GC policy not aware of running jobs.
- Test architecture forces test-only branches into production code.

### 4.7 Storage / deployment problems

- Single-process, local-disk, in-memory state is fine for validation, but documentation describes three deployment targets (Vercel, Render, tunnel) and only the tunnel is real.
- Ingestion limits (100 MB upload, Cloudflare edge) contradict the 1–2 h podcast use case.
- No retention policy distinguishes user output (short-lived) from evaluation/debug artifacts (must be kept).

### 4.8 Observability problems

- The debugger explains *selection arithmetic* only, and on Windows it doesn't persist at all.
- It can't answer "why this clip?" once ASR quality, VAD, boundary snapping or semantic scores matter, because none of those are recorded.
- Some fields are misleading (preview text, /8, duplicated=false), which is worse than missing.

---

## 5. Current Data Contracts

```text
POST /process {"video_url": str}           POST /process/upload  file=<UploadFile>
  → 202 {"job_id": "<uuid4 with dashes>"}   (503 {"error"} when queue full; 400/413 {"error"})

_run_pipeline(video_url | video_path, job_id)
  │
  ├─ get_video_input / save_uploaded_file  → Path  backend/temp/<uuid32hex>.<ext>
  ├─ ffmpeg.probe                          → video_duration: float   (≤ 7200)
  ├─ extract_audio(video_path, job_id)     → str   backend/temp/<uuid32hex>.wav  (16 kHz mono s16le)
  ├─ transcribe(audio_path)                → {"segments": [{"start": float, "end": float, "text": str}]}
  │        (language, language_probability, all_language_probs, duration_after_vad,
  │         avg_logprob, no_speech_prob, compression_ratio, temperature, tokens, words → DISCARDED)
  ├─ select_segments(segments, video_duration, max_clips=3, collect_analysis=True)
  │        → ([{"start": float, "end": float, "score": int(75..98)}] × 3,  analysis: dict)
  ├─ generate_clips(video_path, selected, job_id)
  │        → [abs path str]  backend/outputs/<run_uuid32hex>/<run_uuid>_clip_<i>.mp4
  ├─ analysis.json (meta, transcript, candidates, filtered_windows, decision_log, final_clips, stats)
  │        → backend/outputs/<run_uuid>/analysis.json   (0 bytes on Windows, P-OBS-1)
  └─ returns [{"filename": str, "score": int, "title": "Clip N", "duration": float}]

Job record (GET /status/{job_id}):
  {status, progress, message, elapsed_seconds, speed, eta, clips, error, run_uuid,
   queue_position, estimated_wait_seconds}
  status ∈ queued | downloading | processing | extracting_audio | transcribing |
           selecting_segments | generating_clips | completed | error | cancelled
```

Front-end coupling: `static/index.html` already renders any number of clips and ignores `score`. `dashboard/` reads `/dev/analysis/*` and assumes 8–20 s buckets, "/8" scores and the legacy field names.

---

## 6. Target Architecture

### 6.1 Principle

```text
Audio / code  = temporal authority   (where a cut may happen)
Words         = semantic index        (what is said between cuts)
Model         = semantic judgement    (which pre-validated span is worth posting)
Engine version + analysis artifact = every decision reproducible and explainable
```

### 6.2 Pipeline (target, engine `boundary_v1` / `boundary_v1+semantic`)

```text
Media ingest ──► AudioAsset (16 kHz WAV, duration, content hash)
                     │
                     ├──► SpeechRegions  (Silero VAD; speech/non-speech intervals; config+version)
                     │
                     └──► Transcript      (Faster-Whisper; language policy; words; confidence;
                                           quality flags: hallucination suspects, script mismatch)
                                 │
                                 ▼
                          Utterance/Sentence/ThoughtUnits  (words + punctuation + VAD gaps)
                                 │
                                 ▼
                          CutPoints  (safe gaps: position, gap length, boundary strength)
                                 │
                                 ▼
                          CandidateGenerator  (variable-length unit spans, boundary variants,
                                               duration policy, hard temporal validity checks)
                                 │
                                 ▼
                          FeatureScorer (deterministic, per-video normalised)
                                 │
                                 ├──► [optional] SemanticJudge (local LLM; scores candidate IDs;
                                 │                               picks among precomputed variants)
                                 ▼
                          Ranker + Diversity + Exact-5 policy (tiers, reasons)
                                 │
                                 ▼
                          RenderSpec[] ──► Renderer (FFmpeg)  ──► clips
                                 │
                                 ▼
                          analysis.json v2 (all of the above + timings + versions)
```

### 6.3 Component responsibilities

| Component | Owns | Must not |
|---|---|---|
| Ingest | download/upload, size/duration policy, content hash | know about ASR |
| AudioAsset | canonical WAV; loudness envelope (RMS) for features | — |
| SpeechRegions | VAD intervals, parameters, version | read text |
| Transcription | model/language/VAD config, words, confidence, language info, quality flags, progress & cancellation | select clips; silently stub |
| Units | sentence & thought-unit construction per language | move timestamps outside VAD/word evidence |
| CutPoints | the **only** place cut times are created | use LLM output |
| CandidateGenerator | spans of units, boundary variants, duration policy, validity | rank by semantics |
| FeatureScorer | deterministic features (§14.3) | call a model |
| SemanticJudge | scores/labels for candidate IDs; variant choice by ID | emit or edit timestamps |
| Ranker | combine scores, diversity, exact-5 tiers, reasons | re-cut |
| Renderer | exact cut from RenderSpec, fades, encoding | decide boundaries |
| Engine registry | `legacy_v2`, `boundary_v1`, `boundary_v1+semantic` | — |
| AnalysisWriter | UTF-8, atomic write, schema version, all stages, failure runs too | swallow errors silently |
| Eval runner (offline) | run engines on a frozen dataset with stage caching, compute metrics, blind A/B packets | ship in the API path |

### 6.4 Target internal contracts (proposal for review, not final)

```jsonc
// Transcript (per run)
{
  "asr": {"engine": "faster-whisper", "version": "1.2.1", "model": "large-v3", "compute_type": "int8",
          "beam_size": 5, "language_mode": "auto|forced", "language_forced": null,
          "vad": {"enabled": true, "params": {...}}, "word_timestamps": true,
          "condition_on_previous_text": false, "config_hash": "…"},
  "info": {"language": "ta", "language_probability": 0.93,
           "top_languages": [["ta",0.93],["en",0.04],["hi",0.01]],
           "duration": 5412.3, "duration_after_vad": 4630.1},
  "segments": [{
     "id": 12, "start": 61.84, "end": 66.20, "text": "…",
     "avg_logprob": -0.31, "no_speech_prob": 0.02, "compression_ratio": 1.4, "temperature": 0.0,
     "words": [{"w": "…", "start": 61.84, "end": 62.10, "p": 0.91}],
     "flags": ["script_mismatch" | "low_confidence" | "outside_vad" | "repetition"]
  }],
  "quality": {"flagged_segment_ratio": 0.03, "script_consistency": 0.98, "status": "ok|degraded|failed"}
}

// SpeechRegions
{"vad": "silero (faster-whisper bundled)", "params": {...}, "regions": [[0.42, 5.87], …]}

// Unit (sentence / thought)
{"id": 88, "kind": "sentence|thought", "word_range": [1203, 1231], "start": 612.4, "end": 619.9,
 "terminal": "." | "?" | "!" | "।" | null, "gap_after_ms": 640, "text": "…"}

// Candidate
{"id": "c041", "unit_range": [88, 95], "cut_in": 612.18, "cut_out": 671.05,
 "cut_in_gap_ms": 420, "cut_out_gap_ms": 640, "duration": 58.9,
 "variants": [{"vid": "c041.v0", "unit_end": 93, "cut_out": 655.2}, {"vid": "c041.v1", …}],
 "features": {"speech_ratio": 0.91, "loudness_z": 1.4, "rate_z": 0.8, "question_count": 2,
              "asr_conf": -0.28, "context_ref_start": false, "filler_start": false, …},
 "validity": {"starts_in_gap": true, "ends_in_gap": true, "hallucination_overlap": 0.0}}

// SemanticJudgement (model output, validated against JSON schema)
{"candidate_id": "c041", "variant_id": "c041.v1",
 "scores": {"hook": 8, "energy": 6, "controversy": 3, "question": 7, "curiosity": 8,
            "payoff": 5, "standalone_context": 7, "coherence": 8},
 "ending_type": "resolved|intentional_open_loop|truncated",
 "context_dependency": "none|mild|severe", "topic": "…", "rationale": "≤ 30 words"}

// Selection
{"engine": "boundary_v1+semantic", "engine_version": "…",
 "clips": [{"rank": 1, "candidate_id": "c041", "variant_id": "c041.v1", "tier": 1,
            "final_score": 0.83, "score_breakdown": {...}, "reasons": ["…"]}],
 "fallback": {"tiers_used": [1,1,1,2,2], "notes": ["…"]}}
```

---

## 7. Architecture Options

All three options share the non-negotiables: local-only, VAD/code own time, legacy baseline kept, exact-5 policy, engine versioning, offline evaluation.

### Option A — Boundary-first deterministic pipeline + LLM re-ranker

**Flow:** ASR (words + VAD) → thought units → safe cut points → *exhaustive* variable-length candidates → deterministic features → top-K (e.g. 30–60) → Qwen scores each candidate (and picks one of 2–3 precomputed ending variants) → final ranking + diversity + exact-5.

- ✅ Cleanest separation; the model sees short texts, so cost scales with K, not video length.
- ✅ Easiest to evaluate incrementally (deterministic first, then + model).
- ✅ Works without the model (fallback = deterministic ranking, visibly flagged).
- ❌ **Recall risk:** if deterministic features don't put a semantically great but acoustically calm moment into the top-K, the model never sees it.
- Cost [ASSUMPTION]: K × (~300–800 prompt tokens) + small JSON outputs; CPU minutes, not hours.

### Option B — LLM-first moment discovery over the whole transcript

**Flow:** ASR → units with IDs → transcript chunked (~3–5 min windows with overlap) → Qwen proposes highlight *unit-ID ranges* per chunk with labels → code snaps to cut points and validates → global re-rank → exact-5.

- ✅ Best potential semantic recall (the model reads everything, can find setups and payoffs).
- ✅ Timestamps still owned by code (model returns unit IDs only).
- ❌ Highest cost on CPU: a 2 h podcast ≈ 20–30 k English tokens, and Hindi/Tamil can be several times more tokens per word [ASSUMPTION; EXPERIMENT]. Prefill alone may take tens of minutes to hours on a 5800X.
- ❌ Less deterministic; chunk-boundary artefacts; range proposals are harder to validate and debug; weak without the model.
- ❌ Harder to attribute improvements (ASR vs model vs snapping).

### Option C — Hybrid two-pass (A + cheap semantic recall pass)

**Flow:** Option A, plus a coarse pass where each ~1–2 min region (unit-aligned) gets a short "interest map" score (hook/controversy/question/story present?) from the LLM or a smaller model. That map is one more feature steering candidate generation, then the fine judge runs on top-K as in A.

- ✅ Addresses A's recall risk at a fraction of B's cost (short outputs, can be batched).
- ✅ Still keeps temporal authority in code; still degrades gracefully.
- ❌ More moving parts; two prompts to maintain; more evaluation work.
- ❌ Coarse pass cost still grows with video length (lower than B).

### Comparison

| Criterion | A | B | C |
|---|---|---|---|
| Boundary quality | High | High (if snapping is good) | High |
| Semantic recall | Medium (feature-limited) | High | Medium-high |
| CPU cost (2 h podcast) | Low–medium | High | Medium |
| Works without LLM | Yes | Poorly | Yes |
| Debuggability | High | Medium | Medium-high |
| Incremental measurability | High | Low | High (built on A) |
| Indic token-cost sensitivity | Low | High | Medium |
| Implementation risk | Low | High | Medium |

---

## 8. Recommended Architecture

**Recommend: Option A now, designed so Option C can be added only if evaluation shows a recall gap.**

Reasoning:
1. The dominant current defects are temporal and structural (grid, `+18 s`, no VAD, discarded metadata). Option A fixes all of them without any model and gives a measurable new baseline.
2. CPU-only inference makes B's whole-transcript reading expensive, and it's disproportionately expensive for Tamil/Hindi, the languages you care most about.
3. The "is A missing good moments?" question is answerable with data: **candidate recall@K against human-marked moments** in the evaluation set. If recall@K is low, add C's coarse pass (a contained change: one extra feature).
4. Option A keeps "Model = semantic judgement, Code = temporal authority" absolute: the model chooses among candidate IDs and precomputed variant IDs.

**Not implemented. Awaiting Checkpoint 2.**

---

## 9. Human Decision Points

| ID | Checkpoint | Decision | Options | My recommendation |
|---|---|---|---|---|
| D1 | CP2 | Architecture | A / B / C | A, with C as a data-triggered extension |
| D2 | before CP3 & CP6 | Allow **measurement-only spikes** (scripts outside the production path, plus model downloads) before approving ASR/model configs? | yes, each spike approved individually / no | Yes. Otherwise CP3/CP6 are guesses. Each spike lists what it downloads and runs. |
| D3 | CP3 | Language UX | auto only / explicit `en|hi|ta|auto` selector (default auto) / explicit required | Explicit selector with `auto` default, plus a low-confidence warning |
| D4 | CP3 | Script for code-switched speech | native script with embedded English words / romanised / whatever ASR emits | Decide after seeing samples from the spike. Affects subtitles and future dubbing. |
| D5 | CP3 | ASR model & latency ceiling | base / small / medium / large-v3 / large-v3-turbo (+ optional Indic-specific model experiment) | Decide from data. Also set a max acceptable processing time for a 2 h podcast. |
| D6 | CP3/CP4 | VAD parameters & padding | defaults / tuned | Tuned from the boundary evaluation |
| D7 | CP4 | Duration policy | e.g. min 15 s, target 25–60 s, hard max 90 s | Proposal in §14.2; needs your product call |
| D8 | CP4 | Open-loop policy | allowed ending types and how they are proved | §14.5 |
| D9 | CP4/CP5 | Exact-5 fallback & very short inputs | tiered relaxation; overlapping-but-distinct windows for short videos; minimum input length | §14.6. The short-video case is a conflict you must rule on. |
| D10 | CP5 | What the user sees as a score | hide / real normalised score / tier label | Hide or tier label until the score is validated. The current 75–98 "viral score" is cosmetic. |
| D11 | CP6 | Local model & runtime | Qwen3.5-9B via Ollama / smaller variant / llama.cpp server | Decide from spike data |
| D12 | CP6 | Thinking mode | off / capped budget / on | Off unless the spike shows a clear quality gain worth the latency |
| D13 | CP8 | Worker concurrency during experiments | 2 / 1 | 1 (CPU contention between ASR and LLM) |
| D14 | CP2 | Long-form ingestion | raise upload limit (local only) / local-file ingest for eval / chunked upload later | Offline eval runner reads local files; raise limit for local use; public upload path later |
| D15 | CP7 | Dataset composition, raters, success thresholds | §10 | Proposal in §10 |
| D16 | CP7 | Where the dataset & eval artifacts live | in repo (manifests only) + media outside git / other | Manifests + labels in git, media outside git (copyright) |
| D17 | CP5 | How engines are selected | env var only / env var + debug-only API param | Env default + dev-only override param |
| D18 | CP8 | Retention | keep 24 h GC / exempt eval & debug runs | Exempt `eval/` runs; configurable output retention |
| D19 | CP8 | Legacy tests | keep as legacy golden tests / rewrite | Keep as `legacy_v2` characterisation tests; new tests for new engines |
| D20 | CP8 | Dead deployment artefacts (`vercel.json`, `render-build.sh`) | delete / mark unsupported / fix | Mark unsupported now, delete later |
| D21 | CP8 | Repo junk (`cloudflared_run.log`, `temp_chunk.wav`, stray pyc, `test_select.py`, empty dir) | remove / keep | Remove; consider whether the log's tunnel ID/IPs need rotation |
| D22 | CP1 | Where this plan lives | stays out of repo / `docs/plan/` | Your call |
| D23 | CP4 | Legacy engine clip count in comparisons | 3 (true legacy) / 5 (fair count) | Both: `legacy_v2@3` as historical, `legacy_v2@5` for fair A/B |
| D24 | CP8 | The fake 64-byte clip folder my test run left in `backend/outputs/` | delete / leave | Delete (git-ignored; created by me) |

---

## 10. Evaluation Strategy

### 10.1 Frozen dataset `clippods-eval-v1` (proposal)

Target: **14–16 videos**, versioned manifest, media stored outside git.

| Slot | Language | Length | Character |
|---|---|---|---|
| 1–2 | English | 5–15 min | high-energy / low-energy |
| 3–4 | English | 60–120 min | 2–3 speaker podcast; interview |
| 5–6 | Hindi | 10–20 min + 60–120 min | podcast; monologue |
| 7–8 | Tamil | 10–20 min + 60–120 min | podcast; monologue |
| 9 | Hinglish (code-switched) | 20–60 min | conversational |
| 10 | Tanglish (code-switched) | 20–60 min | conversational |
| 11 | any | any | music/silence-heavy (intro music, breaks) |
| 12 | any | any | difficult audio (remote call, echo, noise) |
| 13 | any | any | multi-speaker panel, cross-talk |
| 14 | any | < 3 min | very short input (exact-5 stress) |
| 15–16 | spare | — | failure cases found during development |

**Manifest** (`backend/evaluation/datasets/clippods-eval/v1/manifest.json`): id, source (URL/local), sha256 of media, duration, language(s), speakers, audio condition, why included, licence/consent note, date frozen. Changing the set → `v2`, never edit `v1`.

**Human labels (per video):**
- **Gold transcript excerpts**: 3–5 random 2–3 min windows (≈ 10–15 min of audio per video) for WER/CER. Full gold transcripts for 2 h podcasts are not realistic.
- **Gold moments**: you mark 5–10 moments you'd post (start, end, type: hook / controversy / question / story / open loop), plus 1–3 "must-not" regions (ads, intros).
- **Boundary spot labels**: for ~30 sampled cut points per system, a quick check of clean / mid-word / mid-sentence / truncated.
- **Language labels**: dominant language and code-switch regions.

**Statistical honesty:** ~15 videos × 5 clips = 75 clips per system. Report paired win rates with bootstrap 95 % CIs over videos (not clips), and per-language breakdowns (n = 2–3 each: *directional only*). One rater (you) risks bias; if a second rater is possible for a subset, compute agreement (Cohen's κ).

### 10.2 Automatic metrics

**ASR**

| Metric | Definition |
|---|---|
| WER (en), CER (hi, ta, code-switched) | vs gold excerpts after normalisation (Indic text → CER, since word segmentation makes WER harsh) |
| Language-ID accuracy | detected vs labelled dominant language; per-chunk accuracy on code-switched files |
| Script consistency | % of characters in the expected Unicode block(s) (Devanagari U+0900–097F, Tamil U+0B80–0BFF, Latin) |
| Hallucination rate | % of transcript words lying outside VAD speech, + repeated n-gram loops, + `compression_ratio > 2.4` |
| Coverage | VAD speech seconds covered by transcript words / total VAD speech |
| ASR RTF & peak RSS | wall time / audio duration; memory |

**Boundaries** (to avoid circular evaluation, the *reference* silence map uses a different detector from the one used for cutting, e.g. FFmpeg `silencedetect` with a fixed dB threshold, plus a second-config VAD; human spot labels arbitrate):

| Metric | Definition |
|---|---|
| Mid-word cut rate | cut point falls inside a word interval of a *reference* transcript (large model, word timestamps) **or** inside reference speech with no ≥ 120 ms gap within ±60 ms |
| Mid-sentence start/end rate | start not at sentence start / end not at sentence terminal (language-aware) |
| Truncated-ending rate | human spot label or LLM label `truncated` (the latter reported separately, never as the only evidence) |
| Leading/trailing silence | seconds of non-speech inside the clip at each edge |
| Start-at-speech-onset | cut_in within [−400 ms, 0] of a reference speech onset |

**Selection**

| Metric | Definition |
|---|---|
| Candidate recall@K | fraction of gold moments with IoU ≥ 0.5 (or ≥ 50 % coverage) against any of top-K candidates |
| Final precision@5 | fraction of the 5 clips matching a gold moment |
| Must-not hit rate | clips overlapping must-not regions |
| Duplicate rate | identical or ≥ 80 % temporal-overlap pairs among the 5 |
| Overlap rate | any temporal overlap among the 5 |
| Semantic redundancy | max pairwise text similarity (char 3-gram Jaccard, script-agnostic); optional embedding similarity later |
| Topic diversity | distinct topic labels among the 5 (LLM label or clustering) |
| #1→#5 degradation | final score and human rating slope by rank |
| Fallback tier distribution | count of clips per tier; % of videos needing tier ≥ 3 |
| Duration distribution | histogram per system |
| Cost | wall time per stage, total, peak RSS (API process + Ollama), CPU %, tokens in/out |

### 10.3 Human evaluation

**Per clip, Likert 1–5:** natural start · natural end · complete thought · standalone context (reverse of context dependency) · hook strength · curiosity · energy · "would I post this?"
**Ending classification:** resolved / intentional open loop / truncated.
**Blind pairwise A/B:**
- *Set-level*: two sets of 5 clips for the same video, order randomised, engine names hidden → "which set would you rather post?" plus reason tags.
- *Slot-level*: clip k from A vs best-matching clip from B.
- Packets generated by the eval runner: random IDs, key file kept separately, answers recorded in CSV/JSON.

### 10.4 Comparisons (each change measured against its predecessor)

```text
E0  legacy_v2@3 on legacy ASR (base)             ← historical truth of today
E1  legacy_v2@5 on legacy ASR                    ← fair count
E2  legacy_v2@5 on new ASR                        ← isolates ASR gains
E3  boundary_v1 (deterministic) on new ASR        ← isolates boundary+selection gains
E4  boundary_v1+semantic on new ASR               ← isolates model gains
```

### 10.5 Success criteria (proposal, for approval at CP7)

| Transition | Must hold | Target |
|---|---|---|
| New ASR vs base | No language gets worse CER/WER; hallucination rate falls | CER/WER relative improvement ≥ 20 % on hi & ta; language-ID correct on all non-code-switched files |
| E3 vs E2 | Mid-word cut rate ≤ 2 %; truncated endings ≤ 5 %; 0 duplicates; 0 overlaps (except approved short-video rule) | Set-level human preference ≥ 65 % wins (ties excluded), CI lower bound > 50 % |
| E4 vs E3 | No regression on boundary metrics; JSON validity ≥ 99 % after retries | Preference ≥ 60 %; hook & curiosity mean +0.5; precision@5 up |
| Cost | Recorded for every run | Within the latency ceiling you set in D5/D11 |

---

## 11. Phased Implementation Plan

Rules for every phase: branch per phase, small commits, tests green, eval where relevant, before/after table, list of regressions, **STOP for approval**. If a phase invalidates an approved assumption, stop and report; don't redesign silently.

Checkpoint mapping: CP1 = this document. CP2 → Phase 0–2 may start. CP3 after Phase 4 data. CP4/CP5 before Phases 5–6. CP6 after Phase 7 data. CP7 before Phase 2's labelling is frozen. CP8 governs everything.

### Phase 0 — Safety net & measurement harness
- **Goal:** be able to measure before changing anything.
- **Files:** new `backend/evaluation/` (runner, metrics, cache), new `backend/tests/legacy/` characterisation tests (freeze current `select_segments` output on fixture transcripts as golden files), `pytest` config to isolate `OUTPUTS_DIR`/`TEMP_DIR` in tests.
- **Deps:** none new.
- **Expected behaviour:** production unchanged. `python -m eval.run --engine legacy_v2 --dataset v1` runs stages on local files with a content-hash stage cache (audio, transcript, VAD, candidates), so selection experiments don't re-transcribe 2 h files.
- **Tests:** golden tests pass on current code; tests no longer write into real `outputs/`.
- **Eval:** none yet (harness smoke test on one short local file).
- **Rollback:** delete new folders; no production code touched.
- **Gate:** you review the harness output format.

### Phase 1 — Backend correctness fixes that don't change clip selection
- **Goal:** trustworthy failures and artefacts.
- **Items:** UTF-8 atomic analysis write (P-OBS-1); `.env` load order (P-REL-1); stub transcription → explicit job error (issue 15); wrap errors raised during segment iteration, keep the real message (P-REL-3); cancellation + progress during transcription by checking between segments (P-REL-2); `processing` cancellable (P-REL-8); GC skips files belonging to active jobs (P-REL-4); job record eviction TTL; record per-stage timings; write analysis for failed runs too; README API table correction (P-DEP-3) *only for facts already true*.
- **Files:** `main.py`, `config.py`, `routers/video.py`, `services/transcription.py`, `job_manager.py`, `utils.py`, `README.md`.
- **Tests:** new unit tests per item (encoding with `→`/Hindi/Tamil on Windows; `.env` respected; cancel mid-transcription; GC active-file exemption).
- **Eval:** E0 must be byte-identical in clip times to pre-phase (proves no selection change).
- **Rollback:** revert branch.
- **Gate:** approval before Phase 2.

### Phase 2 — Dataset assembly & baseline measurement (mostly human work)
- **Goal:** frozen `v1` + E0/E1 numbers.
- **Work:** you pick videos (I propose candidates if you want, but you choose); runner computes automatic metrics; you label gold moments and excerpts; blind packets for E0 vs E1 as a dry run of the A/B tooling.
- **Files:** `backend/evaluation/datasets/clippods-eval/v1/manifest.json`, `…/v1/labels/` (media outside git).
- **Gate:** **CP7** (what "better" means) approved and dataset frozen.

### Phase 3 — Rich transcription contract (same model)
- **Goal:** stop discarding information, without changing quality variables.
- **Items:** Transcript contract of §6.4 with `base` unchanged, word timestamps on, language info kept, quality flags computed; `select_segments` adapted to read `segments` only (legacy unchanged); analysis v2 adds ASR section; config for model/language (defaults = current behaviour).
- **Note:** enabling `word_timestamps` changes decoding slightly [ASSUMPTION], so E0 is re-run and any drift reported.
- **Tests:** contract schema tests; flags on synthetic cases.
- **Eval:** ASR metrics for `base` = the ASR baseline.
- **Rollback:** config flag `ASR_RICH_CONTRACT=false`.
- **Gate:** approval.

### Phase 4 — ASR experiment matrix (measurement spike, needs D2) → **CP3**
- **Goal:** choose model / language mode / VAD / decoding settings from data.
- **Downloads (approval needed):** e.g. `small`, `medium`, `large-v3`, `large-v3-turbo` CTranslate2 weights (≈ 0.5–3 GB each). Optional later spike: an Indic-specialised open model (e.g. AI4Bharat IndicConformer / IndicWhisper fine-tunes), only if Whisper large-v3 is inadequate on Tamil, because those pull in torch/NeMo.
- **Matrix:** model × {auto, auto with `language_detection_segments`>1 on VAD speech, forced} × {VAD off, VAD default, VAD tuned} × {`condition_on_previous_text` on/off} on the gold excerpts plus full-length timing on two long files. Also batched vs sequential inference and `cpu_threads` 8/16.
- **Output:** per-language CER/WER, language-ID, script consistency, hallucination, RTF, RSS, and 10 listened examples per language.
- **Gate:** **CP3** decision (D3–D6).

### Phase 5 — Speech regions, units, cut points (deterministic, no selection change yet)
- **Goal:** the temporal authority exists and is measured.
- **Files:** new `services/speech_regions.py`, `services/units.py`, `services/cut_points.py`; analysis v2 sections.
- **Expected behaviour:** computed and recorded for every run. Legacy selection is still used for output. Eval also reports "what if legacy clips were snapped to the nearest safe cut" as a diagnostic (not shipped).
- **Tests:** per-language punctuation (`।`, `?`, Tamil), gap logic, word-outside-VAD handling, synthetic audio with known silences.
- **Eval:** boundary metrics on reference silence maps; unit length distributions per language.
- **Gate:** **CP4** boundary policy (D6–D8) approved with these numbers.

### Phase 6 — `boundary_v1` deterministic engine behind the engine flag
- **Goal:** new deterministic baseline with exact-5 policy.
- **Files:** `services/selection/engines/legacy_v2.py` (move, unchanged, golden tests), `…/boundary_v1.py`, `…/features.py`, `…/ranker.py`, `…/exact_five.py`; engine registry; `CLIP_COUNT=5`; renderer takes RenderSpec.
- **Tests:** validity invariants (every cut in a gap, no duplicates, no overlaps except approved rule, exactly 5); property tests on random transcripts; legacy goldens still pass.
- **Eval:** E2 vs E3 automatic and blind human.
- **Rollback:** `SELECTION_ENGINE=legacy_v2`.
- **Gate:** **CP5** confirmed with data; approval to proceed to the model.

### Phase 7 — Semantic judge spike (offline only, needs D2) → **CP6**
- **Goal:** know whether Qwen3.5-9B helps, at what cost.
- **Work:** run Ollama locally on cached `boundary_v1` candidates from the dataset; no API integration. Compare prompt designs (per-candidate vs batch of 5–8, pairwise tournament for top-10), thinking off vs capped, 9B vs one smaller variant.
- **Measure:** RAM (Ollama RSS), prefill/generation tok/s, per-video latency, JSON schema validity, run-to-run stability (same inputs twice), agreement with your gold moments & Likert ratings, per-language behaviour, tokens per Hindi/Tamil word.
- **Gate:** **CP6** (D11–D12).

### Phase 8 — `boundary_v1+semantic` integration
- **Goal:** model in the pipeline, isolated.
- **Files:** `services/semantic/judge.py` (interface + Ollama client + null judge), prompt files versioned, worker config (single heavy-inference slot), analysis v2 semantic section, debugger updates.
- **Behaviour:** model unavailable or invalid output → deterministic ranking with `semantic_status=failed` visible in job + analysis (never silent).
- **Tests:** schema validation, timeouts, retries, cancel during inference, no-timestamp-from-model invariant.
- **Eval:** E3 vs E4.
- **Rollback:** `SELECTION_ENGINE=boundary_v1`.
- **Gate:** approval.

### Phase 9 — Debugger v2
- Can be interleaved: each earlier phase adds its section; this phase does the UI. Tabs: ASR (language, confidence, flags), Audio/VAD timeline, Units & cut points, Candidates (features, variants), Semantic (scores, rationale), Selection (tiers, reasons, fallback), Timings/cost, Engine diff view (same video, two engines).
- Gate: approval.

### Phase 10 — Documentation reconciliation & repo hygiene
- README/TEAM docs/contracts/.kiro rewritten to match code; remove or mark unsupported deployment files (D20); junk removal (D21); `.env.example` cleanup; environment instructions matching the actual venv.
- Gate: approval.

### Phase 11 — Legacy retirement decision (not scheduled)
- Only after ≥ 2 evaluation rounds show `legacy_v2` is never preferred and adds no diagnostic value. Your decision.

---

## 12. Backend Cleanup Plan (non-AI)

| Item | Problem IDs | Phase |
|---|---|---|
| UTF-8, atomic (`tmp` + rename) analysis write; write failure runs; surface write errors in job | 18, P-OBS-1/2 | 1 |
| Load `.env` before importing config (or read env lazily) | P-REL-1 | 1 |
| Remove stub transcript; explicit `error` with actionable message | 15 | 1 |
| Transcription: keep underlying error, wrap iteration, progress from `segment.end / info.duration`, cancel between segments | P-REL-2/3 | 1 |
| Single job state machine (allowed transitions table), domain exceptions instead of `HTTPException` in services, typed cancellation exception | P-REL-6/8 | 1 (state table), 6 (exceptions refactor, as touched) |
| Remove MagicMock detection from production code; tests mock at subprocess boundary; one test that runs the real threaded worker | P-REL-7 | 1–2 |
| Drop `asyncio.run` wrapper in worker, or justify it | P-REL-10 | 1 |
| GC: never delete files of active jobs; separate retention for outputs vs eval/debug runs; configurable | P-REL-4, P-OBS-4 | 1 |
| Job store TTL eviction; restart behaviour documented (jobs lost, UI shows "server restarted") | issue 20 | 1 |
| Ingest policy: max duration & size in config; yt-dlp format cap (e.g. ≤ 1080p or audio+low-res video), wall-clock timeout via watchdog; consistent limits for upload and URL | P-REL-9/12 | 1 |
| Long-form ingestion for local validation: eval runner reads local files; configurable upload limit for localhost; document Cloudflare 100 MB limit | issue 23, D14 | 0–1 |
| Queue ETA from measured RTF, or remove | P-REL-11 | 6 |
| Lifespan handler instead of `on_event` | P-REL-13 | 1 |
| Orphan clip cleanup on late cancel | P-REL-14 | 1 |
| Worker concurrency config for heavy inference (single slot) | issue 19, D13 | 8 |
| Tests isolated from real `outputs/`/`temp/` | P-TEST-1 | 0 |
| `KEEP_ORIGINAL_FOR_DEBUG` → link or proxy rather than copy, or audio-only copy | P-OBS-5 | 9 |
| Environment: make `.venv312` real or document the actual interpreter; pin faster-whisper/ctranslate2 versions | P-DEP-7 | 1 |
| Deployment files & docs | P-DEP-1…6 | 10 |

---

## 13. ASR / Timing Plan

### 13.1 Exact current configuration [CONFIRMED]

| Parameter | Value | Source |
|---|---|---|
| Library | faster-whisper 1.2.1 / ctranslate2 4.8.2 | installed |
| Model | `base` (multilingual) | `transcription.py:39` |
| Device / compute | `cpu` / `int8` | same |
| `cpu_threads` / `num_workers` | 0 (CT2 default) / 1 | defaults |
| Task | `transcribe` | default |
| Language | `None` (auto from first 30 s, `language_detection_segments=1`, threshold 0.5) | defaults |
| `multilingual` | False | default |
| Beam / best_of / patience | 5 / 5 / 1 | explicit / defaults |
| Temperature fallback | [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] with compression 2.4, logprob −1.0, no_speech 0.6 thresholds | defaults |
| `condition_on_previous_text` | True | default |
| VAD | off | default |
| Word timestamps | off | default |
| `hallucination_silence_threshold` | None | default |
| Returned | `start`, `end`, `text` only; `info` discarded | `transcription.py:101-126` |

### 13.2 Language handling plan
1. **Modes:** `auto` (default) · `forced:{en|hi|ta}`. Selectable per job via API field and in the eval runner (D3).
2. **Better auto-detection:** run detection over several VAD-speech chunks spread across the file (`language_detection_segments`, or explicit sampling at 10 %/30 %/50 %/70 %), and record per-chunk results and top-3 probabilities.
3. **Guardrails:** if `language_probability` < threshold, or the per-chunk majority disagrees with the file-level choice, or script consistency is low → mark transcript `degraded`, record why, and (policy D3) either continue with a visible warning or re-run with the majority language.
4. **Code-switching:** spike compares (a) forced dominant language, (b) `multilingual=True`, (c) per-VAD-chunk language. Choose after D4 (script policy). Don't promise clean Hinglish/Tanglish until measured.
5. **Never translate** (`task=transcribe` always). Add a script-consistency check to catch translation-like output.

### 13.3 Hallucination & confidence
- VAD on (parameters tuned for podcasts: shorter `min_silence_duration_ms` than the 2000 ms default, `speech_pad_ms` tuned; values from Phase 4/5 data).
- Evaluate `condition_on_previous_text=False` and `hallucination_silence_threshold` (requires word timestamps).
- Per-segment flags: `no_speech_prob > x && avg_logprob < y`, `compression_ratio > 2.4`, repeated n-grams, words outside VAD speech, script mismatch.
- Flagged segments stay in the transcript (for debugging) but are **excluded from candidate text and features**.
- Transcript-level `quality.status` drives visible warnings, never silent substitution.

### 13.4 Timing policy
- **Segment timestamps:** used only for coarse grouping, never as cut points.
- **Word timestamps:** used to map text ↔ time (which words are in a span; sentence ends; pause estimates). Not trusted to ±ms.
- **VAD regions:** define where a cut is *allowed* — inside non-speech gaps.
- **Cut point rule (proposal):** for a desired boundary after word *w*, find the gap between VAD offset near `w.end` and the next VAD onset. Require gap ≥ `G_min` (e.g. 150–250 ms [EXPERIMENT]). Place `cut_out = offset + min(pad_out, gap/2)`, and `cut_in = onset − min(pad_in, gap/2)`. If no qualifying gap exists within a tolerance window, **that boundary is invalid** (the candidate uses a different unit edge).
- **Disagreements** between word timestamps and VAD (word ends after VAD offset, or a word inside non-speech) are recorded as boundary-risk features and in the debugger.
- **Forced alignment:** *not planned.* Because cuts are placed in measured silence gaps, phoneme-level precision isn't required. Re-open **only** if Phase 6 shows mid-word cut rate > 2 % attributable to word/VAD mismatch; then spike a CTC aligner (e.g. MMS/wav2vec2 via torch, which is a heavy dependency).

### 13.5 Source vs translated text
- Because `task=transcribe` and script checks are enforced, word timings refer to source-language tokens. If a future feature needs English text (translation/dubbing), it is derived *from* the source transcript and **never used for timing**.

---

## 14. Clip Selection Plan

### 14.1 Units (language-aware)
- **Words** (from ASR, flagged words removed).
- **Sentences:** split on terminal punctuation set per language: en `. ? !`; hi `। ॥ ? ! .`; ta `. ? !` (Tamil commonly uses Latin punctuation); plus a **long-pause fallback** (gap ≥ ~700 ms with falling boundary) because Whisper punctuation for Indic languages may be sparse or inconsistent [EXPERIMENT: measure punctuation density per language in Phase 5].
- **Thought units:** merge consecutive sentences until a *strong boundary* (pause ≥ T_long, topic-shift cues, question→answer turn, discourse markers like "so the thing is…" / "तो बात यह है" / "அதனால…" — lists per language, deliberately small, reviewed by you). Thought units are heuristic; the LLM later judges completeness, it doesn't construct units.

### 14.2 Duration policy (proposal for D7)
- **Hard min 12–15 s**, **soft target 25–60 s**, **hard max 90 s** (maybe 120 s for long stories). Duration enters ranking as a *mild* prior, never as a cut rule.
- Every candidate must satisfy temporal validity before any scoring.

### 14.3 Candidate generation (deterministic)
- For each thought-unit start *i* (with a valid `cut_in`), extend over units *i..j* while duration ≤ hard max; emit a candidate for every *j* with a valid `cut_out` and duration ≥ min. Keep up to 3 **ending variants** per start (e.g. shortest complete, +1 unit, +2 units).
- Prune: must-not regions (intro/outro music detected by VAD + optional position prior), flagged-transcript overlap > x %, speech ratio < y.
- Candidate count for a 2 h podcast is expected in the low thousands before pruning [ASSUMPTION], so it's cheap for deterministic scoring and the reason the model only sees top-K.

### 14.4 Deterministic features vs model judgement

| Quality dimension | Deterministic signal | Needs LLM? |
|---|---|---|
| Natural start | cut_in in gap; sentence start; no filler/connective start ("and", "but", "so", "और", "அதனால") | No |
| Natural end | cut_out in gap; sentence terminal; falling pause | No (LLM confirms intentionality) |
| Complete thought | thought-unit boundaries | Partly: completeness judgement |
| Context dependency | pronoun/deictic at start ("he", "that", "यह", "அது"), "as I said" | **Yes** for reliable judgement; deterministic cue as feature |
| Hook | question at start, second-person address, numbers, contrast words | **Yes** |
| Energy | loudness RMS z-score, loudness variance, speech-rate z-score (**normalised within the video**, removing language/speaker bias) | Mostly no; LLM adds textual excitement |
| Controversy / opinion | stance lexicon (weak) | **Yes** |
| Interesting question | `?` / interrogatives per language | Partly: "interesting" is semantic |
| Curiosity / open loop | ends on setup phrase, question without answer | **Yes**: intentional vs truncated |
| Payoff | — | **Yes** |
| Shareability | — | **Yes** |
| Coherence | ASR confidence, no flagged words, single speaker stretch (no diarization yet) | Partly |
| Redundancy / diversity | temporal distance, char 3-gram similarity | Optional (topic label) |

**Legacy word-density bias fix:** all rate/energy features are z-scored against the same video's distribution, so Tamil and English speakers aren't compared on absolute words/second.

### 14.5 Open-loop policy (proposal for D8)
- **Allowed endings:** `resolved` (thought completes), or `intentional_open_loop` (a grammatically complete sentence that sets up something unresolved: a question, "here's what nobody tells you…", a cliffhanger clause).
- **Never allowed:** cut not in a VAD gap; last sentence has no terminal (by punctuation *or* long-pause fallback); `truncated` label from the judge.
- **Without the model (`boundary_v1`):** only `resolved`-style endings (sentence terminal + gap). Open loops appear only if a question-terminal ending ranks highly.
- **With the model:** the judge chooses among precomputed variants and labels ending type; a truncated label rejects that variant.

### 14.6 Ranking, diversity and exact-5 (proposal for D9)
1. `final = w_det · det_score (+ w_sem · sem_score)`; weights set from Phase 6–7 data (initially simple, documented).
2. Greedy MMR-style selection: pick best, then penalise candidates overlapping in time or similar in text/topic.
3. **Exact-5 tiers**, each clip tagged with its tier and reason:
   - **Tier 1:** passes all gates (validity, quality threshold, diversity).
   - **Tier 2:** quality threshold relaxed (still valid boundaries, non-overlapping).
   - **Tier 3:** diversity relaxed (same topic allowed, still non-overlapping, min distance smaller).
   - **Tier 4:** duration minimum relaxed (still valid boundaries).
   - **Tier 5 (short inputs only):** partially overlapping but **distinct** spans (different start *and* end units, overlap ≤ 50 %). Never identical duplicates.
   - **Tier X:** if even Tier 5 can't produce 5 distinct valid spans (e.g. a 20 s video), this is a **product conflict**: fail with a clear message, enforce a minimum input length at submit, or accept fewer. **You decide (D9)**; the system won't silently duplicate.
4. The API returns tier per clip (visibility per D10); analysis always records it.

### 14.7 Legacy baseline
- `legacy_v2` moved verbatim into an engine module, parameterised only by `max_clips`, golden-tested. It keeps reading the plain `segments` list so it can run on old or new ASR (E0–E2).

---

## 15. Local SLM Plan

### 15.1 What's known
- Model on disk: **Qwen3.5-9B, Q4_K_M, 6.59 GB** in Ollama (requires Ollama ≥ 0.17.1). Modelfile defaults: temperature 1.0, top_k 20, top_p 0.95, presence_penalty 1.5. **These must be overridden for scoring** (temperature ≈ 0–0.3, presence penalty 0).
- Hardware: 8C/16T Zen 3, dual-channel DDR4 (assumed) → CPU token generation is memory-bandwidth-bound.

### 15.2 Estimates to verify [ASSUMPTION → Phase 7 EXPERIMENT]

| Quantity | Rough expectation | Why it matters |
|---|---|---|
| RAM | ~7–9 GB model + KV cache for the chosen context | fits in 32 GB alongside Whisper large-v3 int8 (~2–4 GB), but not alongside two of each |
| Generation speed | single-digit tokens/s | thinking mode or long rationales become minutes per call |
| Prompt processing | tens of tokens/s | dominates cost; Indic text tokenises into more tokens |
| Per-candidate cost | ~400–900 prompt tokens + ~80–150 output tokens (JSON) | top-40 candidates ≈ tens of minutes on CPU unless batched |

(The Radeon RX 580 is not assumed usable. An optional Vulkan-offload spike could be run later, only if you want it.)

### 15.3 Roles evaluated (maps to your A–E)
- **A. Rank candidates:** listwise ranking of many candidates in one prompt. Suffers position bias and context length. Test only for the final top-10 (pairwise or small-list tournament).
- **B. Classify quality:** e.g. postable / not. Cheap, useful as a gate.
- **C. Score dimensions:** hook, curiosity, controversy, question, payoff, standalone context, coherence, energy (textual), plus `ending_type` and `context_dependency`. **Recommended primary role.** Interpretable, debuggable, combinable with deterministic scores.
- **D. Rewrite/extend boundaries:** **rejected as free-form.** Allowed only as *choosing a precomputed variant ID*.
- **E. Other:** topic label (for diversity) and a ≤ 30-word rationale (for the debugger).

### 15.4 Integration architecture (for Phase 8, not implemented)
```text
SemanticJudge (interface)
  ├─ NullJudge          → returns "not evaluated" (engine boundary_v1)
  └─ OllamaJudge        → HTTP localhost:11434 /api/chat
        • model tag, options {temperature, num_ctx, num_thread, seed}, think=false (per D12)
        • format = JSON schema (structured output), validation with pydantic
        • batching: N candidates per prompt (N from spike), with context-before/after snippets
        • timeouts, 1–2 retries, then mark candidate semantic_status=failed
        • prompt files versioned (prompt_version recorded in analysis)
        • cancellation: check job between batches; abort HTTP request on cancel
Worker: single heavy-inference slot (no ASR and LLM concurrently on CPU, per D13)
```
- **Out-of-process** (Ollama or llama.cpp server) rather than in-process bindings: a model crash or OOM can't take down the API; memory is visible separately; the model can be swapped without Python dependency changes.
- Input contains **text, language, duration, candidate/variant IDs, and neighbouring context**, never raw timestamps to edit.

### 15.5 Model comparison at CP6 (only as necessary)
- **Qwen3.5-9B Q4_K_M** (have).
- **One smaller Qwen3.5 variant** (e.g. ~4B, if available in the Ollama library, to verify) for the cost/quality trade-off.
- Optional: **9B at a higher-precision quant** on a subset, to check quantisation sensitivity for Tamil.
- Report per model: agreement with your labels (pairwise accuracy, Spearman), JSON validity, stability, per-language quality, RAM, latency per video, tokens per Hindi/Tamil word.
- Rule: prefer the smallest model whose E4-style gain over E3 is within noise of the 9B's.

---

## 16. Future Extension Points (not implemented)

Future path: `clip → clip transcript → translation → speaker-preserving TTS/dubbing → multilingual asset`.

Seams that are **justified now** (they serve current needs too):
- **Transcript with words, language and confidence**: needed now for boundaries; later for subtitles, translation and dubbing timing.
- **Clip-relative transcript slice** (words within `[cut_in, cut_out]`, re-based to 0): useful now for the debugger/eval; later the dubbing input.
- **RenderSpec separated from selection**: needed now for engine comparison; later a dubbed audio track is just another render input.
- **Per-clip audio extraction option** (clean source audio for the span): useful now for listening tests; later speaker reference audio.

Seams **not** created now: `TranslationService`, `VoiceDubbingService`, speaker diarization. Documented only. Note: diarization would also benefit selection (speaker turns as boundaries), but it's a separate model decision and not in scope unless you ask.

---

## 17. Deployment / Scale Roadmap

### NOW (single machine, local validation)
- Local FastAPI + worker threads + local disk; Cloudflare tunnel only for demos.
- Worker concurrency 1 for heavy inference (D13); Ollama as a local sidecar process.
- Offline eval runner is the primary way to process long-form content.
- Deployment docs reduced to what works; Vercel/Render marked unsupported (D20).
- Stage caching on local disk keyed by content hash + config hash.

### What currently prevents scaling (identified, not fixed now)
1. In-memory job state (lost on restart; not shareable across processes).
2. Workers in the API process (a long CPU job competes with request handling; restart kills jobs).
3. Local-disk outputs discovered by glob; GC by mtime.
4. Models loaded per process; no model server for ASR.
5. Uploads streamed through the API and capped by Cloudflare (100 MB).
6. No auth, rate limits or per-user quotas; debugger bundle public.
7. No retries/idempotency; a job is lost on crash mid-stage.

### LATER (only when the NOW system is proven)
```text
Local validation (now)
  → Single dedicated CPU/GPU server: API process + separate worker process, persistent job table (SQLite/Postgres)
  → Object storage (R2/S3) for media & clips; presigned direct uploads for long files
  → Persistent queue only when >1 worker host is needed (Redis/RQ or similar, chosen then)
  → Distributed workers; ASR/LLM as model servers; GPU for large-v3 & LLM
```
No Redis/Celery/RQ/K8s/object storage in this project unless you explicitly approve it.

---

## 18. Risks / Unknowns

### Confirmed facts
- Everything tagged [CONFIRMED] in §3 and §13.1: grid starts, end overwrite, `+18 s`, sum-density ranking, duplication, fake energy, stub fallback, discarded language info, cp1252 write failure, `.env` order bug, base/cpu/int8/beam 5/no VAD/no words, 100 MB upload cap, only `base` cached, Qwen3.5-9B Q4_K_M present in Ollama, `.venv312` empty, 105 tests passing.

### Assumptions (reasoned, not verified here)
- `base` is the largest single cause of poor Hindi/Tamil accuracy.
- Whisper outputs English or romanised text when Tamil/Hindi is mis-detected.
- Whisper word timestamps are typically within a few hundred ms but unreliable at segment edges and for hallucinated words.
- CTranslate2 serialises concurrent calls on one model with `num_workers=1`.
- Large-v3 on this CPU runs near or below real time; a 2 h podcast could take on the order of an hour or more.
- Qwen3.5-9B Q4 on this CPU generates single-digit tokens/s.
- Whisper's Hindi output uses `।` often enough to matter.
- Hindi/Tamil text costs noticeably more LLM tokens per word than English.

### Requires experimentation
- Relative contribution of model size / language detection / VAD / conditioning to Indic ASR errors (Phase 4).
- Best VAD parameters and minimum gap for clean cuts on podcast audio (Phase 5).
- Punctuation density of Whisper Hindi/Tamil output and whether pause fallback is needed (Phase 5).
- Candidate recall@K of deterministic features, which decides whether Option C is needed (Phase 6).
- Whether Qwen3.5-9B scores agree with your judgement better than deterministic features, per language (Phase 7).
- Whether thinking mode is worth its latency (Phase 7).
- Code-switched transcription quality under each language mode (Phase 4).
- Whether 5 genuinely distinct good moments exist in short/medium videos, i.e. how often tiers ≥ 3 are needed (Phase 6).

### Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Processing time explodes (large ASR + LLM on CPU) | experiments slow; GC/timeouts bite | stage cache; measured latency ceiling (D5); GC fix in Phase 1 |
| Tiny dataset → false confidence | wrong decisions | paired, per-video CIs; report as directional; second rater if possible |
| Single rater bias | overfits to your taste | blind packets; that taste *is* the product owner's for now, stated explicitly |
| Indic ASR still inadequate with large-v3 | semantic stage garbage-in | spike Indic-specialised model (heavier deps) as a gated option |
| LLM scores unstable or position-biased | noisy ranking | temperature ≈ 0, fixed seed, small batches, stability metric, pairwise for top ranks |
| Legacy tests block refactors | slows Phase 6 | move to engine-scoped golden tests (D19) |
| Copyright of YouTube eval media | legal/sharing | media outside git; manifest with hashes only (D16) |
| Exact-5 on very short inputs | product quality | explicit tier policy + your decision (D9) |
| Scope creep (diarization, vertical reframing, subtitles) | delays core goal | out of scope unless approved |

---

## 19. Definition of Done

### Reliability
- [ ] No stub/fake transcripts anywhere; model/ASR failure → visible job error with cause.
- [ ] Hallucination suspects flagged per segment; transcript `quality.status` visible in job and analysis.
- [ ] Detected language, probability, per-chunk results and mode (auto/forced) visible in job and analysis.
- [ ] Every job ends in exactly one terminal state; cancellation works in every long stage (download, ASR, LLM, render) within a bounded time.
- [ ] GC never deletes active-job files; eval/debug artifacts follow their own retention.
- [ ] analysis.json writes are UTF-8 and atomic on Windows and Linux, including failed runs; write failures are visible.
- [ ] `.env` settings take effect; the documented environment matches the real one.

### Temporal quality (measured on `clippods-eval-v1`)
- [ ] Mid-word cut rate ≤ 2 % (reference-based metric + spot labels).
- [ ] No fixed-grid starts; no fixed-duration end overwrite (enforced by invariant tests).
- [ ] Every cut point lies in a measured non-speech gap (invariant test + analysis field).
- [ ] Truncated-ending rate ≤ 5 % (human spot labels).

### Semantic quality
- [ ] Blind set-level preference for the final engine over `legacy_v2@5` ≥ 65 % (CI lower bound > 50 %), with no language showing a regression.
- [ ] Hook and curiosity Likert means improve by ≥ 0.5 over `boundary_v1` if the semantic engine ships.
- [ ] Precision@5 against your gold moments improves over legacy on every language subset (directional).
- [ ] Intentional open loops are labelled and are rated "intentional" rather than "truncated" by you in ≥ 80 % of cases.

### Product behaviour
- [ ] Exactly 5 clips for every accepted input, each with tier and reason; zero identical duplicates; overlaps only under the approved short-video rule.
- [ ] Duration follows thought units within the approved policy; distribution reported.
- [ ] Processing time and peak RAM recorded per run and within the ceiling you set.

### Engineering quality
- [ ] `legacy_v2`, `boundary_v1` and `boundary_v1+semantic` are selectable and comparable on the same cached inputs.
- [ ] Stage contracts (§6.4) are typed and schema-tested; the model can't set timestamps (invariant test).
- [ ] No paid APIs; all inference local.
- [ ] Debugger answers "why this clip?" with ASR, VAD, boundary, feature, semantic and fallback evidence.
- [ ] Docs describe only what the code does; unsupported deployment paths are removed or labelled.
- [ ] Tests don't touch real `outputs/`/`temp/`; the real worker path is covered.

---

### Checkpoint 1 (resolved)

Approved 2026-09-14. See the Decision Record at the top. The original questions were:

1. Do the confirmed findings in §3 match what you've seen? Is anything wrong or missing?
2. Decisions **D1** (architecture direction), **D2** (allow measurement-only spikes), **D14** (long-form ingestion for local validation), **D22** (where this plan lives), **D24** (delete the test-created fake clip folder).
3. Whether Phases 0–1 may start after Checkpoint 2, since neither changes clip selection.
