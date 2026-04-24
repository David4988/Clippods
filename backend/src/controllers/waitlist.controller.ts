import { Request, Response } from 'express';
import { runQuery, getQuery } from '../db/database';

export default async function waitlistController(req: Request, res: Response) {
  const { email, role, platform } = req.body;
  if (!email) return res.status(400).json({ success: false, message: 'Email required' });

  try {
    const existing = await getQuery('SELECT * FROM waitlist WHERE email = ?', [email]);
    if (existing) {
        return res.json({ success: true, message: 'Already on waitlist', data: { id: existing.id, email } });
    }

    const result = await runQuery(
      `INSERT INTO waitlist (email, role, platform) VALUES (?, ?, ?)`,
      [email, role, platform]
    );

    const inserted = await getQuery('SELECT * FROM waitlist WHERE email = ?', [email]);

    return res.json({
      success: true,
      message: 'Joined waitlist successfully',
      data: {
        id: inserted.id,
        email: inserted.email
      }
    });
  } catch (error) {
    return res.status(500).json({ success: false, message: 'Waitlist error' });
  }
}
