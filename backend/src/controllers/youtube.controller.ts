import { Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';
import path from 'path';
import fs from 'fs';
import { execFile, spawn } from 'child_process';
import { PATHS } from '../config/paths';
import { runQuery } from '../db/database';
import { AuthRequest } from '../middleware/auth.middleware';
import ffmpeg from 'fluent-ffmpeg';

ffmpeg.setFfmpegPath(PATHS.ffmpeg);
ffmpeg.setFfprobePath(PATHS.ffprobe);

const MAX_VIDEO_DURATION_SECONDS = 7200; // 2 hours
const DOWNLOAD_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

const YT_URL_REGEX = /^(?:https?:\/\/)?(?:www\.)?(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})(?:\S+)?$/;

/**
 * Pre-flight check: fetch video metadata without downloading.
 * Returns parsed JSON or null on failure.
 */
function fetchVideoMeta(ytdlpBin: string, url: string): Promise<any | null> {
  return new Promise((resolve) => {
    execFile(
      ytdlpBin,
      ['--dump-json', '--no-download', '--no-warnings', url],
      { timeout: 30_000, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout) => {
        if (err || !stdout) return resolve(null);
        try {
          resolve(JSON.parse(stdout));
        } catch {
          resolve(null);
        }
      }
    );
  });
}

/**
 * Download video using spawn (non-blocking, argument-safe).
 * Resolves when yt-dlp exits successfully, rejects otherwise.
 */
function downloadVideo(
  ytdlpBin: string,
  url: string,
  tempDir: string,
  timeoutMs: number
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const args = [
      '--keep-video',
      '-P', tempDir,
      '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
      '--merge-output-format', 'mp4',
      '--write-info-json',
      '-o', 'video.%(ext)s',
      '--no-warnings',
      url,
    ];

    const proc = spawn(ytdlpBin, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    let killed = false;

    const timer = setTimeout(() => {
      killed = true;
      proc.kill('SIGTERM');
      reject(new Error(`yt-dlp download timed out after ${timeoutMs / 1000}s`));
    }, timeoutMs);

    proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

    proc.on('close', (code) => {
      clearTimeout(timer);
      if (killed) return;
      if (code !== 0) {
        reject(new Error(`yt-dlp exited with code ${code}: ${stderr.slice(0, 500)}`));
      } else {
        resolve({ stdout, stderr });
      }
    });

    proc.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * Extract highlight suggestions from yt-dlp info.json.
 */
function extractSuggestions(infoJsonPath: string, sourceDuration: number): any[] {
  if (!fs.existsSync(infoJsonPath)) return [];

  try {
    const raw = fs.readFileSync(infoJsonPath, 'utf8');
    const data = JSON.parse(raw);
    const dur = sourceDuration || data.duration || 0;

    // Prefer heatmap data (audience retention)
    if (data.heatmap && Array.isArray(data.heatmap) && data.heatmap.length > 0) {
      const sorted = [...data.heatmap].sort((a: any, b: any) => b.value - a.value);
      const peaks: any[] = [];
      for (const block of sorted) {
        const overlap = peaks.some((p) => Math.abs(p.startTime - block.start_time) < 30);
        if (!overlap) {
          const start = Math.max(0, block.start_time - 5);
          const end = Math.min(dur, start + 30);
          peaks.push({
            startTime: parseFloat(start.toFixed(2)),
            endTime: parseFloat(end.toFixed(2)),
            label: peaks.length === 0 ? 'Highest Replay Value' : 'High Engagement Moment',
            confidence: parseFloat(block.value.toFixed(2)),
          });
        }
        if (peaks.length >= 3) break;
      }
      return peaks;
    }

    // Fallback to chapters
    if (data.chapters && Array.isArray(data.chapters) && data.chapters.length > 0) {
      const suggestions: any[] = [];
      for (const chap of data.chapters) {
        if (suggestions.length >= 3) break;
        const start = chap.start_time;
        const end = Math.min(dur, start + 30);
        const title = typeof chap.title === 'string' ? chap.title : 'Chapter';
        suggestions.push({
          startTime: parseFloat(start.toFixed(2)),
          endTime: parseFloat(end.toFixed(2)),
          label: `Chapter: ${title.substring(0, 20)}`,
          confidence: 0.8,
        });
      }
      return suggestions;
    }
  } catch (e) {
    console.error('[youtube] Failed to parse info.json:', e);
  }

  return [];
}

/**
 * Safely remove a directory, ignoring errors (temp cleanup).
 */
function cleanupDir(dir: string) {
  try {
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  } catch (e) {
    console.warn('[youtube] Cleanup warning:', (e as Error).message);
  }
}

export default async function youtubeController(req: Request, res: Response) {
  const { url } = req.body;
  if (!url || typeof url !== 'string') {
    return res.status(400).json({ success: false, message: 'URL required' });
  }

  const trimmedUrl = url.trim();
  if (!YT_URL_REGEX.test(trimmedUrl)) {
    return res.status(400).json({ success: false, message: 'Invalid YouTube URL' });
  }

  const videoId = `yt_${uuidv4().replace(/-/g, '').substring(0, 8)}`;
  const destinationPath = path.join(PATHS.uploads, `${videoId}.mp4`);
  const tempDir = path.join(PATHS.temp, `yt_${videoId}`);
  const ytdlpBin = PATHS.ytdlp;

  // Extract userId from auth token if present
  const authReq = req as AuthRequest;
  const userId = authReq.user?.id || null;

  try {
    // Pre-flight: check video duration before downloading
    console.log(`[youtube] Pre-flight metadata check for: ${trimmedUrl}`);
    const meta = await fetchVideoMeta(ytdlpBin, trimmedUrl);

    if (meta && meta.duration && meta.duration > MAX_VIDEO_DURATION_SECONDS) {
      return res.status(400).json({
        success: false,
        message: `Video is too long (${Math.round(meta.duration / 60)} minutes). Maximum allowed is ${MAX_VIDEO_DURATION_SECONDS / 60} minutes.`,
      });
    }

    if (meta && meta.is_live) {
      return res.status(400).json({
        success: false,
        message: 'Live streams cannot be imported. Please wait for the stream to end.',
      });
    }

    // Create temp directory
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true });
    }

    // Download video using spawn (non-blocking, argument-safe)
    console.log(`[youtube] Downloading: ${trimmedUrl} → ${tempDir}`);
    await downloadVideo(ytdlpBin, trimmedUrl, tempDir, DOWNLOAD_TIMEOUT_MS);

    // Move downloaded file to final destination
    const tempMp4 = path.join(tempDir, 'video.mp4');
    if (!fs.existsSync(tempMp4)) {
      cleanupDir(tempDir);
      return res.status(500).json({ success: false, message: 'Download completed but video file was not found' });
    }

    // Safe cross-device move: copy then delete
    fs.copyFileSync(tempMp4, destinationPath);

    // Extract suggestions from info.json before cleanup
    const infoJsonPath = path.join(tempDir, 'video.info.json');
    const suggestions = extractSuggestions(infoJsonPath, meta?.duration || 0);

    // Cleanup temp directory
    cleanupDir(tempDir);

    // Probe the final file for metadata
    const probeResult = await new Promise<{ duration: number; width: number; height: number }>((resolve) => {
      ffmpeg.ffprobe(destinationPath, (err, metadata) => {
        if (err || !metadata?.format) {
          resolve({ duration: meta?.duration || 0, width: 0, height: 0 });
          return;
        }
        const videoStream = metadata.streams.find((s) => s.codec_type === 'video');
        resolve({
          duration: metadata.format.duration || 0,
          width: videoStream?.width || 0,
          height: videoStream?.height || 0,
        });
      });
    });

    const suggestionsStr = suggestions.length > 0 ? JSON.stringify(suggestions) : null;

    await runQuery(
      `INSERT INTO videos (id, userId, sourceType, originalName, originalPath, duration, width, height, suggestions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [videoId, userId, 'youtube', trimmedUrl, destinationPath, probeResult.duration, probeResult.width, probeResult.height, suggestionsStr]
    );

    console.log(`[youtube] ✅ Import complete: ${videoId} (${Math.round(probeResult.duration)}s)`);

    return res.json({
      success: true,
      message: 'YouTube video imported successfully',
      data: {
        videoId,
        sourceType: 'youtube',
        originalPath: destinationPath,
        duration: probeResult.duration,
        width: probeResult.width,
        height: probeResult.height,
        suggestions,
      },
    });
  } catch (error: any) {
    console.error('[youtube] Import failed:', error.message);
    cleanupDir(tempDir);

    // Clean up partial destination file
    try { if (fs.existsSync(destinationPath)) fs.unlinkSync(destinationPath); } catch {}

    const userMessage = error.message?.includes('timed out')
      ? 'Download timed out — the video may be too large or your connection is slow'
      : 'Failed to download YouTube video';

    return res.status(500).json({ success: false, message: userMessage });
  }
}
