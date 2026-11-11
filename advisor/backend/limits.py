"""CPU / concurrency guards (no auth) to reduce DoS impact."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Iterator


class BusyError(Exception):
    """Raised when the server is at capacity."""


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# Cap parallel Stockfish processes and chessvision detects.
MAX_ENGINE = _env_int("MAX_ENGINE_CONCURRENCY", 2)
MAX_DETECT = _env_int("MAX_DETECT_CONCURRENCY", 1)

# Per-IP request budgets (rolling window).
ANALYZE_RATE = _env_int("ANALYZE_RATE_PER_MIN", 30)
DETECT_RATE = _env_int("DETECT_RATE_PER_MIN", 20)

_engine_slots = threading.BoundedSemaphore(MAX_ENGINE)
_detect_slots = threading.BoundedSemaphore(MAX_DETECT)
_rate_lock = threading.Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def _prune(bucket: deque[float], now: float, window_s: float) -> None:
    while bucket and now - bucket[0] > window_s:
        bucket.popleft()


def check_rate_limit(bucket_key: str, max_calls: int, window_s: float = 60.0) -> None:
    """Raise BusyError if this key exceeded max_calls in the window."""
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_hits[bucket_key]
        _prune(bucket, now, window_s)
        if len(bucket) >= max_calls:
            raise BusyError("Too many requests — slow down and try again.")
        bucket.append(now)


@contextmanager
def engine_slot() -> Iterator[None]:
    if not _engine_slots.acquire(blocking=False):
        raise BusyError(
            f"Stockfish busy (max {MAX_ENGINE} concurrent). Try again in a moment."
        )
    try:
        yield
    finally:
        _engine_slots.release()


@contextmanager
def detect_slot() -> Iterator[None]:
    if not _detect_slots.acquire(blocking=False):
        raise BusyError(
            f"Detection busy (max {MAX_DETECT} concurrent). Try again in a moment."
        )
    try:
        yield
    finally:
        _detect_slots.release()


def client_ip(request) -> str:
    """Best-effort client IP (honors first X-Forwarded-For hop if present)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
