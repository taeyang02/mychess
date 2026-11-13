"""Advisor v2 API — dual suggestions (progressive Stockfish search)."""

from __future__ import annotations

import json
import logging
from contextlib import aclosing

import chess
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.suggest import SuggestRequest, SuggestResponse
from app.services.suggest import iter_suggest_progressive, suggest_moves

logger = logging.getLogger("lab.api")
router = APIRouter(prefix="/api/v1")


class SuggestStreamResponse(StreamingResponse):
    async def stream_response(self, send):
        async with aclosing(self.body_iterator):
            await super().stream_response(send)


@router.post("/suggest", response_model=SuggestResponse)
def suggest(body: SuggestRequest) -> SuggestResponse:
    """One-shot depth search (debug / fallback). Prefer /suggest/stream for UI."""
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


@router.post("/suggest/stream")
async def suggest_stream(body: SuggestRequest) -> StreamingResponse:
    """NDJSON stream while Stockfish searches up to max_time_s (default 10s)."""
    try:
        chess.Board(body.fen.split()[0] + " w - - 0 1")
    except ValueError as exc:
        raise HTTPException(400, f"Invalid FEN: {exc}") from exc

    async def gen():
        try:
            async for update in iter_suggest_progressive(
                body.fen,
                turn=body.turn,
                elo=body.elo,
                multipv=body.multipv,
                max_time_s=body.max_time_s,
            ):
                yield json.dumps(update.model_dump(), ensure_ascii=False) + "\n"
        except FileNotFoundError as exc:
            yield json.dumps({"error": str(exc)}) + "\n"
        except Exception as exc:
            logger.exception("suggest stream failed")
            yield json.dumps({"error": f"Suggestion failed: {exc}"}) + "\n"

    return SuggestStreamResponse(gen(), media_type="application/x-ndjson")


@router.get("/meta")
def meta() -> dict:
    return {
        "product": "Move Advisor v2",
        "modes": ["stockfish_progressive", "human_typical_maia_style"],
        "note": "Stockfish searches up to 10s (shallow→deep). Educational dual suggestions.",
    }
