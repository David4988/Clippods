"""
services/job_worker.py — Bounded background worker thread pool for processing jobs.
Avoids Celery/Redis by running a local queue.Queue worker loop.
"""
import logging
import queue
import threading
import time
from typing import Callable, Any

from config import MAX_CONCURRENT_JOBS, MAX_QUEUED_JOBS

logger = logging.getLogger(__name__)

import sys

# Auto-detect testing environment
IS_TESTING = "pytest" in sys.modules

class JobWorkerPool:
    def __init__(self, num_workers: int = MAX_CONCURRENT_JOBS):
        self.num_workers = num_workers
        self.task_queue = queue.Queue(maxsize=MAX_QUEUED_JOBS)
        self.workers = []
        self.shutdown_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self.synchronous = IS_TESTING

    def start(self):
        """Start the worker thread pool."""
        if self.synchronous:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
            self.shutdown_event.clear()

        logger.info("Starting JobWorkerPool with %d worker threads...", self.num_workers)
        for i in range(self.num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"ClipPodsWorker-{i}",
                daemon=True
            )
            t.start()
            self.workers.append(t)

    def stop(self):
        """Signal workers to stop and wait for them to finish."""
        if self.synchronous:
            return
        with self._lock:
            if not self._running:
                return
            self._running = False
            self.shutdown_event.set()

        logger.info("Stopping JobWorkerPool...")
        # Wake up any blocked queue.get() calls
        # Join worker threads
        for t in self.workers:
            if t.is_alive():
                # worker thread will exit on next timeout or empty check
                pass
        self.workers.clear()
        logger.info("JobWorkerPool stopped.")

    def submit_job(self, job_id: str, fn: Callable[[], Any]) -> bool:
        """
        Submit a background job task to the queue.
        Returns True if successfully queued, False if queue is full.
        """
        if self.synchronous:
            logger.info("Running job %s synchronously for testing", job_id)
            fn()
            return True

        # Auto-start worker pool if not running (e.g. inside test runners bypassing FastAPI startup)
        with self._lock:
            if not self._running:
                self.start()

        try:
            self.task_queue.put_nowait((job_id, fn))
            logger.info("Job %s successfully queued.", job_id)
            return True
        except queue.Full:
            logger.warning("Job queue is full (max size %d). Rejecting job %s.", MAX_QUEUED_JOBS, job_id)
            return False

    def _worker_loop(self):
        """Worker thread execution loop."""
        while not self.shutdown_event.is_set():
            try:
                # Poll queue with 1-second timeout so we regularly check shutdown_event
                task = self.task_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            job_id, fn = task
            logger.info("Worker thread starting job %s", job_id)
            
            try:
                # Run the task function
                fn()
            except Exception as e:
                logger.error("Error executing job %s in worker pool: %s", job_id, e, exc_info=True)
            finally:
                self.task_queue.task_done()
                logger.info("Worker thread completed processing task for job %s", job_id)

# Global worker pool instance
worker_pool = JobWorkerPool()
