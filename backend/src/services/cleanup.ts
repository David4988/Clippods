import fs from 'fs';
import path from 'path';
import { PATHS } from '../config/paths';

const CLEANUP_INTERVAL_MS = 30 * 60 * 1000; // 30 minutes
const MAX_AGE_MS = 60 * 60 * 1000; // 1 hour

/**
 * Remove files and directories from a target directory that are older than maxAgeMs.
 * Designed for cleaning up orphaned temp files from failed imports/renders.
 */
function cleanStaleEntries(dir: string, maxAgeMs: number): number {
  if (!fs.existsSync(dir)) return 0;

  let cleaned = 0;
  const now = Date.now();

  try {
    const entries = fs.readdirSync(dir);
    for (const entry of entries) {
      const fullPath = path.join(dir, entry);
      try {
        const stat = fs.statSync(fullPath);
        const age = now - stat.mtimeMs;

        if (age > maxAgeMs) {
          if (stat.isDirectory()) {
            fs.rmSync(fullPath, { recursive: true, force: true });
          } else {
            fs.unlinkSync(fullPath);
          }
          cleaned++;
        }
      } catch {
        // Skip entries we can't stat or delete (in use, permissions, etc.)
      }
    }
  } catch (err: any) {
    console.error(`[cleanup] Error scanning ${dir}:`, err.message);
  }

  return cleaned;
}

/**
 * Run a single cleanup pass on temp and output temp directories.
 */
export function runCleanup(): void {
  const tempCleaned = cleanStaleEntries(PATHS.temp, MAX_AGE_MS);
  if (tempCleaned > 0) {
    console.log(`[cleanup] Removed ${tempCleaned} stale entries from temp/`);
  }

  // Also clean up any _rendering temp files in outputs that are older than maxAge
  // (these indicate ffmpeg crashed mid-render)
  if (fs.existsSync(PATHS.outputs)) {
    try {
      const entries = fs.readdirSync(PATHS.outputs);
      const now = Date.now();
      let renderClean = 0;

      for (const entry of entries) {
        if (entry.includes('_rendering')) {
          const fullPath = path.join(PATHS.outputs, entry);
          try {
            const stat = fs.statSync(fullPath);
            if (now - stat.mtimeMs > MAX_AGE_MS) {
              fs.unlinkSync(fullPath);
              renderClean++;
            }
          } catch {}
        }
      }

      if (renderClean > 0) {
        console.log(`[cleanup] Removed ${renderClean} stale render temp files from outputs/`);
      }
    } catch {}
  }
}

/**
 * Start periodic cleanup. Safe to call from backend startup.
 */
export function startCleanupScheduler(): void {
  // Run once on startup (delayed 10s to let the app settle)
  setTimeout(() => {
    runCleanup();
  }, 10_000);

  // Then run periodically
  setInterval(() => {
    runCleanup();
  }, CLEANUP_INTERVAL_MS);

  console.log(`[cleanup] Scheduler started (interval: ${CLEANUP_INTERVAL_MS / 1000}s, maxAge: ${MAX_AGE_MS / 1000}s)`);
}
