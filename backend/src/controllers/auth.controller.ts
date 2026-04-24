import { Request, Response } from 'express';
import { runQuery, getQuery } from '../db/database';
import { AuthRequest } from '../middleware/auth.middleware';

export async function syncUser(req: AuthRequest, res: Response) {
  try {
    const { workspaceName } = req.body;
    if (workspaceName && req.user && req.user.id) {
      await runQuery('UPDATE users SET workspaceName = ? WHERE id = ?', [workspaceName, req.user.id]);
    }
    
    if (req.user && req.user.id) {
      const user = await getQuery('SELECT id, workspaceName, email FROM users WHERE id = ?', [req.user.id]);
      return res.json({ success: true, message: 'User synced successfully', data: { user } });
    }
    return res.status(400).json({ success: false, message: 'Invalid user' });
  } catch (error) {
    console.error('Sync error:', error);
    res.status(500).json({ success: false, message: 'Sync failed' });
  }
}

export async function getMe(req: AuthRequest, res: Response) {
  try {
    if (!req.user || !req.user.id) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }
    
    const user = await getQuery('SELECT id, workspaceName, email, createdAt FROM users WHERE id = ?', [req.user.id]);
    if (!user) {
      return res.status(404).json({ success: false, message: 'User not found' });
    }

    res.json({ success: true, data: user });
  } catch (error) {
    console.error('getMe error:', error);
    res.status(500).json({ success: false, message: 'Failed to fetch user profile' });
  }
}

