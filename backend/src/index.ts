import app from './app';
import { ENV } from './config/env';
import { checkRedisHealth } from './queue/clip.queue';
import { initFirebase } from './config/firebase';
import { startCleanupScheduler } from './services/cleanup';

async function start() {
  initFirebase();
  
  // Start periodic temp file cleanup
  startCleanupScheduler();
  // Check Redis health at startup — warn but don't crash
  const redisOk = await checkRedisHealth();
  if (redisOk) {
    console.log('[startup] ✅ Redis is reachable — clip queue is ready');
  } else {
    console.warn('[startup] ⚠️  Redis is NOT reachable — clip generation will fail until Redis is available');
    console.warn('[startup]    Run: docker compose up -d    (to start Redis)');
  }

  app.listen(ENV.PORT, () => {
    console.log(`[startup] Backend is running at http://localhost:${ENV.PORT}`);
  });
}

start().catch((err) => {
  console.error('[startup] Fatal error:', err);
  process.exit(1);
});
