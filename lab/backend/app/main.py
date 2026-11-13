"""Anti-Cheat Lab API — separate process from Move Advisor."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import router as v1_router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lab")

app = FastAPI(
    title="Chess Human Behavior & Anti-Cheat Lab",
    version=__version__,
    description=(
        "Offline research lab for human vs engine behavior. "
        "No live-game move advice. Anomaly scores are not cheat verdicts."
    ),
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "anticheat-lab",
        "version": __version__,
        "advisor_untouched": True,
    }
