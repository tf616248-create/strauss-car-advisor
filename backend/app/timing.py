"""Timing logs: how long each part of an answer takes (data load, each model call, each tool).

One line per step, e.g. "⏱ model gemini_2: 4.21s" or "⏱ tool calculate: 0.003s (ValueError)".
The server prints them (app/api/server.py); tests read them with caplog.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

log = logging.getLogger("app.timing")
log.setLevel(logging.INFO)


@contextmanager
def timed(label: str):
    start = time.perf_counter()
    try:
        yield
    except BaseException as e:
        log.info("⏱ %s: %.3fs (%s)", label, time.perf_counter() - start, type(e).__name__)
        raise
    log.info("⏱ %s: %.3fs", label, time.perf_counter() - start)
