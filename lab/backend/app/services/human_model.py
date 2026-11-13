"""Human-typical move suggestions (Maia-style interface).

Club players often do NOT play Stockfish #1 (human top-move rates are far
below engine). This surrogate deliberately down-weights engine top-1 at
lower/mid Elo so the yellow suggestion is educationally distinct from the
green Stockfish arrow.

Educational contrast only — not a tool to lower Fair Play / bot scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chess
import numpy as np

from app.config import settings
from app.services.stockfish_worker import EngineLine, PositionAnalysis

ELO_BANDS = (800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400)


def nearest_elo_band(elo: int) -> int:
    return min(ELO_BANDS, key=lambda b: abs(b - elo))


def _preferred_engine_rank(elo: int) -> float:
    """Where a 'typical' player of this Elo sits in the engine MultiPV list."""
    # 800 → ~3.6, 1400 → ~2.5, 1800 → ~1.8, 2400 → ~1.1
    return max(1.05, 3.8 - (elo - 800) * (2.7 / 1600.0))


def _rank_spread(elo: int) -> float:
    # Lower Elo → wider mix across MultiPV ranks
    return max(0.55, 1.35 - (elo - 800) * (0.8 / 1600.0))


def _engine_pull(elo: int) -> float:
    """How strongly raw engine eval still pulls (higher = more bot-like)."""
    # Keep weak — humans are not soft-max of MultiPV CP.
    return max(0.08, 0.45 - (elo - 800) * (0.30 / 1600.0))


def _softmax(logits: list[float]) -> list[float]:
    arr = np.asarray(logits, dtype=np.float64)
    arr = arr - arr.max()
    ex = np.exp(arr)
    return (ex / ex.sum()).tolist()


def _stable_rng(fen: str, elo_band: int) -> np.random.Generator:
    material = abs(hash((fen.split()[0], elo_band, settings.seed))) % (2**32 - 1)
    return np.random.default_rng(material)


@dataclass
class HumanSuggestion:
    elo_band: int
    backend: str
    lines: list[tuple[EngineLine, float]]
    note: str


def _engine_score(line: EngineLine) -> float:
    if line.mate is not None:
        return 10000.0 - abs(line.mate) * 100 if line.mate > 0 else -10000.0
    return float(line.score_cp or 0)


def _salience_bonus(board: chess.Board, line: EngineLine, elo_band: int) -> float:
    try:
        move = chess.Move.from_uci(line.uci)
    except ValueError:
        return 0.0
    bonus = 0.0
    # Club players overweight obvious/forcing ideas vs quiet engine prophylactics.
    if board.is_capture(move):
        bonus += 0.55
    if board.gives_check(move):
        bonus += 0.35
    if board.is_castling(move):
        bonus += 0.45
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.PAWN and elo_band <= 1600:
        bonus += 0.25
    return bonus * max(0.2, (2000 - elo_band) / 1200.0)


def suggest_human_moves(
    board: chess.Board,
    analysis: PositionAnalysis,
    elo: int,
) -> HumanSuggestion:
    elo_band = nearest_elo_band(elo)
    preferred = _preferred_engine_rank(elo_band)
    spread = _rank_spread(elo_band)
    pull = _engine_pull(elo_band)
    rng = _stable_rng(board.fen(), elo_band)

    if settings.human_model_backend == "maia" and settings.maia_weights_path:
        backend = "maia-pending-loader"
        note = (
            "Maia weights configured but loader not bundled; using club-human "
            "MultiPV surrogate (intentionally less bot-like than Stockfish #1)."
        )
    else:
        backend = "surrogate-club-human"
        note = (
            "Human-typical down-weights Stockfish #1 at club Elo so the yellow "
            "arrow is not a second engine best. Educational contrast only — "
            "not for lowering Fair Play suspicion scores."
        )

    if not analysis.lines:
        legal = list(board.legal_moves)
        fake: list[tuple[EngineLine, float]] = []
        if legal:
            move = legal[0]
            try:
                san = board.san(move)
            except ValueError:
                san = move.uci()
            fake.append((EngineLine(1, move.uci(), san, None, None, [move.uci()]), 1.0))
        return HumanSuggestion(elo_band, backend, fake, note)

    # Softmax over MultiPV with rank targeting — NOT monotone in engine CP.
    logits: list[float] = []
    scores = [_engine_score(line) for line in analysis.lines]
    score_scale = max(40.0, float(np.std(scores)) + 1e-6)

    for rank, line in enumerate(analysis.lines, start=1):
        # Prefer moves near the Elo-typical engine rank (often 2–3 for club).
        rank_term = -((rank - preferred) ** 2) / (2.0 * spread * spread)
        # Mild eval pull (weak) + salience + stable noise
        eval_term = pull * (_engine_score(line) / score_scale)
        sal = _salience_bonus(board, line, elo_band)
        noise = float(rng.normal(0.0, 0.35))
        # Extra penalty on pure engine #1 below ~2000 so yellow ≠ green more often
        top1_pen = -1.15 * max(0.0, (2000 - elo_band) / 1200.0) if rank == 1 else 0.0
        logits.append(rank_term + eval_term + sal + noise + top1_pen)

    probs = _softmax(logits)
    ranked = sorted(
        list(zip(analysis.lines, probs, strict=True)),
        key=lambda t: t[1],
        reverse=True,
    )

    relabeled: list[tuple[EngineLine, float]] = []
    for i, (line, p) in enumerate(ranked, start=1):
        relabeled.append(
            (
                EngineLine(
                    i,
                    line.uci,
                    line.san,
                    line.score_cp,
                    line.mate,
                    line.pv,
                    line.depth,
                ),
                float(p),
            )
        )

    return HumanSuggestion(elo_band=elo_band, backend=backend, lines=relabeled, note=note)


def describe_backend(elo_band: int) -> dict[str, Any]:
    return {
        "requested_backend": settings.human_model_backend,
        "active_backend": "surrogate-club-human",
        "elo_band": elo_band,
        "elo_bands": list(ELO_BANDS),
        "preferred_engine_rank": round(_preferred_engine_rank(elo_band), 2),
        "maia_weights_configured": bool(settings.maia_weights_path),
        "entropy_hint": "Club Elo human-typical usually avoids Stockfish #1",
        "disclaimer": "Not for reducing anti-cheat / Fair Play scores.",
    }
