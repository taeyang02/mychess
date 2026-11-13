"""Stockfish MultiPV analysis for Advisor v2 (one-shot + progressive)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

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
    depth: int | None = None


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


def _lines_from_infos(
    board: chess.Board,
    info_list: list[chess.engine.InfoDict],
) -> list[EngineLine]:
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
                depth=info.get("depth"),
            )
        )
    return lines


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
        lines = _lines_from_infos(board, info_list)

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


def line_payload(fen: str, line: EngineLine, *, probability: float | None = None) -> dict[str, Any]:
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


async def iter_progressive_analysis(
    fen: str,
    *,
    multipv: int = 5,
    max_time_s: float = 10.0,
    engine_path: Path | None = None,
) -> AsyncIterator[tuple[PositionAnalysis, int, int, bool]]:
    """Yield (analysis, elapsed_ms, max_ms, done) while Stockfish searches up to max_time_s."""
    max_time_s = max(0.5, min(float(max_time_s), 10.0))
    max_ms = int(max_time_s * 1000)
    path = engine_path or resolve_stockfish()
    board = chess.Board(fen)
    started = time.monotonic()
    last_uci: str | None = None
    last_emit = 0.0
    last_lines: list[EngineLine] = []
    engine_name = "Stockfish"
    reached_depth = 0

    transport, protocol = await asyncio.wait_for(chess.engine.popen_uci(str(path)), timeout=5.0)
    try:
        engine_name = protocol.id.get("name", "Stockfish")
        analysis = await asyncio.wait_for(
            protocol.analysis(
                board,
                chess.engine.Limit(time=max_time_s),
                game=object(),
                multipv=multipv,
            ),
            timeout=5.0,
        )
        deadline = time.monotonic() + max_time_s + 2.0
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                info = await asyncio.wait_for(analysis.next(), remaining)
                if info is None:
                    break

                # Keep latest multipv snapshot when available
                mp_lines = _lines_from_infos(board, list(analysis.multipv))
                if mp_lines:
                    last_lines = mp_lines
                    if mp_lines[0].depth is not None:
                        reached_depth = max(reached_depth, int(mp_lines[0].depth))

                if info.get("multipv", 1) != 1 or not info.get("pv"):
                    continue

                now = time.monotonic()
                best_uci = info["pv"][0].uci()
                depth = int(info.get("depth") or reached_depth or 0)
                reached_depth = max(reached_depth, depth)
                if best_uci == last_uci and now - last_emit < 0.2:
                    continue
                last_uci = best_uci
                last_emit = now

                # Prefer full multipv; fall back to single line
                lines = last_lines or _lines_from_infos(board, [info])
                pos = PositionAnalysis(
                    fen=fen,
                    depth=reached_depth,
                    multipv=multipv,
                    engine_name=engine_name,
                    lines=lines,
                )
                yield pos, int((now - started) * 1000), max_ms, False

            # Final snapshot
            final_lines = _lines_from_infos(board, list(analysis.multipv)) or last_lines
            if not final_lines:
                raise ValueError("No legal moves / Stockfish returned empty PV")
            if final_lines[0].depth is not None:
                reached_depth = max(reached_depth, int(final_lines[0].depth))
            pos = PositionAnalysis(
                fen=fen,
                depth=reached_depth,
                multipv=multipv,
                engine_name=engine_name,
                lines=final_lines,
            )
            yield pos, int((time.monotonic() - started) * 1000), max_ms, True
        finally:
            analysis.stop()
            try:
                await asyncio.wait_for(analysis.wait(), timeout=0.5)
            except (TimeoutError, chess.engine.EngineError):
                pass
    finally:
        transport.close()
