"""Wall-clock and peak-RSS measurement for evaluation stages."""
from __future__ import annotations

import threading
import time

import psutil


class Measure:
    """
    Context manager that records wall time and peak resident memory of this
    process while the block runs. Child processes (FFmpeg) and out-of-process
    model servers are not included; stages that use them record those separately.
    """

    def __init__(self, interval_s: float = 0.25):
        self.interval_s = interval_s
        self.wall_s: float | None = None
        self.peak_rss_mb: float | None = None
        self.start_rss_mb: float | None = None
        self._stop = threading.Event()
        self._proc = psutil.Process()
        self._peak = 0

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_s):
            self._peak = max(self._peak, self._proc.memory_info().rss)

    def __enter__(self) -> "Measure":
        rss = self._proc.memory_info().rss
        self.start_rss_mb = round(rss / 2**20, 1)
        self._peak = rss
        self._t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._sample, name="eval-rss-sampler", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self._peak = max(self._peak, self._proc.memory_info().rss)
        self.wall_s = round(time.perf_counter() - self._t0, 3)
        self.peak_rss_mb = round(self._peak / 2**20, 1)

    def as_dict(self) -> dict:
        return {"wall_s": self.wall_s, "start_rss_mb": self.start_rss_mb, "peak_rss_mb": self.peak_rss_mb}
