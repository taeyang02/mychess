"""Runtime settings from environment."""

from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# production | development
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PROD = APP_ENV in {"prod", "production"}

# Comma-separated origins. Empty in prod means same-origin only (no CORS *).
# In development, default to * for Vite.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if _raw_origins:
    ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
elif IS_PROD:
    ALLOWED_ORIGINS = []
else:
    ALLOWED_ORIGINS = ["*"]

# Optional host allowlist, e.g. "advisor.example.com,localhost"
_raw_hosts = os.getenv("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "").strip() or None

# Docs/OpenAPI — off in production unless explicitly enabled.
ENABLE_DOCS = env_bool("ENABLE_DOCS", default=not IS_PROD)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "4096"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(25_000_000)))
