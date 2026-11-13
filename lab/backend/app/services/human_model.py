"""Human-typical move suggestions (Maia-style interface).

MVP: Elo-conditioned surrogate over Stockfish MultiPV with deterministic
Elo-noise so the top human pick can differ from Stockfish #1 (especially
at lower ratings). Real Maia weights can replace this sampler later.

Educational only — not for evading anti-cheat / lowering bot scores.
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


def _noise_sigma_for_elo(elo: int) -> float:
    """Centipawn-scale logit noise. Lower Elo → more often ≠ Stockfish #1."""
    # 800 → ~95, 2400 → ~8
    return max(8.0, 95.0 - (elo - 800) * (87.0 / 1600.0))


def _softmax(scores: list[float], temperature: float) -> list[float]:
    arr = np.asarray(scores, dtype=np.float64) / max(temperature, 1e-6)
    arr = arr - arr.max()
    ex = np.exp(arr)
    return (ex / ex.sum()).tolist()


def _stable_rng(fen: str, elo_band: int) -> np.random.Generator:
    # Deterministic per (position, elo band) so progressive updates stay stable.
    material = abs(hash((fen.split()[0], elo_band, settings.seed))) % (2**32 - 1)
    return np.random.default_rng(material)


@dataclass
class HumanSuggestion:
    elo_band: int
    backend: str
    lines: list[tuple[EngineLine, float]]  # line, probability
    note: str


def _engine_score(line: EngineLine) -> float:
    if line.mate is not None:
        return 10000.0 - abs(line.mate) * 100 if line.mate > 0 else -10000.0
    return float(line.score_cp or 0)


def _human_bias(board: chess.Board, line: EngineLine, elo_band: int) -> float:
    """Soft preferences that can reorder vs pure engine ranking."""
    try:
        move = chess.Move.from_uci(line.uci)
    except ValueError:
        return 0.0

    bias = 0.0
    # Lower Elo: prefer captures / checks slightly less “quiet engine” moves? 
    # Prefer developing / castling / captures as more “human-salient”.
    if board.is_castling(move):
        bias += 35.0 * (1.0 - (elo_band - 800) / 1600.0)
    if board.is_capture(move):
        bias += 18.0 * (1.0 - (elo_band - 800) / 2000.0)
    if board.gives_check(move) and elo_band <= 1600:
        bias += 12.0
    # Stronger players track engine more closely — less bias
    bias *= max(0.15, (2200 - elo_band) / 1400.0)
    return bias


def suggest_human_moves(
    board: chess.Board,
    analysis: PositionAnalysis,
    elo: int,
) -> HumanSuggestion:
    elo_band = nearest_elo_band(elo)
    temp = _temperature_for_elo(elo_band)
    sigma = _noise_sigma_for_elo(elo_band)
    rng = _stable_rng(board.fen(), elo_band)

    if settings.human_model_backend == "maia" and settings.maia_weights_path:
        backend = "maia-pending-loader"
        note = (
            "Maia weights path configured but neural loader not bundled in MVP; "
            "falling back to Elo surrogate over MultiPV."
        )
    else:
        backend = "surrogate-stockfish-multipv"
        note = (
            "Human-typical can differ from Stockfish via Elo temperature + bias + "
            "stable noise (Maia-compatible API). Educational only."
        )

    if not analysis.lines:
        legal = list(board.legal_moves)
        fake_lines: list[tuple[EngineLine, float]] = []
        if legal:
            move = legal[0]
            try:
                san = board.san(move)
            except ValueError:
                san = move.uci()
            el = EngineLine(1, move.uci(), san, None, None, [move.uci()])
            fake_lines.append((el, 1.0))
        return HumanSuggestion(elo_band, backend, fake_lines, note)

    # Logits that are NOT a monotone transform of engine rank → can differ from SF#1
    logits: list[float] = []
    for line in analysis.lines:
        base = _engine_score(line)
        bias = _human_bias(board, line, elo_band)
        noise = float(rng.normal(0.0, sigma))
        logits.append(base + bias + noise)

    probs = _softmax(logits, temp)
    ranked = sorted(
        [
            (line, float(p), logit)
            for line, p, logit in zip(analysis.lines, probs, logits, strict=True)
        ],
        key=lambda t: t[1],
        reverse=True,
    )

    relabeled: list[tuple[EngineLine, float]] = []
    for i, (line, p, _logit) in enumerate(ranked, start=1):
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
        "entropy_hint": "Lower Elo → higher chance human-typical ≠ Stockfish best",
    }
