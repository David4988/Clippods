import { Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { runQuery, getQuery } from '../db/database';
import { addClipJob } from '../queue/clip.queue';
import { AuthRequest } from '../middleware/auth.middleware';

const MAX_SEGMENTS = 5;
const MAX_CLIP_DURATION_SECONDS = 3600; // 1 hour per clip segment

export default async function clipController(req: Request, res: Response) {
  try {
    const { videoId, startTime, endTime, mode, segments, quality, ratio, format } = req.body;

    if (!videoId || typeof videoId !== 'string') {
      return res.status(400).json({ success: false, message: 'Missing or invalid videoId' });
    }

    const clipMode = mode || 'accurate';
    if (!['fast', 'accurate'].includes(clipMode)) {
      return res.status(400).json({ success: false, message: 'Mode must be "fast" or "accurate"' });
    }

    const video = await getQuery('SELECT * FROM videos WHERE id = ?', [videoId]);
    if (!video) {
      return res.status(404).json({ success: false, message: 'Video not found' });
    }

    const videoDuration = video.duration || 0;

    // Build and validate segments
    const rawSegments = (segments && Array.isArray(segments) && segments.length > 0)
      ? segments
      : [{ start: startTime != null ? Number(startTime) : 0, end: endTime != null ? Number(endTime) : 10 }];

    if (rawSegments.length > MAX_SEGMENTS) {
      return res.status(400).json({ success: false, message: `Maximum ${MAX_SEGMENTS} segments allowed` });
    }

    // Validate every segment
    for (let i = 0; i < rawSegments.length; i++) {
      const seg = rawSegments[i];
      const start = Number(seg.start);
      const end = Number(seg.end);

      if (!isFinite(start) || !isFinite(end)) {
        return res.status(400).json({ success: false, message: `Segment ${i + 1}: start and end must be valid numbers` });
      }
      if (start < 0) {
        return res.status(400).json({ success: false, message: `Segment ${i + 1}: start time cannot be negative` });
      }
      if (end <= start) {
        return res.status(400).json({ success: false, message: `Segment ${i + 1}: end time must be after start time` });
      }
      if (videoDuration > 0 && end > videoDuration + 1) {
        return res.status(400).json({ success: false, message: `Segment ${i + 1}: end time exceeds video duration` });
      }
      if ((end - start) > MAX_CLIP_DURATION_SECONDS) {
        return res.status(400).json({ success: false, message: `Segment ${i + 1}: clip duration exceeds maximum of ${MAX_CLIP_DURATION_SECONDS / 60} minutes` });
      }
    }

    const configObj = {
      quality: quality || '720p',
      ratio: ratio || 'original',
      format: format || 'video',
    };
    const configStr = JSON.stringify(configObj);

    // Extract userId from auth token
    const authReq = req as AuthRequest;
    const userId = authReq.user?.id || null;

    const jobIds: string[] = [];

    for (const segment of rawSegments) {
      const jobId = `job_${uuidv4().replace(/-/g, '').substring(0, 8)}`;
      jobIds.push(jobId);

      const segStart = Number(segment.start);
      const segEnd = Number(segment.end);

      await runQuery(
        `INSERT INTO clip_jobs (id, videoId, userId, startTime, endTime, mode, status, inputPath, config) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [jobId, videoId, userId, segStart, segEnd, clipMode, 'pending', video.originalPath, configStr]
      );

      await addClipJob(jobId, {
        jobId,
        videoId,
        startTime: segStart,
        endTime: segEnd,
        mode: clipMode,
        inputPath: video.originalPath,
        config: configObj,
      });
    }

    return res.json({
      success: true,
      message: 'Clip jobs created',
      data: { jobIds, status: 'pending' },
    });
  } catch (error: any) {
    console.error('[clip] Create error:', error.message);
    const message = error?.message?.includes('Redis')
      ? 'Redis is unavailable — please ensure Redis is running (docker compose up -d)'
      : 'Failed to create clip job';
    return res.status(500).json({ success: false, message });
  }
}
