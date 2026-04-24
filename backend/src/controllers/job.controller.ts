import { Request, Response } from 'express';
import { getQuery } from '../db/database';
import fs from 'fs';
import path from 'path';

export default {
  getStatus: async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      if (!id || typeof id !== 'string') {
        return res.status(400).json({ success: false, message: 'Job ID required' });
      }

      const job = await getQuery('SELECT * FROM clip_jobs WHERE id = ?', [id]);
      if (!job) return res.status(404).json({ success: false, message: 'Job not found' });

      const responseData: any = {
        jobId: job.id,
        status: job.status,
        progress: job.progress || 0,
        outputPath: job.outputPath || null,
        errorMessage: job.errorMessage || null,
      };

      if (job.status === 'completed') {
        responseData.downloadUrl = `/api/output/${job.id}`;
      }

      return res.json({ success: true, data: responseData });
    } catch (error: any) {
      console.error('[job] Status error:', error.message);
      return res.status(500).json({ success: false, message: 'Failed to get job status' });
    }
  },

  getOutput: async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const job = await getQuery('SELECT * FROM clip_jobs WHERE id = ?', [id]);

      if (!job || !job.outputPath) {
        return res.status(404).json({ success: false, message: 'Output not ready' });
      }
      if (!fs.existsSync(job.outputPath)) {
        return res.status(404).json({ success: false, message: 'Output file missing' });
      }

      res.download(job.outputPath);
    } catch (error: any) {
      console.error('[job] Download error:', error.message);
      return res.status(500).json({ success: false, message: 'Download failed' });
    }
  },

  streamOriginal: async (req: Request, res: Response) => {
    try {
      const { videoId } = req.params;
      if (!videoId) {
        return res.status(400).json({ success: false, message: 'Video ID required' });
      }

      const video = await getQuery('SELECT * FROM videos WHERE id = ?', [videoId]);
      if (!video) return res.status(404).json({ success: false, message: 'Video not found' });
      if (!fs.existsSync(video.originalPath)) {
        return res.status(404).json({ success: false, message: 'Video file missing from disk' });
      }

      const filePath = video.originalPath;
      const stat = fs.statSync(filePath);
      const fileSize = stat.size;
      const range = req.headers.range;

      // Determine content type from extension
      const ext = path.extname(filePath).toLowerCase();
      const contentType = ext === '.webm' ? 'video/webm' : 'video/mp4';

      if (range) {
        const parts = range.replace(/bytes=/, '').split('-');
        const start = parseInt(parts[0], 10);
        const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

        // Validate parsed range values
        if (!isFinite(start) || start < 0 || start >= fileSize) {
          return res.status(416).json({ success: false, message: 'Invalid range start' });
        }

        const safeEnd = Math.min(isFinite(end) ? end : fileSize - 1, fileSize - 1);
        const chunkSize = safeEnd - start + 1;

        const stream = fs.createReadStream(filePath, { start, end: safeEnd });
        res.writeHead(206, {
          'Content-Range': `bytes ${start}-${safeEnd}/${fileSize}`,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunkSize,
          'Content-Type': contentType,
        });
        stream.pipe(res);
      } else {
        res.writeHead(200, {
          'Content-Length': fileSize,
          'Content-Type': contentType,
          'Accept-Ranges': 'bytes',
        });
        fs.createReadStream(filePath).pipe(res);
      }
    } catch (error: any) {
      console.error('[job] Stream error:', error.message);
      return res.status(500).json({ success: false, message: 'Stream failed' });
    }
  },
};
