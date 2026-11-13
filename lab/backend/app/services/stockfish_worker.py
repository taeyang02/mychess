"""Stockfish MultiPV analysis for Advisor v2."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import chess.engine

from app.config import resolve_stockfish, settings


@dataclass(frozen=True)
class EngineLine:
    rank: int
    uci: str
    san: str
    score_cp: int | None
    mate: int | None
    pv: list[str]


@dataclass
class PositionAnalysis:
    fen: str
    depth: int
    multipv: int
    engine_name: str
    lines: list[EngineLine]


def _eval_text(cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"M{mate}"
    if cp is None:
        return "—"
    pawns = cp / 100.0
    sign = "+" if pawns > 0 else ""
    return f"{sign}{pawns:.2f}"


def analyze_position(
    fen: str,
    *,
    multipv: int | None = None,
    depth: int | None = None,
    engine_path: Path | None = None,
) -> PositionAnalysis:
    multipv = multipv or settings.multipv
    depth = depth or settings.analysis_depth
    path = engine_path or resolve_stockfish()
    board = chess.Board(fen)
    limit = chess.engine.Limit(depth=depth)

    with chess.engine.SimpleEngine.popen_uci(str(path)) as engine:
        info_list = engine.analyse(board, limit, multipv=multipv)
        if isinstance(info_list, dict):
            info_list = [info_list]
        engine_name = engine.id.get("name", "Stockfish")
        lines: list[EngineLine] = []
        for idx, info in enumerate(info_list, start=1):
            pv_moves: list[chess.Move] = info.get("pv") or []
            if not pv_moves:
                continue
            best = pv_moves[0]
            score = info.get("score")
            cp = mate = None
            if score is not None:
                pov = score.pov(board.turn)
                if pov.is_mate():
                    mate = pov.mate()
                else:
                    cp = pov.score(mate_score=100000)
            tmp = board.copy(stack=False)
            try:
                san = tmp.san(best)
            except ValueError:
                san = best.uci()
            lines.append(
                EngineLine(
                    rank=idx,
                    uci=best.uci(),
                    san=san,
                    score_cp=cp,
                    mate=mate,
                    pv=[m.uci() for m in pv_moves[:6]],
                )
            )

    return PositionAnalysis(
        fen=fen,
        depth=depth,
        multipv=multipv,
        engine_name=engine_name,
        lines=lines,
    )


@lru_cache(maxsize=2048)
def cached_analyze(fen: str, multipv: int, depth: int) -> PositionAnalysis:
    return analyze_position(fen, multipv=multipv, depth=depth)


def pv_to_san(fen: str, uci_list: list[str]) -> list[str]:
    board = chess.Board(fen)
    out: list[str] = []
    for u in uci_list:
        try:
            move = chess.Move.from_uci(u)
            out.append(board.san(move))
            board.push(move)
        except ValueError:
            break
    return out


def line_payload(fen: str, line: EngineLine, *, probability: float | None = None) -> dict:
    return {
        "rank": line.rank,
        "san": line.san,
        "uci": line.uci,
        "score_cp": line.score_cp,
        "mate": line.mate,
        "eval_text": _eval_text(line.score_cp, line.mate),
        "probability": probability,
        "pv_san": pv_to_san(fen, line.pv),
    }
