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

# Statuses from which a job will never move again.
TERMINAL_JOB_STATUSES = {"completed", "error", "cancelled"}

class JobWorkerPool:
    def __init__(self, num_workers: int = MAX_CONCURRENT_JOBS):
        self.num_workers = num_workers
        self.task_queue = queue.Queue(maxsize=MAX_QUEUED_JOBS)
        self.workers = []
        self.shutdown_event = threading.Event()
        # RLock, not Lock: submit_job() holds this while calling start(), which
        # re-acquires it. With a plain Lock that self-deadlocks the request thread.
        self._lock = threading.RLock()
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
        # Workers poll the queue with a 1s timeout, so they observe shutdown_event
        # within ~1s. Join them so a later start() does not leak threads.
        for t in self.workers:
            if t.is_alive():
                t.join(timeout=3.0)
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
            except BaseException as e:
                # KeyboardInterrupt / SystemExit: log, let the finally block mark
                # the job terminal, then re-raise so shutdown is not swallowed.
                logger.error("Job %s aborted by %s", job_id, type(e).__name__)
                raise
            finally:
                self.task_queue.task_done()
                self._ensure_terminal_state(job_id)
                logger.info("Worker thread completed processing task for job %s", job_id)

    @staticmethod
    def _ensure_terminal_state(job_id: str) -> None:
        """
        Safety net: a job must never be left in a non-terminal state once its
        worker task has returned. Without this, any failure path the task itself
        did not catch leaves the job stuck at 'queued'/'processing' forever and
        the frontend polls it until the user gives up.
        """
        from job_manager import get_job, update_job

        job = get_job(job_id)
        if job is None:
            return
        if job.get("status") in TERMINAL_JOB_STATUSES:
            return

        logger.error(
            "Job %s finished in non-terminal state %r — forcing 'error'.",
            job_id,
            job.get("status"),
        )
        update_job(
            job_id,
            status="error",
            error="Processing stopped unexpectedly. Please try again.",
            message="Processing failed",
        )

# Global worker pool instance
worker_pool = JobWorkerPool()
