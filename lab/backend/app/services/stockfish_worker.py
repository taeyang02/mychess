"""Offline Stockfish MultiPV analysis worker with FEN cache."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

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
    wdl_win: float | None
    pv: list[str]


@dataclass
class PositionAnalysis:
    fen: str
    depth: int
    multipv: int
    nodes: int | None
    time_ms: int | None
    engine_name: str
    lines: list[EngineLine]


def _wdl_from_cp(cp: int | None, mate: int | None) -> float | None:
    """Crude win-probability from CP (Lichess-like logistic). Not a claim of truth."""
    if mate is not None:
        return 1.0 if mate > 0 else 0.0
    if cp is None:
        return None
    # Same family as Lichess win% approximation
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


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
    if settings.analysis_movetime_ms:
        limit = chess.engine.Limit(time=settings.analysis_movetime_ms / 1000.0)

    with chess.engine.SimpleEngine.popen_uci(str(path)) as engine:
        info_list = engine.analyse(board, limit, multipv=multipv)
        if isinstance(info_list, dict):
            info_list = [info_list]
        engine_name = engine.id.get("name", "Stockfish")
        nodes = info_list[0].get("nodes") if info_list else None
        time_ms = None
        if info_list and info_list[0].get("time") is not None:
            time_ms = int(float(info_list[0]["time"]) * 1000)

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
                    wdl_win=_wdl_from_cp(cp, mate),
                    pv=[m.uci() for m in pv_moves[:8]],
                )
            )

    return PositionAnalysis(
        fen=fen,
        depth=depth,
        multipv=multipv,
        nodes=int(nodes) if nodes is not None else None,
        time_ms=time_ms,
        engine_name=engine_name,
        lines=lines,
    )


@lru_cache(maxsize=4096)
def cached_analyze(fen: str, multipv: int, depth: int) -> PositionAnalysis:
    return analyze_position(fen, multipv=multipv, depth=depth)


def cp_loss_for_move(played_uci: str, analysis: PositionAnalysis) -> tuple[float | None, float | None, int | None]:
    """Return (cp_loss, wdl_loss, engine_rank). Mate-aware; no fake 100cp for mates."""
    if not analysis.lines:
        return None, None, None

    best = analysis.lines[0]
    rank = None
    played_line = None
    for line in analysis.lines:
        if line.uci == played_uci:
            rank = line.rank
            played_line = line
            break

    # If played move not in MultiPV, treat as worse than last line (bounded).
    if played_line is None:
        played_line = analysis.lines[-1]
        rank = None

    if best.mate is not None or played_line.mate is not None:
        # Prefer WDL loss for mate contexts; CP loss left null when mate involved.
        best_wdl = best.wdl_win if best.wdl_win is not None else (1.0 if (best.mate or 0) > 0 else 0.0)
        played_wdl = played_line.wdl_win
        if played_wdl is None and played_line.mate is not None:
            played_wdl = 1.0 if played_line.mate > 0 else 0.0
        wdl_loss = None if played_wdl is None else max(0.0, best_wdl - played_wdl)
        return None, wdl_loss, rank

    if best.score_cp is None or played_line.score_cp is None:
        return None, None, rank

    cp_loss = max(0.0, float(best.score_cp - played_line.score_cp))
    best_wdl = best.wdl_win or 0.5
    played_wdl = played_line.wdl_win or 0.5
    wdl_loss = max(0.0, best_wdl - played_wdl)
    return cp_loss, wdl_loss, rank


def lines_as_dicts(analysis: PositionAnalysis) -> list[dict[str, Any]]:
    return [
        {
            "rank": line.rank,
            "uci": line.uci,
            "san": line.san,
            "score_cp": line.score_cp,
            "mate": line.mate,
            "wdl_win": line.wdl_win,
            "pv": line.pv,
        }
        for line in analysis.lines
    ]
