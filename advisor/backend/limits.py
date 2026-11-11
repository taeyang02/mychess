"""CPU / concurrency guards (no auth) to reduce DoS impact."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict, deque
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
_rate_hits: OrderedDict[str, deque[float]] = OrderedDict()
_RATE_WINDOW_S = 60.0
_MAX_RATE_KEYS = _env_int("MAX_RATE_LIMIT_KEYS", 10_000)


def _prune(bucket: deque[float], now: float, window_s: float) -> None:
    while bucket and now - bucket[0] > window_s:
        bucket.popleft()


def check_rate_limit(bucket_key: str, max_calls: int) -> None:
    """Raise BusyError if this key exceeded max_calls in the window."""
    with _rate_lock:
        now = time.monotonic()
        while _rate_hits:
            oldest = next(iter(_rate_hits.values()))
            if now - oldest[-1] <= _RATE_WINDOW_S:
                break
            _rate_hits.popitem(last=False)

        bucket = _rate_hits.get(bucket_key)
        if bucket is None:
            if len(_rate_hits) >= _MAX_RATE_KEYS:
                raise BusyError("Too many requests — slow down and try again.")
            bucket = _rate_hits[bucket_key] = deque()
        _prune(bucket, now, _RATE_WINDOW_S)
        if len(bucket) >= max_calls:
            raise BusyError("Too many requests — slow down and try again.")
        bucket.append(now)
        _rate_hits.move_to_end(bucket_key)


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
    """Use the client address resolved by the ASGI server and trusted proxies."""
    return request.client.host if request.client else "unknown"
