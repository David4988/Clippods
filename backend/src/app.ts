import express from 'express';
import cors from 'cors';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { v4 as uuidv4 } from 'uuid';
import { PATHS } from './config/paths';
import { ENV } from './config/env';
import uploadController from './controllers/upload.controller';
import youtubeController from './controllers/youtube.controller';
import clipController from './controllers/clip.controller';
import jobController from './controllers/job.controller';
import waitlistController from './controllers/waitlist.controller';
import { getVideoMetadata } from './controllers/video.controller';
import { syncUser, getMe } from './controllers/auth.controller';
import { requireAuth, optionalAuth } from './middleware/auth.middleware';
import rateLimit from 'express-rate-limit';
import { requestIdMiddleware, requestLoggerMiddleware, logger } from './utils/logger';

const app = express();

// CORS — configurable via env, defaults to allow all for local dev
const corsOrigins = ENV.CORS_ORIGIN;
app.use(cors({
  origin: corsOrigins === '*' ? true : corsOrigins.split(',').map(s => s.trim()),
  credentials: true,
}));

app.use(express.json({ limit: '1mb' }));
app.use(requestIdMiddleware);
app.use(requestLoggerMiddleware);

// Ensure required directories exist
[PATHS.uploads, PATHS.outputs, PATHS.temp, PATHS.logs].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// Rate limiting — separate limits for different endpoint classes
const generalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 200,
  message: { success: false, message: 'Too many requests, please try again later.' },
});

const uploadLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: { success: false, message: 'Upload rate limit reached. Please wait before uploading again.' },
});

app.use(generalLimiter);

// Multer config: UUID-based filenames to prevent collision
const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, PATHS.temp),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    cb(null, `tmp_${uuidv4().replace(/-/g, '').substring(0, 12)}${ext}`);
  },
});
const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 * 1024 }, // 10 GB
});

// --- Health Check ---
app.get('/api/health', (_req, res) => {
  res.json({ success: true, status: 'ok', timestamp: new Date().toISOString() });
});

// --- Upload & Import ---
app.post('/api/upload', uploadLimiter, optionalAuth, upload.single('file'), uploadController);
app.post('/api/youtube/import', uploadLimiter, optionalAuth, youtubeController);

// --- Auth ---
app.post('/api/auth/sync', requireAuth, syncUser);
app.get('/api/auth/me', requireAuth, getMe);

// --- Clip Creation ---
app.post('/api/clip/create', requireAuth, clipController);

// --- Video Context ---
app.get('/api/video/:id', optionalAuth, getVideoMetadata);

// --- Job Status ---
app.get('/api/job/:id/status', jobController.getStatus);

// --- Video Streaming (must be before /api/output/:id to prevent route collision) ---
app.get('/api/output/stream/:videoId', jobController.streamOriginal);

// --- Download (protected) ---
app.get('/api/output/:id', requireAuth, jobController.getOutput);

// --- Waitlist ---
app.post('/api/waitlist', waitlistController);

// --- Global Error Handler ---
app.use((err: any, req: express.Request, res: express.Response, _next: express.NextFunction) => {
  logger.error(err.message || String(err), { reqId: req.reqId, status: err.status || 500 });
  res.status(err.status || 500).json({ success: false, message: 'Internal server error' });
});

export default app;
