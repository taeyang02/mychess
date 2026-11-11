"""Client-safe error messages (no paths / internals)."""

from __future__ import annotations

import logging
import re

from engine import EngineError

logger = logging.getLogger("advisor")

_PATH_RE = re.compile(r"(/[^\s:]+|[A-Za-z]:\\[^\s]+)")


def public_engine_error(exc: EngineError) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "not found" in lower or "not a file" in lower:
        return "Chess engine unavailable on server"
    if "invalid fen" in lower:
        return "Invalid board position"
    if "no white king" in lower or "no black king" in lower or "too many kings" in lower:
        return msg  # already user-facing
    if "too many" in lower or "back rank" in lower or "backrank" in lower:
        return msg
    if "no legal moves" in lower or "empty pv" in lower:
        return "No legal moves for this position"
    if "busy" in lower:
        return msg
    # Strip filesystem paths just in case.
    cleaned = _PATH_RE.sub("[path]", msg)
    if cleaned != msg:
        logger.warning("Sanitized engine error: %s", msg)
        return "Analysis failed for this position"
    return cleaned[:200]


def log_exception(context: str, exc: BaseException) -> None:
    logger.exception("%s: %s", context, exc)
