"""Human-typical move suggestions (Maia-style interface).

MVP: Elo-conditioned surrogate policy over Stockfish MultiPV.
When LAB_MAIA_WEIGHTS_PATH + LAB_HUMAN_MODEL_BACKEND=maia are set, swap the
sampler without changing the API.

Purpose: educational “what a typical player at this Elo often plays”.
Not for evading anti-cheat / lowering bot scores.
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


def _temperature_for_elo(elo: int) -> float:
    # Weaker → flatter; stronger → peakier around engine prefs
    return max(28.0, 155.0 - (elo - 800) * (120.0 / 1600.0))


def _softmax(scores: list[float], temperature: float) -> list[float]:
    arr = np.asarray(scores, dtype=np.float64) / max(temperature, 1e-6)
    arr = arr - arr.max()
    ex = np.exp(arr)
    return (ex / ex.sum()).tolist()


@dataclass
class HumanSuggestion:
    elo_band: int
    backend: str
    lines: list[tuple[EngineLine, float]]  # line, probability
    note: str


def suggest_human_moves(
    board: chess.Board,
    analysis: PositionAnalysis,
    elo: int,
) -> HumanSuggestion:
    elo_band = nearest_elo_band(elo)
    temp = _temperature_for_elo(elo_band)

    if settings.human_model_backend == "maia" and settings.maia_weights_path:
        # Hook reserved for real Maia/LC0 weights.
        backend = "maia-pending-loader"
        note = (
            "Maia weights path configured but neural loader not bundled in MVP; "
            "falling back to Elo surrogate over MultiPV."
        )
    else:
        backend = "surrogate-stockfish-multipv"
        note = (
            "Human-typical list is an Elo-conditioned surrogate over Stockfish MultiPV "
            "(Maia-compatible API). Install Maia weights later for neural priors. "
            "Educational only — not an anti-cheat evasion aid."
        )

    scored: list[tuple[EngineLine, float]] = []
    for line in analysis.lines:
        if line.mate is not None:
            score = 10000.0 - abs(line.mate) * 100 if line.mate > 0 else -10000.0
        else:
            score = float(line.score_cp or 0)
        # Mild Elo noise: lower Elo prefers slightly safer/simpler (less extreme) scores
        if elo_band <= 1400 and line.mate is None:
            score = score * 0.85
        scored.append((line, score))

    if not scored:
        # Fallback: any legal move uniform
        legal = list(board.legal_moves)
        fake_lines: list[tuple[EngineLine, float]] = []
        if legal:
            p = 1.0 / len(legal)
            move = legal[0]
            try:
                san = board.san(move)
            except ValueError:
                san = move.uci()
            el = EngineLine(1, move.uci(), san, None, None, [move.uci()])
            fake_lines.append((el, p))
        return HumanSuggestion(elo_band, backend, fake_lines, note)

    probs = _softmax([s for _, s in scored], temp)
    ranked = sorted(
        [(line, float(p)) for (line, _), p in zip(scored, probs, strict=True)],
        key=lambda t: t[1],
        reverse=True,
    )
    # Re-rank for human list display
    relabeled: list[tuple[EngineLine, float]] = []
    for i, (line, p) in enumerate(ranked, start=1):
        relabeled.append(
            (
                EngineLine(i, line.uci, line.san, line.score_cp, line.mate, line.pv),
                p,
            )
        )

    return HumanSuggestion(elo_band=elo_band, backend=backend, lines=relabeled, note=note)


def describe_backend(elo_band: int) -> dict[str, Any]:
    return {
        "requested_backend": settings.human_model_backend,
        "active_backend": (
            "surrogate-stockfish-multipv"
            if not (settings.human_model_backend == "maia" and settings.maia_weights_path)
            else "maia-pending-loader"
        ),
        "elo_band": elo_band,
        "elo_bands": list(ELO_BANDS),
        "maia_weights_configured": bool(settings.maia_weights_path),
        "entropy_hint": "Higher Elo → peakier human-typical distribution",
    }
