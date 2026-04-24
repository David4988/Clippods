import { Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';
import path from 'path';
import fs from 'fs';
import ffmpeg from 'fluent-ffmpeg';
import { PATHS } from '../config/paths';
import { runQuery } from '../db/database';
import { AuthRequest } from '../middleware/auth.middleware';

ffmpeg.setFfmpegPath(PATHS.ffmpeg);
ffmpeg.setFfprobePath(PATHS.ffprobe);

const MAX_UPLOAD_SIZE = 10 * 1024 * 1024 * 1024; // 10 GB
const ALLOWED_EXTENSIONS = new Set(['.mp4', '.webm', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.m4a', '.flac']);

/**
 * Safely move a file, falling back to copy+delete if rename fails
 * (handles cross-device moves on Windows).
 */
function safeMove(src: string, dest: string): void {
  try {
    fs.renameSync(src, dest);
  } catch (err: any) {
    if (err.code === 'EXDEV') {
      fs.copyFileSync(src, dest);
      fs.unlinkSync(src);
    } else {
      throw err;
    }
  }
}

export default async function uploadController(req: Request, res: Response) {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, message: 'No file uploaded' });
    }

    const file = req.file;

    // Validate file extension
    const ext = path.extname(file.originalname).toLowerCase() || '.mp4';
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      // Clean up the temp file
      try { fs.unlinkSync(file.path); } catch {}
      return res.status(400).json({
        success: false,
        message: `Unsupported file type: ${ext}. Allowed: ${[...ALLOWED_EXTENSIONS].join(', ')}`,
      });
    }

    const videoId = `vid_${uuidv4().replace(/-/g, '').substring(0, 8)}`;
    const finalName = `${videoId}${ext}`;
    const destinationPath = path.join(PATHS.uploads, finalName);

    // Safe cross-device move from temp to uploads
    safeMove(file.path, destinationPath);

    // Extract userId from auth token if present
    const authReq = req as AuthRequest;
    const userId = authReq.user?.id || null;

    // Probe metadata using a promise wrapper
    const probeResult = await new Promise<{ duration: number; width: number; height: number }>((resolve) => {
      ffmpeg.ffprobe(destinationPath, (err, metadata) => {
        if (err || !metadata?.format) {
          resolve({ duration: 0, width: 0, height: 0 });
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

    await runQuery(
      `INSERT INTO videos (id, userId, sourceType, originalName, originalPath, duration, width, height) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [videoId, userId, 'upload', file.originalname, destinationPath, probeResult.duration, probeResult.width, probeResult.height]
    );

    return res.json({
      success: true,
      message: 'Video uploaded successfully',
      data: {
        videoId,
        sourceType: 'upload',
        originalName: file.originalname,
        originalPath: destinationPath,
        duration: probeResult.duration,
        width: probeResult.width,
        height: probeResult.height,
      },
    });
  } catch (error: any) {
    console.error('[upload] Error:', error.message);
    // Clean up temp file on failure
    if (req.file?.path) {
      try { fs.unlinkSync(req.file.path); } catch {}
    }
    return res.status(500).json({ success: false, message: 'Upload error processing video' });
  }
}
