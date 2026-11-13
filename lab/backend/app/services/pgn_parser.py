"""PGN import, validation, clock extraction, FEN reconstruction."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import chess
import chess.pgn

CLK_RE = re.compile(r"\[%clk\s+([^\]]+)\]")
EVAL_RE = re.compile(r"\[%eval\s+([^\]]+)\]")


def _parse_clk(comment: str) -> float | None:
    match = CLK_RE.search(comment or "")
    if not match:
        return None
    raw = match.group(1).strip()
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(raw)
    except ValueError:
        return None


def _parse_increment(time_control: str | None) -> tuple[float | None, float]:
    if not time_control or time_control in {"-", "?"}:
        return None, 0.0
    # Formats: 600, 600+5, 180+2, 1/60
    if "/" in time_control:
        return None, 0.0
    if "+" in time_control:
        base, inc = time_control.split("+", 1)
        try:
            return float(base), float(inc)
        except ValueError:
            return None, 0.0
    try:
        return float(time_control), 0.0
    except ValueError:
        return None, 0.0


@dataclass
class ParsedMove:
    ply: int
    color: str
    fen_before: str
    san: str
    uci: str
    clock_after: float | None
    eval_comment: str | None
    comment: str


@dataclass
class ParsedGame:
    headers: dict[str, str]
    moves: list[ParsedMove]
    warnings: list[str] = field(default_factory=list)
    missing: dict[str, bool] = field(default_factory=dict)
    platform: str = "offline"
    think_times: list[float | None] = field(default_factory=list)

    @property
    def metadata(self) -> dict[str, Any]:
        white_elo = self.headers.get("WhiteElo")
        black_elo = self.headers.get("BlackElo")
        return {
            "event": self.headers.get("Event"),
            "site": self.headers.get("Site"),
            "date": self.headers.get("Date"),
            "white": self.headers.get("White"),
            "black": self.headers.get("Black"),
            "result": self.headers.get("Result"),
            "white_elo": int(white_elo) if white_elo and white_elo.isdigit() else None,
            "black_elo": int(black_elo) if black_elo and black_elo.isdigit() else None,
            "time_control": self.headers.get("TimeControl"),
            "eco": self.headers.get("ECO"),
            "opening": self.headers.get("Opening"),
            "platform": self.platform,
            "move_count": len(self.moves),
            "missing_fields": [k for k, v in self.missing.items() if v],
        }


def parse_pgn_text(pgn_text: str, *, platform: str = "offline", max_plies: int = 200) -> ParsedGame:
    text = (pgn_text or "").strip()
    if not text:
        raise ValueError("Empty PGN")

    game = chess.pgn.read_game(io.StringIO(text))
    if game is None:
        raise ValueError("Could not parse PGN")

    headers = {k: game.headers.get(k, "") for k in game.headers.keys()}
    warnings: list[str] = []
    missing = {
        "WhiteElo": not bool(headers.get("WhiteElo") and str(headers.get("WhiteElo")).isdigit()),
        "BlackElo": not bool(headers.get("BlackElo") and str(headers.get("BlackElo")).isdigit()),
        "TimeControl": not bool(headers.get("TimeControl")),
        "clock_comments": False,
    }

    base_seconds, increment = _parse_increment(headers.get("TimeControl"))
    board = game.board()
    moves: list[ParsedMove] = []
    clocks_after: list[float | None] = []
    node = game

    while node.variations and len(moves) < max_plies:
        next_node = node.variation(0)
        move = next_node.move
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move at ply {len(moves) + 1}: {board.san(move) if move else '?'}")

        fen_before = board.fen()
        san = board.san(move)
        uci = move.uci()
        color = "white" if board.turn == chess.WHITE else "black"
        comment = next_node.comment or ""
        clock_after = _parse_clk(comment)
        eval_m = EVAL_RE.search(comment)
        clocks_after.append(clock_after)

        moves.append(
            ParsedMove(
                ply=len(moves) + 1,
                color=color,
                fen_before=fen_before,
                san=san,
                uci=uci,
                clock_after=clock_after,
                eval_comment=eval_m.group(1).strip() if eval_m else None,
                comment=comment,
            )
        )
        board.push(move)
        node = next_node

    if len(moves) >= max_plies:
        warnings.append(f"Truncated to max_plies={max_plies}")

    if not any(c is not None for c in clocks_after):
        missing["clock_comments"] = True
        warnings.append("No [%clk] comments found — think times unavailable")

    # Derive think times from consecutive clocks of the same side (+ increment).
    think_times: list[float | None] = []
    last_clock = {"white": base_seconds, "black": base_seconds}
    for mv, clock_after in zip(moves, clocks_after, strict=True):
        before = last_clock[mv.color]
        if before is None or clock_after is None:
            think_times.append(None)
        else:
            # clock_after ≈ before - think + increment
            think = before - clock_after + increment
            if think < -1 or think > 3600:
                warnings.append(f"Inconsistent clock at ply {mv.ply}")
                think_times.append(None)
            else:
                think_times.append(max(0.0, think))
        if clock_after is not None:
            last_clock[mv.color] = clock_after

    if "synthetic" in (headers.get("Annotator") or "").lower() or "synthetic" in (headers.get("Event") or "").lower():
        warnings.append("Marked synthetic/demo game — not real cheat evidence")

    return ParsedGame(
        headers=headers,
        moves=moves,
        warnings=warnings,
        missing=missing,
        platform=platform,
        think_times=think_times,
    )
