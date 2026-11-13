"""Build dual Stockfish + human-typical suggestion payload."""

from __future__ import annotations

import chess

from app.schemas.suggest import MoveLine, SuggestResponse
from app.services.human_model import describe_backend, suggest_human_moves
from app.services.stockfish_worker import cached_analyze, line_payload


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
    if not board.is_valid():
        # Still try analysis; python-chess may raise
        pass

    analysis = cached_analyze(fen_n, multipv, depth)
    if not analysis.lines:
        raise ValueError("No legal moves / empty engine PV")

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
        engine={
            "name": analysis.engine_name,
            "depth": analysis.depth,
            "multipv": analysis.multipv,
            "role": "best_play",
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
