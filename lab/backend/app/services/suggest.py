"""Build dual Stockfish + human-typical suggestion payload."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import chess

from app.schemas.suggest import MoveLine, SuggestResponse
from app.services.human_model import describe_backend, suggest_human_moves
from app.services.stockfish_worker import (
    PositionAnalysis,
    cached_analyze,
    iter_progressive_analysis,
    line_payload,
)


def _apply_turn(fen: str, turn: str | None) -> str:
    parts = fen.strip().split()
    if len(parts) == 1:
        side = "w" if turn != "black" else "b"
        return f"{parts[0]} {side} - - 0 1"
    if turn == "white":
        parts[1] = "w"
    elif turn == "black":
        parts[1] = "b"
    while len(parts) < 6:
        parts.append(["w", "-", "-", "0", "1"][len(parts) - 1])
    return " ".join(parts[:6])


def _build_response(
    fen_n: str,
    board: chess.Board,
    analysis: PositionAnalysis,
    elo: int,
    *,
    elapsed_ms: int,
    max_ms: int,
    done: bool,
) -> SuggestResponse:
    human = suggest_human_moves(board, analysis, elo)
    sf_payloads = [MoveLine(**line_payload(fen_n, line)) for line in analysis.lines]
    human_payloads = [
        MoveLine(**line_payload(fen_n, line, probability=p)) for line, p in human.lines
    ]
    side: str = "white" if board.turn == chess.WHITE else "black"
    return SuggestResponse(
        fen=fen_n,
        turn=side,  # type: ignore[arg-type]
        elo_band=human.elo_band,
        depth=analysis.depth,
        elapsed_ms=elapsed_ms,
        max_ms=max_ms,
        done=done,
        engine={
            "name": analysis.engine_name,
            "depth": analysis.depth,
            "multipv": analysis.multipv,
            "role": "best_play",
            "search": "progressive-time" if max_ms else "depth",
        },
        human={
            **describe_backend(human.elo_band),
            "note": human.note,
            "role": "human_typical",
        },
        stockfish_best=sf_payloads[0],
        stockfish_lines=sf_payloads,
        human_typical=human_payloads[0],
        human_lines=human_payloads,
        disclaimer=(
            "Two separate suggestions: Stockfish = strongest play; "
            "Human-typical = Elo-band style (Maia-compatible surrogate). "
            "Educational training aid only — not for live rated cheating or "
            "evading anti-cheat detection."
        ),
    )


def suggest_moves(
    fen: str,
    *,
    turn: str | None,
    elo: int,
    depth: int,
    multipv: int,
) -> SuggestResponse:
    fen_n = _apply_turn(fen, turn)
    board = chess.Board(fen_n)
    analysis = cached_analyze(fen_n, multipv, depth)
    if not analysis.lines:
        raise ValueError("No legal moves / empty engine PV")
    return _build_response(
        fen_n,
        board,
        analysis,
        elo,
        elapsed_ms=0,
        max_ms=0,
        done=True,
    )


async def iter_suggest_progressive(
    fen: str,
    *,
    turn: str | None,
    elo: int,
    multipv: int,
    max_time_s: float,
) -> AsyncIterator[SuggestResponse]:
    fen_n = _apply_turn(fen, turn)
    board = chess.Board(fen_n)
    async for analysis, elapsed_ms, max_ms, done in iter_progressive_analysis(
        fen_n,
        multipv=multipv,
        max_time_s=max_time_s,
    ):
        if not analysis.lines:
            continue
        yield _build_response(
            fen_n,
            board,
            analysis,
            elo,
            elapsed_ms=elapsed_ms,
            max_ms=max_ms,
            done=done,
        )


def suggest_to_dict(resp: SuggestResponse) -> dict[str, Any]:
    return resp.model_dump()
