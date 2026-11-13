"""Per-move feature engineering and game summaries."""

from __future__ import annotations

from typing import Any

import chess

from app.schemas.analysis import MoveFeature, PlayerSummary
from app.services.human_model import describe_backend, policy_from_stockfish
from app.services.pgn_parser import ParsedGame
from app.services.stockfish_worker import (
    cached_analyze,
    cp_loss_for_move,
    lines_as_dicts,
)


def detect_phase(board: chess.Board, ply: int) -> str:
    if ply <= 20:
        return "opening"
    pieces = len(board.piece_map())
    if pieces <= 12:
        return "endgame"
    return "middlegame"


def is_tactical(analysis_lines: list, board: chess.Board) -> bool:
    """Heuristic: checks, captures in top lines, or large eval swing among MultiPV."""
    if board.is_check():
        return True
    if not analysis_lines:
        return False
    cps = [ln.score_cp for ln in analysis_lines if ln.score_cp is not None]
    if len(cps) >= 2 and (max(cps) - min(cps)) >= 150:
        return True
    # Capture available among top-3
    for line in analysis_lines[:3]:
        try:
            move = chess.Move.from_uci(line.uci)
        except ValueError:
            continue
        if board.is_capture(move) or board.gives_check(move):
            return True
    return False


def build_move_features(
    game: ParsedGame,
    *,
    multipv: int,
    depth: int,
    side: str = "both",
) -> list[MoveFeature]:
    features: list[MoveFeature] = []
    white_elo = game.metadata.get("white_elo")
    black_elo = game.metadata.get("black_elo")

    for mv, think in zip(game.moves, game.think_times, strict=True):
        if side == "white" and mv.color != "white":
            continue
        if side == "black" and mv.color != "black":
            continue

        board = chess.Board(mv.fen_before)
        analysis = cached_analyze(mv.fen_before, multipv, depth)
        cp_loss, wdl_loss, rank = cp_loss_for_move(mv.uci, analysis)
        elo = white_elo if mv.color == "white" else black_elo
        policy = policy_from_stockfish(board, analysis, mv.uci, elo)

        missing = []
        if think is None:
            missing.append("think_time")
        if elo is None:
            missing.append("elo")
        if rank is None and analysis.lines:
            missing.append("engine_rank_outside_multipv")

        top1 = rank == 1 if rank is not None else False
        top3 = rank is not None and rank <= 3

        review_reasons: list[str] = []
        review = False
        # Flag for expert review — not an accusation.
        if (cp_loss is not None and cp_loss <= 15 and (policy.played_probability or 1) < 0.05 and think is not None and think < 2.0):
            review = True
            review_reasons.append("Low human-policy probability with strong engine match and short think (needs expert context)")
        if policy.surprisal is not None and policy.surprisal > 4.5 and top1:
            review = True
            review_reasons.append("High surprisal under surrogate policy but Stockfish top-1")

        phase = detect_phase(board, mv.ply)
        tactical = is_tactical(analysis.lines, board)

        # clock_before from think + clock_after - increment approx already in think
        clock_after = mv.clock_after
        clock_before = None
        if clock_after is not None and think is not None:
            clock_before = clock_after + think  # increment absorbed in think derivation

        features.append(
            MoveFeature(
                ply=mv.ply,
                color=mv.color,  # type: ignore[arg-type]
                fen_before=mv.fen_before,
                san=mv.san,
                uci=mv.uci,
                engine_rank=rank,
                cp_loss=cp_loss,
                wdl_loss=wdl_loss,
                stockfish_top1=top1,
                stockfish_top3=top3,
                maia_probability=policy.played_probability,
                maia_rank=policy.played_rank,
                maia_surprisal=policy.surprisal,
                human_policy_entropy=policy.entropy,
                tactical_context=tactical,
                phase=phase,  # type: ignore[arg-type]
                clock_before=clock_before,
                clock_after=clock_after,
                think_time_seconds=think,
                missing_fields=missing,
                stockfish_top_moves=lines_as_dicts(analysis),
                review_flag=review,
                review_reasons=review_reasons,
            )
        )
    return features


def _safe_mean(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def _rate(flags: list[bool | None]) -> float | None:
    xs = [1.0 if f else 0.0 for f in flags if f is not None]
    return sum(xs) / len(xs) if xs else None


def summarize_player(
    color: str,
    moves: list[MoveFeature],
    elo: int | None,
    platform: str,
    anomaly_score: float | None,
    anomaly_percentile: float | None,
) -> PlayerSummary:
    subset = [m for m in moves if m.color == color]
    blunders = [(m.cp_loss is not None and m.cp_loss >= 300) for m in subset]
    inaccuracies = [(m.cp_loss is not None and m.cp_loss >= 100) for m in subset]
    return PlayerSummary(
        color=color,  # type: ignore[arg-type]
        elo=elo,
        elo_missing=elo is None,
        platform=platform,
        avg_cp_loss=_safe_mean([m.cp_loss for m in subset]),
        top1_agreement=_rate([m.stockfish_top1 for m in subset]),
        top3_agreement=_rate([m.stockfish_top3 for m in subset]),
        mean_maia_probability=_safe_mean([m.maia_probability for m in subset]),
        mean_surprisal=_safe_mean([m.maia_surprisal for m in subset]),
        blunder_rate=_rate(blunders),
        inaccuracy_rate=_rate(inaccuracies),
        mean_think_time=_safe_mean([m.think_time_seconds for m in subset]),
        move_count=len(subset),
        anomaly_percentile=anomaly_percentile,
        anomaly_score=anomaly_score,
        calibrated_cheat_probability=None,
        confidence_note=(
            "Anomaly score/percentile only — NOT a cheat probability. "
            "Single-game conclusions are invalid."
        ),
    )


def phase_breakdown(moves: list[MoveFeature]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for phase in ("opening", "middlegame", "endgame"):
        subset = [m for m in moves if m.phase == phase]
        out[phase] = {
            "moves": len(subset),
            "avg_cp_loss": _safe_mean([m.cp_loss for m in subset]),
            "top1_agreement": _rate([m.stockfish_top1 for m in subset]),
            "mean_surprisal": _safe_mean([m.maia_surprisal for m in subset]),
        }
    return out


def human_model_meta() -> dict[str, Any]:
    return describe_backend()
