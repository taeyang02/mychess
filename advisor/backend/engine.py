"""Stockfish analysis wrapper via python-chess."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from anyio import CancelScope

import chess
import chess.engine

from limits import BusyError, engine_slot

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENGINE_CANDIDATES = (
    ROOT / "stockfish" / "stockfish-macos-universal",
    ROOT / "stockfish" / "stockfish-ubuntu-x86-64-avx2",
    ROOT / "stockfish" / "stockfish",
    Path("/usr/bin/stockfish"),
    Path("/usr/local/bin/stockfish"),
)
DEFAULT_DEPTH = 16


class EngineError(Exception):
    """Raised when Stockfish cannot analyze a position."""


def resolve_engine_path(path: str | Path | None = None) -> Path:
    if path:
        engine_path = Path(path)
    else:
        env_path = os.getenv("STOCKFISH_PATH", "").strip()
        if env_path:
            engine_path = Path(env_path)
        else:
            engine_path = next((p for p in DEFAULT_ENGINE_CANDIDATES if p.is_file()), None)
            if engine_path is None:
                raise EngineError("Chess engine unavailable on server")

    if not engine_path.exists() or not engine_path.is_file():
        raise EngineError("Chess engine unavailable on server")
    return engine_path


class EnginePool:
    """Lease one UCI process per active analysis, up to the configured limit."""

    def __init__(self) -> None:
        self._idle: list[tuple[Path, asyncio.SubprocessTransport, chess.engine.UciProtocol]] = []

    @asynccontextmanager
    async def lease(self, path: Path):
        with engine_slot():
            while self._idle:
                idle_path, transport, protocol = self._idle.pop()
                if idle_path == path and transport.get_returncode() is None:
                    break
                transport.close()
            else:
                transport, protocol = await asyncio.wait_for(
                    chess.engine.popen_uci(str(path)), timeout=5.0
                )

            try:
                yield protocol
            except BaseException:
                # An interrupted UCI search can still have outstanding output.
                transport.close()
                raise
            else:
                if transport.get_returncode() is None:
                    self._idle.append((path, transport, protocol))
                else:
                    transport.close()

    def close(self) -> None:
        while self._idle:
            _, transport, _ = self._idle.pop()
            transport.close()


def build_board(fen: str, turn: str | None = None) -> chess.Board:
    """Build a board from FEN, optionally overriding whose turn it is."""
    fen = fen.strip()
    parts = fen.split()

    # Accept piece placement only, or full FEN.
    if len(parts) == 1:
        fen = f"{parts[0]} w KQkq - 0 1"
        parts = fen.split()
    elif len(parts) < 6:
        # Pad incomplete FEN with safe defaults.
        defaults = ["w", "KQkq", "-", "0", "1"]
        while len(parts) < 6:
            parts.append(defaults[len(parts) - 1])
        fen = " ".join(parts)

    # Prefer a tolerant rebuild so minor castling / ep issues still analyze.
    placement = parts[0]
    try:
        board = chess.Board(None)
        board.set_board_fen(placement)
    except ValueError:
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            raise EngineError(f"Invalid FEN: {exc}") from exc

    if turn is not None:
        turn_norm = turn.strip().lower()
        if turn_norm in {"w", "white", "trang", "trắng"}:
            board.turn = chess.WHITE
        elif turn_norm in {"b", "black", "den", "đen"}:
            board.turn = chess.BLACK
        else:
            raise EngineError("turn must be 'white' or 'black'")
    elif len(parts) >= 2 and parts[1] in {"w", "b"}:
        board.turn = chess.WHITE if parts[1] == "w" else chess.BLACK

    # Keep castling / ep when present and legal-ish; otherwise clear.
    try:
        if len(parts) >= 3:
            board.set_castling_fen(parts[2])
    except ValueError:
        board.castling_rights = 0

    if len(parts) >= 4 and parts[3] != "-":
        try:
            board.ep_square = chess.parse_square(parts[3])
        except ValueError:
            board.ep_square = None
    else:
        board.ep_square = None

    if len(parts) >= 5:
        try:
            board.halfmove_clock = int(parts[4])
        except ValueError:
            board.halfmove_clock = 0
    if len(parts) >= 6:
        try:
            board.fullmove_number = max(1, int(parts[5]))
        except ValueError:
            board.fullmove_number = 1

    status = board.status()
    if status & chess.STATUS_NO_WHITE_KING:
        raise EngineError("Position has no white king — chỉnh lại bàn rồi thử.")
    if status & chess.STATUS_NO_BLACK_KING:
        raise EngineError("Position has no black king — chỉnh lại bàn rồi thử.")
    if status & chess.STATUS_TOO_MANY_KINGS:
        raise EngineError(
            "Nhận diện ra quá nhiều vua (thường do dính UI Chess.com). "
            "Hãy crop sát bàn cờ hoặc kéo sửa quân trên bàn."
        )
    if status & chess.STATUS_TOO_MANY_WHITE_PAWNS or status & chess.STATUS_TOO_MANY_BLACK_PAWNS:
        raise EngineError("Quá nhiều tốt — kiểm tra lại vị trí trên bàn.")
    if status & chess.STATUS_PAWNS_ON_BACKRANK:
        raise EngineError("Tốt nằm hàng cuối — nhận diện lệch, hãy sửa quân rồi phân tích.")

    return board


def format_score(score: chess.engine.PovScore, turn: chess.Color) -> dict[str, Any]:
    pov = score.pov(turn)
    if pov.is_mate():
        mate = pov.mate()
        return {
            "type": "mate",
            "value": mate,
            "text": f"M{mate}" if mate and mate > 0 else f"M{mate}",
        }
    cp = pov.score(mate_score=100000)
    pawns = (cp or 0) / 100.0
    sign = "+" if pawns > 0 else ""
    return {
        "type": "cp",
        "value": cp,
        "text": f"{sign}{pawns:.2f}",
    }


def _info_to_result(
    board: chess.Board,
    info: chess.engine.InfoDict,
    *,
    mode: str,
    elapsed_ms: int,
    max_ms: int | None = None,
    done: bool = False,
) -> dict[str, Any]:
    pv: list[chess.Move] = info.get("pv") or []
    if not pv:
        raise EngineError("No legal moves / Stockfish returned empty PV")

    best = pv[0]
    try:
        best_san = board.san(best)
    except ValueError:
        best_san = best.uci()

    score = info.get("score")
    evaluation = (
        format_score(score, board.turn)
        if score is not None
        else {"type": "cp", "value": 0, "text": "0.00"}
    )

    san_pv: list[str] = []
    tmp = board.copy(stack=False)
    for move in pv[:8]:
        try:
            san_pv.append(tmp.san(move))
            tmp.push(move)
        except ValueError:
            break

    reached_depth = info.get("depth")
    return {
        "board_fen": board.fen(),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "mode": mode,
        "depth": int(reached_depth) if reached_depth is not None else 0,
        "movetime_ms": elapsed_ms,
        "elapsed_ms": elapsed_ms,
        "max_ms": max_ms,
        "done": done,
        "best_move_uci": best.uci(),
        "best_move_san": best_san,
        "from_square": chess.square_name(best.from_square),
        "to_square": chess.square_name(best.to_square),
        "evaluation": evaluation,
        "pv_uci": [m.uci() for m in pv[:8]],
        "pv_san": san_pv,
    }


async def analyze_position(
    pool: EnginePool,
    fen: str,
    turn: str | None = None,
    depth: int | None = DEFAULT_DEPTH,
    movetime_ms: int | None = None,
    engine_path: str | Path | None = None,
) -> dict[str, Any]:
    board = build_board(fen, turn=turn)
    path = resolve_engine_path(engine_path)

    if movetime_ms is not None:
        think_ms = max(50, min(int(movetime_ms), 10000))
        limit = chess.engine.Limit(time=think_ms / 1000.0)
        mode = "time"
    else:
        depth_val = max(1, min(int(depth or DEFAULT_DEPTH), 30))
        limit = chess.engine.Limit(depth=depth_val)
        think_ms = None
        mode = "depth"

    started = time.monotonic()
    try:
        async with pool.lease(path) as engine:
            info = await asyncio.wait_for(
                engine.analyse(board, limit, game=object()), timeout=15.0
            )
    except BusyError:
        raise
    except chess.engine.EngineTerminatedError as exc:
        raise EngineError(f"Stockfish terminated unexpectedly: {exc}") from exc
    except TimeoutError as exc:
        raise EngineError("Stockfish analysis timed out") from exc
    except Exception as exc:
        raise EngineError(f"Stockfish analysis failed: {exc}") from exc

    return _info_to_result(
        board,
        info,
        mode=mode,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        max_ms=think_ms,
        done=True,
    )


async def iter_analyze_progressive(
    pool: EnginePool,
    fen: str,
    turn: str | None = None,
    max_time_s: float = 10.0,
    engine_path: str | Path | None = None,
):
    """Yield analysis updates while Stockfish thinks up to max_time_s."""
    board = build_board(fen, turn=turn)
    path = resolve_engine_path(engine_path)
    max_time_s = max(0.5, min(float(max_time_s), 10.0))
    max_ms = int(max_time_s * 1000)
    started = time.monotonic()
    last_uci: str | None = None
    last_emit = 0.0
    final_info: chess.engine.InfoDict | None = None

    try:
        async with pool.lease(path) as engine:
            analysis = await asyncio.wait_for(
                engine.analysis(board, chess.engine.Limit(time=max_time_s), game=object()),
                timeout=5.0,
            )
            deadline = time.monotonic() + max_time_s + 2.0
            try:
                while True:
                    info = await asyncio.wait_for(analysis.next(), deadline - time.monotonic())
                    if info is None:
                        break
                    if not info.get("pv"):
                        continue
                    final_info = info
                    now = time.monotonic()
                    best_uci = info["pv"][0].uci()
                    if best_uci == last_uci and now - last_emit < 0.25:
                        continue

                    last_uci = best_uci
                    last_emit = now
                    yield _info_to_result(
                        board,
                        info,
                        mode="progressive",
                        elapsed_ms=int((now - started) * 1000),
                        max_ms=max_ms,
                        done=False,
                    )
            except BaseException:
                with CancelScope(shield=True):
                    analysis.stop()
                    try:
                        await asyncio.wait_for(analysis.wait(), timeout=0.5)
                    except (TimeoutError, chess.engine.EngineError):
                        pass
                raise
    except BusyError:
        raise
    except chess.engine.EngineTerminatedError as exc:
        raise EngineError(f"Stockfish terminated unexpectedly: {exc}") from exc
    except TimeoutError as exc:
        raise EngineError("Stockfish analysis timed out") from exc
    except Exception as exc:
        raise EngineError(f"Stockfish analysis failed: {exc}") from exc

    if final_info is None:
        raise EngineError("No legal moves / Stockfish returned empty PV")

    yield _info_to_result(
        board,
        final_info,
        mode="progressive",
        elapsed_ms=int((time.monotonic() - started) * 1000),
        max_ms=max_ms,
        done=True,
    )
