"""Background worker that processes queued runs one at a time."""

from __future__ import annotations

import logging
import threading

from shortstock import db, pipeline

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, idle_seconds: float = 2.0) -> None:
        self.idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="shortstock-worker", daemon=True)

    def start(self) -> None:
        db.requeue_interrupted_runs()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        logger.info("worker started")
        while not self._stop.is_set():
            try:
                processed = pipeline.run_next()
            except Exception:
                logger.exception("worker error")
                processed = None
            if processed is None:
                self._wake.wait(self.idle_seconds)
                self._wake.clear()
