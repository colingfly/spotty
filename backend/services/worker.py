# backend/services/worker.py
"""
Background completion worker.

Previously a generation only finished when the browser happened to poll the
status endpoint, so closing the tab left tracks stuck at "pending" forever.
This daemon thread polls ACE-Step for every active generation and saves the
audio as soon as it's ready, independent of any client.
"""
from __future__ import annotations

import logging
import threading
import time

from config import settings

log = logging.getLogger("spotty.worker")

_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop() -> None:
    from db import SessionLocal
    from services.generation_service import sync_active

    log.info("Completion worker started (interval=%ss)", settings.worker_interval_seconds)
    while not _stop.is_set():
        db = SessionLocal()
        try:
            n = sync_active(db)
            if n:
                log.info("Worker updated %d generation(s)", n)
        except Exception as e:  # never let the loop die
            log.warning("Worker tick failed: %s", e)
        finally:
            db.close()
        _stop.wait(settings.worker_interval_seconds)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="trill-completion-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
