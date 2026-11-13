"""Human move model.

MVP ships a documented Elo-conditioned *surrogate* policy derived from Stockfish
MultiPV scores. This is NOT Maia-3 weights. When LAB_HUMAN_MODEL_BACKEND=maia and
weights exist, a Maia-compatible loader can be plugged in without API changes.

Surrogate purpose: offline statistical comparison of move likelihood vs engine
preference across rating bands — not to evade anti-cheat systems.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import chess
import numpy as np

from app.config import settings
from app.services.stockfish_worker import PositionAnalysis

ELO_BANDS = (800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400)


def nearest_elo_band(elo: int | None) -> int:
    if elo is None:
        return 1600
    return min(ELO_BANDS, key=lambda b: abs(b - elo))


def _temperature_for_elo(elo: int) -> float:
    """Higher temp → flatter distribution (weaker players)."""
    # 800 → ~120, 2400 → ~35 (centipawn scale softmax)
    return max(25.0, 160.0 - (elo - 800) * (125.0 / 1600.0))


@dataclass
class HumanPolicy:
    backend: str
    elo_band: int
    probabilities: dict[str, float]  # uci -> p
    entropy: float
    played_probability: float | None
    played_rank: int | None
    surprisal: float | None
    note: str


def _softmax(scores: list[float], temperature: float) -> list[float]:
    arr = np.asarray(scores, dtype=np.float64) / max(temperature, 1e-6)
    arr = arr - arr.max()
    ex = np.exp(arr)
    return (ex / ex.sum()).tolist()


def policy_from_stockfish(
    board: chess.Board,
    analysis: PositionAnalysis,
    played_uci: str,
    elo: int | None,
) -> HumanPolicy:
    """Surrogate human policy: softmax over MultiPV CP with Elo temperature.

    Moves outside MultiPV share a small residual mass uniformly over remaining
    legal moves so surprisal is defined for all legal plays.
    """
    elo_band = nearest_elo_band(elo)
    temp = _temperature_for_elo(elo_band)
    legal = [m.uci() for m in board.legal_moves]
    if not legal:
        return HumanPolicy(
            backend="surrogate",
            elo_band=elo_band,
            probabilities={},
            entropy=0.0,
            played_probability=None,
            played_rank=None,
            surprisal=None,
            note="No legal moves",
        )

    line_by_uci = {line.uci: line for line in analysis.lines}
    # Score: prefer CP; mate in N as large positive/negative.
    scored: list[tuple[str, float]] = []
    for line in analysis.lines:
        if line.mate is not None:
            score = 10000.0 - abs(line.mate) * 100 if line.mate > 0 else -10000.0
        else:
            score = float(line.score_cp or 0)
        scored.append((line.uci, score))

    if scored:
        probs_top = _softmax([s for _, s in scored], temp)
        probs = {uci: p for (uci, _), p in zip(scored, probs_top, strict=True)}
        mass_top = sum(probs.values())
        residual = max(0.0, 1.0 - mass_top) + 1e-9
    else:
        probs = {}
        residual = 1.0

    outside = [u for u in legal if u not in probs]
    if outside:
        share = residual / len(outside)
        for u in outside:
            probs[u] = share
    else:
        # Renormalize
        total = sum(probs.values()) or 1.0
        probs = {k: v / total for k, v in probs.items()}

    # Entropy
    entropy = -sum(p * math.log(p + 1e-12) for p in probs.values())

    played_p = probs.get(played_uci)
    surprisal = None if played_p is None else -math.log(played_p + 1e-12)

    # Rank among legal by descending probability
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    played_rank = next((i + 1 for i, (u, _) in enumerate(ranked) if u == played_uci), None)

    return HumanPolicy(
        backend="surrogate-stockfish-multipv",
        elo_band=elo_band,
        probabilities={k: float(v) for k, v in list(probs.items())[:20]},
        entropy=float(entropy),
        played_probability=float(played_p) if played_p is not None else None,
        played_rank=played_rank,
        surprisal=float(surprisal) if surprisal is not None else None,
        note=(
            "Surrogate policy (not Maia-3). Install Maia weights and set "
            "LAB_HUMAN_MODEL_BACKEND=maia for neural human priors."
        ),
    )


def describe_backend() -> dict[str, Any]:
    backend = settings.human_model_backend
    return {
        "requested_backend": backend,
        "active_backend": "surrogate-stockfish-multipv" if backend != "maia" else "maia-pending",
        "elo_bands": list(ELO_BANDS),
        "maia_weights_configured": bool(settings.maia_weights_path),
        "status": (
            "tested-surrogate"
            if backend != "maia"
            else "proposed-maia-loader-needs-weights"
        ),
        "disclaimer": (
            "Surrogate distributions approximate rating-conditioned move preference "
            "for research baselines only. They are not claims about real player intent "
            "and must not be used to optimize evasion of anti-cheat systems."
        ),
    }
