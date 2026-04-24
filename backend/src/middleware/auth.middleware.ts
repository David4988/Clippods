import { Request, Response, NextFunction } from 'express';
import { firebaseAdmin } from '../config/firebase';
import { getQuery, runQuery } from '../db/database';

export interface AuthRequest extends Request {
  user?: { id: number; email: string; workspaceName?: string; firebaseUid?: string };
}

export async function requireAuth(req: AuthRequest, res: Response, next: NextFunction) {
  let token = req.headers.authorization?.split(' ')[1];

  if (!token && req.query.token) {
    token = req.query.token as string;
  }

  if (!token) {
    return res.status(401).json({ success: false, message: 'Authentication required' });
  }

  try {
    const decodedToken = await firebaseAdmin.auth().verifyIdToken(token);
    
    // Auto-sync user to SQLite on first seen
    let user = await getQuery('SELECT id, email, workspaceName FROM users WHERE email = ?', [decodedToken.email]);
    if (!user && decodedToken.email) {
      await runQuery('INSERT INTO users (email, password, workspaceName) VALUES (?, ?, ?)', [decodedToken.email, 'firebase_oauth', '']);
      user = await getQuery('SELECT id, email, workspaceName FROM users WHERE email = ?', [decodedToken.email]);
    }
    
    if (!user) {
      return res.status(401).json({ success: false, message: 'Invalid user mapping' });
    }

    req.user = { id: user.id, email: user.email, workspaceName: user.workspaceName || '', firebaseUid: decodedToken.uid };
    next();
  } catch (error) {
    console.error('Firebase token verification failed:', error);
    return res.status(401).json({ success: false, message: 'Invalid or expired token' });
  }
}

export async function optionalAuth(req: AuthRequest, res: Response, next: NextFunction) {
  let token = req.headers.authorization?.split(' ')[1];

  if (!token && req.query.token) {
    token = req.query.token as string;
  }

  if (token) {
    try {
      const decodedToken = await firebaseAdmin.auth().verifyIdToken(token);
      let user = await getQuery('SELECT id, email, workspaceName FROM users WHERE email = ?', [decodedToken.email]);
      if (!user && decodedToken.email) {
        await runQuery('INSERT INTO users (email, password, workspaceName) VALUES (?, ?, ?)', [decodedToken.email, 'firebase_oauth', '']);
        user = await getQuery('SELECT id, email, workspaceName FROM users WHERE email = ?', [decodedToken.email]);
      }
      if (user) {
        req.user = { id: user.id, email: user.email, workspaceName: user.workspaceName || '', firebaseUid: decodedToken.uid };
      }
    } catch {
      // Token invalid — proceed without user
    }
  }

  next();
}

