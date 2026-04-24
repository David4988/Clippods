import { Request, Response } from 'express';
import { getQuery } from '../db/database';

export const getVideoMetadata = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    if (!id) {
      return res.status(400).json({ success: false, message: 'Video ID required' });
    }

    const video = await getQuery('SELECT * FROM videos WHERE id = ?', [id]);
    if (!video) {
        return res.status(404).json({ success: false, message: 'Video not found' });
    }

    const suggestions = video.suggestions ? JSON.parse(video.suggestions) : [];

    return res.json({
        success: true,
        data: {
            videoId: video.id,
            sourceType: video.sourceType,
            duration: video.duration,
            width: video.width,
            height: video.height,
            suggestions
        }
    });

  } catch (err: any) {
    console.error('Video metadata error:', err);
    return res.status(500).json({ success: false, message: 'Internal server error' });
  }
};
