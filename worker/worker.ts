import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import os from 'os';

// ─── Load .env ─────────────────────────────────────────────
dotenv.config({ path: path.resolve(__dirname, '.env') });

import { Worker, Job } from 'bullmq';
import ffmpeg from 'fluent-ffmpeg';
import sqlite3 from 'sqlite3';
import IORedis from 'ioredis';

// ─── Config ────────────────────────────────────────────────
const REDIS_HOST = process.env.REDIS_HOST || '127.0.0.1';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379', 10);
const JOB_QUEUE = 'clip_jobs';
const WORKER_CONCURRENCY = 2;
const JOB_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes max per job

// Resolve project root relative to this file
const rootDir = path.resolve(__dirname, '..');
const dbPath = path.join(rootDir, 'backend', 'src', 'db', 'clippods.sqlite');

// ─── FFmpeg binary resolution ──────────────────────────────
const home = os.homedir();
const wingetLinks = path.join(home, 'AppData', 'Local', 'Microsoft', 'WinGet', 'Links');

function resolveTool(candidates: string[], fallback: string): string {
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return fallback;
}

const resolvedFfmpeg = resolveTool([
  'D:\\tools\\ffmpeg\\bin\\ffmpeg.exe',
  path.join(wingetLinks, 'ffmpeg.exe'),
], 'ffmpeg');

const resolvedFfprobe = resolveTool([
  'D:\\tools\\ffmpeg\\bin\\ffprobe.exe',
  path.join(wingetLinks, 'ffprobe.exe'),
], 'ffprobe');

console.log(`[worker] ffmpeg  → ${resolvedFfmpeg}`);
console.log(`[worker] ffprobe → ${resolvedFfprobe}`);

ffmpeg.setFfmpegPath(resolvedFfmpeg);
ffmpeg.setFfprobePath(resolvedFfprobe);

// Ensure output directory exists
const outputsDir = path.join(rootDir, 'outputs');
if (!fs.existsSync(outputsDir)) fs.mkdirSync(outputsDir, { recursive: true });

// ─── Startup validation ───────────────────────────────────
function validateStartup(): boolean {
  let ok = true;

  if (!fs.existsSync(dbPath)) {
    console.error(`[worker] ❌ Database not found at: ${dbPath}`);
    console.error(`[worker]    Start the backend first to create the database.`);
    ok = false;
  }

  if (resolvedFfmpeg !== 'ffmpeg' && !fs.existsSync(resolvedFfmpeg)) {
    console.warn(`[worker] ⚠️  ffmpeg binary not found at resolved path: ${resolvedFfmpeg} — will try PATH fallback`);
  }

  return ok;
}

// ─── Database helper ───────────────────────────────────────
let db: sqlite3.Database;

function openDb(): sqlite3.Database {
  const database = new sqlite3.Database(dbPath, (err) => {
    if (err) {
      console.error('[worker] ❌ Failed to open database:', err.message);
    } else {
      // Enable WAL + extended busy timeout for concurrent access
      database.run('PRAGMA journal_mode = WAL;');
      database.run('PRAGMA busy_timeout = 10000;');
      console.log('[worker] ✅ Database connected (WAL mode)');
    }
  });
  return database;
}

function updateJobDB(
  jobId: string,
  updates: Partial<{ status: string; progress: number; outputPath: string; errorMessage: string }>
): Promise<void> {
  return new Promise((resolve, reject) => {
    const fields: string[] = [];
    const params: any[] = [];
    for (const [k, v] of Object.entries(updates)) {
      fields.push(`${k} = ?`);
      params.push(v);
    }
    fields.push('updatedAt = CURRENT_TIMESTAMP');
    const query = `UPDATE clip_jobs SET ${fields.join(', ')} WHERE id = ?`;
    params.push(jobId);
    db.run(query, params, (err) => {
      if (err) {
        console.error(`[worker] DB update error for job ${jobId}:`, err.message);
        reject(err);
      } else {
        resolve();
      }
    });
  });
}

/**
 * Check if a job is already being processed (deduplication guard).
 */
function getJobStatus(jobId: string): Promise<string | null> {
  return new Promise((resolve, reject) => {
    db.get('SELECT status FROM clip_jobs WHERE id = ?', [jobId], (err, row: any) => {
      if (err) reject(err);
      else resolve(row?.status || null);
    });
  });
}

/**
 * Check available disk space (returns bytes available).
 */
function getAvailableDiskSpace(): number {
  try {
    // On Windows, we check the drive where outputs are stored
    const stats = fs.statfsSync(outputsDir);
    return stats.bavail * stats.bsize;
  } catch {
    // statfsSync may not be available on older Node.js, return a safe default
    return Infinity;
  }
}

// ─── Aspect ratio crop filters ─────────────────────────────
function getCropFilter(ratio: string): string {
  switch (ratio) {
    case '1:1':
      return "crop='min(iw,ih)':'min(iw,ih)'";
    case '9:16':
      return "crop='if(gt(iw/ih,9/16),ih*(9/16),iw)':'if(gt(iw/ih,9/16),ih,iw*(16/9))'";
    case '16:9':
      return "crop='if(gt(iw/ih,16/9),ih*(16/9),iw)':'if(gt(iw/ih,16/9),ih,iw/(16/9))'";
    case '4:5':
      return "crop='if(gt(iw/ih,4/5),ih*(4/5),iw)':'if(gt(iw/ih,4/5),ih,iw*(5/4))'";
    default:
      return '';
  }
}

// ─── Redis connection with retry ───────────────────────────
const redisConnection = new IORedis({
  host: REDIS_HOST,
  port: REDIS_PORT,
  maxRetriesPerRequest: null,
  enableReadyCheck: false,
  retryStrategy(times: number) {
    const delay = Math.min(times * 500, 5000);
    console.warn(`[worker:redis] Reconnecting attempt ${times} (next retry in ${delay}ms)...`);
    return delay;
  },
  reconnectOnError(err) {
    console.error('[worker:redis] Connection error:', err.message);
    return true;
  },
});

redisConnection.on('connect', () => {
  console.log('[worker:redis] ✅ Connected to Redis');
});

redisConnection.on('error', (err) => {
  console.error('[worker:redis] Redis error:', err.message);
});

// ─── Worker ────────────────────────────────────────────────
async function startWorker() {
  if (!validateStartup()) {
    console.error('[worker] Startup validation failed — exiting');
    process.exit(1);
  }

  db = openDb();

  // Ping Redis
  try {
    const pong = await redisConnection.ping();
    console.log(`[worker] Redis ping: ${pong}`);
  } catch (err: any) {
    console.warn(`[worker] ⚠️  Redis not reachable yet: ${err.message}`);
    console.warn(`[worker]    Worker will keep retrying in background...`);
  }

  const worker = new Worker(
    JOB_QUEUE,
    async (job: Job) => {
      const { jobId, startTime, endTime, mode, inputPath, config } = job.data;
      const ratio = config?.ratio || 'original';
      const format = config?.format || 'video';

      // Deduplication: skip if already processing or completed
      const currentStatus = await getJobStatus(jobId).catch(() => null);
      if (currentStatus === 'processing' || currentStatus === 'completed') {
        console.log(`[worker] Skipping job ${jobId} — already ${currentStatus}`);
        return;
      }

      let finalMode = mode;
      if (ratio !== 'original') {
        finalMode = 'accurate';
      }

      console.log(`[worker] ────────────────────────────────────────`);
      console.log(`[worker] Processing job ${jobId}`);
      console.log(`[worker]   Input: ${inputPath}`);
      console.log(`[worker]   Range: ${startTime}s → ${endTime}s`);
      console.log(`[worker]   Mode:  ${finalMode} | Ratio: ${ratio} | Format: ${format}`);

      // Validate input file exists
      if (!fs.existsSync(inputPath)) {
        const errMsg = `Input file not found: ${inputPath}`;
        console.error(`[worker] ❌ ${errMsg}`);
        await updateJobDB(jobId, { status: 'failed', errorMessage: errMsg }).catch(() => {});
        throw new Error(errMsg);
      }

      // Validate time range
      const duration = endTime - startTime;
      if (duration <= 0 || !isFinite(duration)) {
        const errMsg = `Invalid time range: ${startTime} → ${endTime}`;
        console.error(`[worker] ❌ ${errMsg}`);
        await updateJobDB(jobId, { status: 'failed', errorMessage: errMsg }).catch(() => {});
        throw new Error(errMsg);
      }

      // Disk space check (require at least 500MB free)
      const freeSpace = getAvailableDiskSpace();
      if (freeSpace < 500 * 1024 * 1024) {
        const errMsg = 'Insufficient disk space (< 500MB free)';
        console.error(`[worker] ❌ ${errMsg}`);
        await updateJobDB(jobId, { status: 'failed', errorMessage: errMsg }).catch(() => {});
        throw new Error(errMsg);
      }

      await updateJobDB(jobId, { status: 'processing', progress: 5 });

      const isAudioOnly = format === 'audio';
      const outExt = isAudioOnly ? '.m4a' : '.mp4';
      // Write to a temp file first, then rename atomically
      const finalOutputPath = path.join(outputsDir, `${jobId}${outExt}`);
      const tempOutputPath = path.join(outputsDir, `${jobId}_rendering${outExt}`);

      let lastProgressUpdate = 0;

      // Choose preset based on clip duration (longer clips use faster presets)
      const preset = duration > 1800 ? 'ultrafast' : duration > 600 ? 'veryfast' : 'fast';

      return new Promise<string>((resolve, reject) => {
        const ff = ffmpeg(inputPath);

        const vfString = getCropFilter(ratio);

        if (isAudioOnly) {
          ff.inputOptions([`-ss`, `${startTime}`])
            .outputOptions([`-t`, `${duration}`, `-vn`, `-c:a`, `aac`, `-avoid_negative_ts`, `make_zero`]);
        } else if (finalMode === 'fast') {
          ff.inputOptions([`-ss`, `${startTime}`])
            .outputOptions([`-t`, `${duration}`, `-c`, `copy`, `-avoid_negative_ts`, `make_zero`]);
        } else {
          const outOpts = [
            `-t`, `${duration}`,
            `-c:v`, `libx264`,
            `-preset`, preset,
            `-crf`, `23`,
            `-c:a`, `aac`,
            `-avoid_negative_ts`, `make_zero`,
          ];
          if (vfString) {
            outOpts.push('-vf', vfString);
          }
          ff.inputOptions([`-ss`, `${startTime}`])
            .outputOptions(outOpts);
        }

        // Set a hard timeout to kill stuck ffmpeg processes
        const jobTimer = setTimeout(() => {
          console.error(`[worker] ⏰ Job ${jobId} timed out after ${JOB_TIMEOUT_MS / 1000}s — killing ffmpeg`);
          try { ff.kill('SIGTERM'); } catch {}
        }, JOB_TIMEOUT_MS);

        ff.output(tempOutputPath)
          .on('start', (commandLine: string) => {
            console.log(`[worker] FFmpeg: ${commandLine}`);
            updateJobDB(jobId, { progress: 10 }).catch(() => {});
          })
          .on('progress', (progress: any) => {
            // Guard against NaN/undefined/negative percent values
            const rawPercent = progress?.percent;
            const percent = (typeof rawPercent === 'number' && isFinite(rawPercent) && rawPercent > 0)
              ? Math.min(95, Math.max(10, Math.floor(rawPercent)))
              : 10;

            const now = Date.now();
            // Throttle DB updates to avoid SQLITE_BUSY
            if (now - lastProgressUpdate > 2000) {
              lastProgressUpdate = now;
              updateJobDB(jobId, { progress: percent }).catch(() => {});
            }
          })
          .on('end', async () => {
            clearTimeout(jobTimer);
            try {
              if (!fs.existsSync(tempOutputPath)) {
                const errMsg = 'FFmpeg completed but output file was not created';
                console.error(`[worker] ❌ ${errMsg}`);
                await updateJobDB(jobId, { status: 'failed', errorMessage: errMsg });
                reject(new Error(errMsg));
                return;
              }

              const stats = fs.statSync(tempOutputPath);
              if (stats.size === 0) {
                const errMsg = 'FFmpeg produced an empty output file';
                console.error(`[worker] ❌ ${errMsg}`);
                try { fs.unlinkSync(tempOutputPath); } catch {}
                await updateJobDB(jobId, { status: 'failed', errorMessage: errMsg });
                reject(new Error(errMsg));
                return;
              }

              // Atomic rename: temp → final (same filesystem, so this is safe)
              fs.renameSync(tempOutputPath, finalOutputPath);

              await updateJobDB(jobId, { status: 'completed', progress: 100, outputPath: finalOutputPath });
              console.log(`[worker] ✅ Job ${jobId} completed → ${finalOutputPath} (${(stats.size / 1024 / 1024).toFixed(2)} MB)`);
              resolve(finalOutputPath);
            } catch (e) {
              reject(e);
            }
          })
          .on('error', async (err: Error) => {
            clearTimeout(jobTimer);
            console.error(`[worker] ❌ Job ${jobId} FFmpeg error:`, err.message);
            // Clean up partial output
            try { if (fs.existsSync(tempOutputPath)) fs.unlinkSync(tempOutputPath); } catch {}
            await updateJobDB(jobId, { status: 'failed', errorMessage: err.message }).catch(() => {});
            reject(err);
          });

        ff.run();
      });
    },
    {
      connection: redisConnection,
      concurrency: WORKER_CONCURRENCY,
    }
  );

  worker.on('failed', (job, err) => {
    console.error(`[worker] BullMQ reports job ${job?.id} failed: ${err.message}`);
  });

  worker.on('completed', (job) => {
    console.log(`[worker] BullMQ reports job ${job?.id} completed`);
  });

  worker.on('error', (err) => {
    console.error('[worker] Worker error event:', err.message);
  });

  worker.on('ready', () => {
    console.log('[worker] ────────────────────────────────────────');
    console.log('[worker] ✅ ClipPods worker is READY and listening for jobs');
    console.log(`[worker]    Queue: ${JOB_QUEUE}`);
    console.log(`[worker]    Redis: ${REDIS_HOST}:${REDIS_PORT}`);
    console.log(`[worker]    Concurrency: ${WORKER_CONCURRENCY}`);
    console.log('[worker] ────────────────────────────────────────');
  });

  // ─── Graceful shutdown ─────────────────────────────────────
  async function shutdown(signal: string) {
    console.log(`\n[worker] Received ${signal} — shutting down gracefully...`);
    try {
      await worker.close();
      console.log('[worker] Worker closed — in-flight jobs will be retried');
    } catch (err: any) {
      console.error('[worker] Shutdown error:', err.message);
    }
    process.exit(0);
  }

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

// ─── Start ─────────────────────────────────────────────────
startWorker().catch((err) => {
  console.error('[worker] Fatal startup error:', err);
  process.exit(1);
});
