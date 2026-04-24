import sqlite3 from 'sqlite3';
import { PATHS } from '../config/paths';

export const dbPath = PATHS.db;

const db = new sqlite3.Database(dbPath, (err) => {
  if (err) {
    console.error('[db] Error opening database:', err.message);
  } else {
    db.serialize(() => {
      // WAL mode prevents locking during concurrent BullMQ renders
      db.run('PRAGMA journal_mode = WAL;');
      db.run('PRAGMA busy_timeout = 10000;');

      db.run(`CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspaceName TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP
      )`);

      db.run(`CREATE TABLE IF NOT EXISTS waitlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        role TEXT,
        platform TEXT,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP
      )`);

      db.run(`CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        userId INTEGER,
        sourceType TEXT NOT NULL,
        originalName TEXT,
        originalPath TEXT NOT NULL,
        duration REAL,
        width INTEGER,
        height INTEGER,
        suggestions TEXT,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP
      )`);

      db.run(`CREATE TABLE IF NOT EXISTS clip_jobs (
        id TEXT PRIMARY KEY,
        videoId TEXT NOT NULL,
        userId INTEGER,
        startTime REAL NOT NULL,
        endTime REAL NOT NULL,
        mode TEXT NOT NULL,
        status TEXT NOT NULL,
        progress INTEGER DEFAULT 0,
        inputPath TEXT NOT NULL,
        outputPath TEXT,
        errorMessage TEXT,
        config TEXT,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
      )`);

      db.run(`CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        message TEXT NOT NULL,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP
      )`);

      // Safe column additions for schema evolution (check existence first)
      db.all("PRAGMA table_info(videos)", (err, columns: any[]) => {
        if (err) return;
        const colNames = new Set(columns.map((c: any) => c.name));
        if (!colNames.has('userId')) db.run('ALTER TABLE videos ADD COLUMN userId INTEGER');
        if (!colNames.has('suggestions')) db.run('ALTER TABLE videos ADD COLUMN suggestions TEXT');
      });

      db.all("PRAGMA table_info(clip_jobs)", (err, columns: any[]) => {
        if (err) return;
        const colNames = new Set(columns.map((c: any) => c.name));
        if (!colNames.has('userId')) db.run('ALTER TABLE clip_jobs ADD COLUMN userId INTEGER');
        if (!colNames.has('config')) db.run('ALTER TABLE clip_jobs ADD COLUMN config TEXT');
      });
    });
  }
});

export default db;

export function runQuery(query: string, params: any[] = []): Promise<any> {
  return new Promise((resolve, reject) => {
    db.run(query, params, function(err) {
      if (err) reject(err);
      else resolve(this);
    });
  });
}

export function getQuery(query: string, params: any[] = []): Promise<any> {
  return new Promise((resolve, reject) => {
    db.get(query, params, function(err, row) {
      if (err) reject(err);
      else resolve(row);
    });
  });
}

export function allQuery(query: string, params: any[] = []): Promise<any[]> {
  return new Promise((resolve, reject) => {
    db.all(query, params, function(err, rows) {
      if (err) reject(err);
      else resolve(rows || []);
    });
  });
}
