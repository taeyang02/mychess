"""Move Advisor v2 API."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import router as v1_router
from app.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Move Advisor v2",
    version=__version__,
    description="Stockfish best + human-typical (Maia-style) suggestions. Educational only.",
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
        "service": "move-advisor-v2",
        "version": __version__,
        "advisor_v1_untouched": True,
    }
