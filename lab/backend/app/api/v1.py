"""Advisor v2 API — dual suggestions only (no live anti-cheat evasion)."""

from __future__ import annotations

import logging

import chess
from fastapi import APIRouter, HTTPException

from app.schemas.suggest import SuggestRequest, SuggestResponse
from app.services.suggest import suggest_moves

logger = logging.getLogger("lab.api")
router = APIRouter(prefix="/api/v1")


@router.post("/suggest", response_model=SuggestResponse)
def suggest(body: SuggestRequest) -> SuggestResponse:
    try:
        chess.Board(body.fen.split()[0] + " w - - 0 1")
    except ValueError as exc:
        raise HTTPException(400, f"Invalid FEN: {exc}") from exc

    try:
        return suggest_moves(
            body.fen,
            turn=body.turn,
            elo=body.elo,
            depth=body.depth,
            multipv=body.multipv,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("suggest failed")
        raise HTTPException(500, f"Suggestion failed: {exc}") from exc


@router.get("/meta")
def meta() -> dict:
    return {
        "product": "Move Advisor v2",
        "modes": ["stockfish_best", "human_typical_maia_style"],
        "note": "Educational dual suggestions. Not an anti-cheat evasion tool.",
    }
