"""Stockfish analysis wrapper via python-chess."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENGINE_PATH = ROOT / "stockfish" / "stockfish-macos-universal"
DEFAULT_DEPTH = 16


class EngineError(Exception):
    """Raised when Stockfish cannot analyze a position."""


def resolve_engine_path(path: str | Path | None = None) -> Path:
    engine_path = Path(path) if path else DEFAULT_ENGINE_PATH
    if not engine_path.exists():
        raise EngineError(f"Stockfish binary not found: {engine_path}")
    if not engine_path.is_file():
        raise EngineError(f"Stockfish path is not a file: {engine_path}")
    return engine_path


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


def analyze_position(
    fen: str,
    turn: str | None = None,
    depth: int | None = DEFAULT_DEPTH,
    movetime_ms: int | None = None,
    engine_path: str | Path | None = None,
) -> dict[str, Any]:
    board = build_board(fen, turn=turn)
    path = resolve_engine_path(engine_path)

    if movetime_ms is not None:
        think_ms = max(50, min(int(movetime_ms), 15000))
        limit = chess.engine.Limit(time=think_ms / 1000.0)
        mode = "time"
    else:
        depth_val = max(1, min(int(depth or DEFAULT_DEPTH), 30))
        limit = chess.engine.Limit(depth=depth_val)
        think_ms = None
        mode = "depth"

    try:
        with chess.engine.SimpleEngine.popen_uci(str(path)) as engine:
            info = engine.analyse(board, limit, multipv=1)
    except chess.engine.EngineTerminatedError as exc:
        raise EngineError(f"Stockfish terminated unexpectedly: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EngineError(f"Stockfish analysis failed: {exc}") from exc

    if isinstance(info, list):
        info = info[0]

    return _info_to_result(
        board,
        info,
        mode=mode,
        elapsed_ms=think_ms or 0,
        max_ms=think_ms,
        done=True,
    )


def iter_analyze_progressive(
    fen: str,
    turn: str | None = None,
    max_time_s: float = 10.0,
    engine_path: str | Path | None = None,
):
    """Yield analysis updates while Stockfish thinks up to max_time_s."""
    import time

    board = build_board(fen, turn=turn)
    path = resolve_engine_path(engine_path)
    max_time_s = max(0.5, min(float(max_time_s), 15.0))
    max_ms = int(max_time_s * 1000)
    started = time.monotonic()
    last_uci: str | None = None
    last_depth = -1
    last_emit = 0.0
    final_info: chess.engine.InfoDict | None = None

    try:
        with chess.engine.SimpleEngine.popen_uci(str(path)) as engine:
            with engine.analysis(board, chess.engine.Limit(time=max_time_s)) as analysis:
                for info in analysis:
                    if "pv" not in info or not info["pv"]:
                        continue
                    final_info = info
                    now = time.monotonic()
                    elapsed_ms = int((now - started) * 1000)
                    best_uci = info["pv"][0].uci()
                    depth_now = int(info.get("depth") or 0)

                    # Emit when best move/depth changes, or every ~250ms for progress.
                    should_emit = (
                        best_uci != last_uci
                        or depth_now > last_depth
                        or (now - last_emit) >= 0.25
                    )
                    if not should_emit:
                        continue

                    last_uci = best_uci
                    last_depth = depth_now
                    last_emit = now
                    yield _info_to_result(
                        board,
                        info,
                        mode="progressive",
                        elapsed_ms=min(elapsed_ms, max_ms),
                        max_ms=max_ms,
                        done=False,
                    )
    except chess.engine.EngineTerminatedError as exc:
        raise EngineError(f"Stockfish terminated unexpectedly: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EngineError(f"Stockfish analysis failed: {exc}") from exc

    if final_info is None or not final_info.get("pv"):
        raise EngineError("No legal moves / Stockfish returned empty PV")

    yield _info_to_result(
        board,
        final_info,
        mode="progressive",
        elapsed_ms=max_ms,
        max_ms=max_ms,
        done=True,
    )
