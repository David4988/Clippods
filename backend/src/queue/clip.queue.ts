import { Queue } from 'bullmq';
import { ENV } from '../config/env';
import IORedis from 'ioredis';

const JOB_QUEUE = 'clip_jobs';

// ─── Shared Redis connection with retry logic ──────────────
export const redisConnection = new IORedis({
  host: ENV.REDIS_HOST,
  port: ENV.REDIS_PORT,
  maxRetriesPerRequest: null,       // Required by BullMQ
  enableReadyCheck: false,          // Prevents startup hang
  retryStrategy(times: number) {
    const delay = Math.min(times * 500, 5000); // Exponential backoff, max 5s
    console.warn(`[redis] Reconnecting attempt ${times} (next retry in ${delay}ms)...`);
    return delay;
  },
  reconnectOnError(err) {
    console.error('[redis] Connection error:', err.message);
    return true;  // Always attempt reconnect
  },
});

redisConnection.on('connect', () => {
  console.log('[redis] Connected to Redis successfully');
});

redisConnection.on('error', (err) => {
  // Prevent unhandled error crash — just log it
  console.error('[redis] Redis error:', err.message);
});

redisConnection.on('close', () => {
  console.warn('[redis] Redis connection closed, will retry...');
});

// ─── Queue ─────────────────────────────────────────────────
export const clipQueue = new Queue(JOB_QUEUE, {
  connection: redisConnection,
});

clipQueue.on('error', (err) => {
  console.error('[queue] BullMQ Queue error:', err.message);
});

// ─── Add job helper with error handling ────────────────────
export const addClipJob = async (jobId: string, data: any) => {
  try {
    return await clipQueue.add('process-clip', data, { jobId });
  } catch (err: any) {
    console.error('[queue] Failed to enqueue clip job:', err.message);
    throw new Error('Redis is unavailable — cannot queue clip job. Please ensure Redis is running.');
  }
};

// ─── Health check helper ───────────────────────────────────
export async function checkRedisHealth(): Promise<boolean> {
  try {
    const result = await redisConnection.ping();
    return result === 'PONG';
  } catch {
    return false;
  }
}
