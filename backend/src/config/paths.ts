import path from 'path';
import fs from 'fs';
import os from 'os';

// Resolve project root relative to this file: config/ -> src/ -> backend/ -> project root
const rootDir = path.resolve(__dirname, '..', '..', '..');

/**
 * Resolve a tool path by checking an ordered list of candidate locations.
 * Falls back to the bare binary name (relies on system PATH at runtime).
 */
function resolveTool(candidates: string[], fallbackBinary: string): string {
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return fallbackBinary;
}

const home = os.homedir();
const wingetLinks = path.join(home, 'AppData', 'Local', 'Microsoft', 'WinGet', 'Links');

export const PATHS = {
  root: rootDir,
  uploads: path.join(rootDir, 'uploads'),
  outputs: path.join(rootDir, 'outputs'),
  temp: path.join(rootDir, 'temp'),
  logs: path.join(rootDir, 'logs'),
  db: path.join(rootDir, 'backend', 'src', 'db', 'clippods.sqlite'),
  ytdlp: resolveTool([
    "D:\\tools\\yt-dlp\\yt-dlp.exe",
    path.join(wingetLinks, 'yt-dlp.exe'),
    path.join(home, 'AppData', 'Local', 'Programs', 'Python', 'Python311', 'Scripts', 'yt-dlp.exe'),
  ], "yt-dlp"),
  ffmpeg: resolveTool([
    "D:\\tools\\ffmpeg\\bin\\ffmpeg.exe",
    path.join(wingetLinks, 'ffmpeg.exe'),
  ], "ffmpeg"),
  ffprobe: resolveTool([
    "D:\\tools\\ffmpeg\\bin\\ffprobe.exe",
    path.join(wingetLinks, 'ffprobe.exe'),
  ], "ffprobe"),
};
