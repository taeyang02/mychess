"""Statistical anomaly detector (offline research MVP).

Without verified cheat labels this module emits anomaly scores / empirical
percentiles against synthetic honest baselines — never calibrated P(cheat).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.config import settings
from app.schemas.analysis import MoveFeature

# Hand-crafted "honest" baseline centroids by rating band (synthetic research priors).
# Values are illustrative and marked synthetic — not fitted on real platform data.
SYNTHETIC_HONEST_PRIORS = {
    800: {"avg_cp_loss": 95, "top1": 0.28, "surprisal": 2.4, "think": 8.0},
    1000: {"avg_cp_loss": 80, "top1": 0.32, "surprisal": 2.2, "think": 7.5},
    1200: {"avg_cp_loss": 68, "top1": 0.36, "surprisal": 2.0, "think": 7.0},
    1400: {"avg_cp_loss": 55, "top1": 0.40, "surprisal": 1.85, "think": 6.5},
    1600: {"avg_cp_loss": 45, "top1": 0.45, "surprisal": 1.7, "think": 6.0},
    1800: {"avg_cp_loss": 36, "top1": 0.50, "surprisal": 1.55, "think": 5.5},
    2000: {"avg_cp_loss": 28, "top1": 0.55, "surprisal": 1.4, "think": 5.0},
    2200: {"avg_cp_loss": 22, "top1": 0.60, "surprisal": 1.25, "think": 4.5},
    2400: {"avg_cp_loss": 16, "top1": 0.65, "surprisal": 1.1, "think": 4.0},
}


def _band(elo: int | None) -> int:
    if elo is None:
        return 1600
    bands = sorted(SYNTHETIC_HONEST_PRIORS)
    return min(bands, key=lambda b: abs(b - elo))


def _player_vector(moves: list[MoveFeature]) -> np.ndarray:
    def mean(xs: list[float | None], default: float) -> float:
        vals = [x for x in xs if x is not None]
        return float(np.mean(vals)) if vals else default

    avg_cp = mean([m.cp_loss for m in moves], 50.0)
    top1 = mean([1.0 if m.stockfish_top1 else 0.0 for m in moves], 0.4)
    surprisal = mean([m.maia_surprisal for m in moves], 1.7)
    think = mean([m.think_time_seconds for m in moves], 6.0)
    entropy = mean([m.human_policy_entropy for m in moves], 2.5)
    # Engine-like signature: high top1 + low cp + low think + high surprisal mismatch
    return np.array([avg_cp, top1, surprisal, think, entropy], dtype=np.float64)


@dataclass
class AnomalyResult:
    score: float  # higher = more unusual vs synthetic honest baseline
    percentile: float  # 0-100 empirical vs bootstrap honest samples
    method: str
    components: dict[str, float]
    explanation: list[str]
    label_status: str


def _bootstrap_honest_samples(elo: int | None, n: int = 400) -> np.ndarray:
    rng = np.random.default_rng(settings.seed)
    prior = SYNTHETIC_HONEST_PRIORS[_band(elo)]
    samples = []
    for _ in range(n):
        avg_cp = rng.normal(prior["avg_cp_loss"], prior["avg_cp_loss"] * 0.25)
        top1 = np.clip(rng.normal(prior["top1"], 0.08), 0.05, 0.95)
        surprisal = rng.normal(prior["surprisal"], 0.35)
        think = max(0.5, rng.normal(prior["think"], 2.0))
        entropy = rng.normal(2.4, 0.4)
        samples.append([avg_cp, top1, surprisal, think, entropy])
    return np.asarray(samples, dtype=np.float64)


def score_player(moves: list[MoveFeature], elo: int | None) -> AnomalyResult:
    if len(moves) < 5:
        return AnomalyResult(
            score=0.0,
            percentile=50.0,
            method="insufficient-moves",
            components={},
            explanation=["Fewer than 5 moves — anomaly scoring skipped"],
            label_status="unlabeled-research-only",
        )

    vec = _player_vector(moves)
    honest = _bootstrap_honest_samples(elo)
    scaler = StandardScaler()
    honest_s = scaler.fit_transform(honest)
    vec_s = scaler.transform(vec.reshape(1, -1))[0]

    # IsolationForest on synthetic honest cloud
    iso = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=settings.seed,
    )
    iso.fit(honest_s)
    # decision_function: higher = more normal; invert for anomaly
    raw = float(-iso.decision_function(vec_s.reshape(1, -1))[0])

    # Distance vs prior centroid (z-score L2)
    centroid = honest_s.mean(axis=0)
    zdist = float(np.linalg.norm(vec_s - centroid))

    # Optional logistic "prototype" — trained ONLY on synthetic honest vs synthetic
    # engine-like vectors. Labels are synthetic; output is NOT P(cheat).
    engine_like = honest.copy()
    engine_like[:, 0] *= 0.35  # lower cp loss
    engine_like[:, 1] = np.clip(engine_like[:, 1] + 0.25, 0, 0.98)  # higher top1
    engine_like[:, 3] *= 0.4  # faster
    X = np.vstack([honest_s, scaler.transform(engine_like)])
    y = np.array([0] * len(honest_s) + [1] * len(engine_like))
    clf = LogisticRegression(max_iter=200, random_state=settings.seed)
    clf.fit(X, y)
    proto = float(clf.predict_proba(vec_s.reshape(1, -1))[0, 1])

    score = 0.45 * zdist + 0.35 * max(0.0, raw * 5) + 0.20 * proto

    # Empirical percentile of zdist among honest distances
    honest_d = np.linalg.norm(honest_s - centroid, axis=1)
    percentile = float((honest_d < zdist).mean() * 100.0)

    prior = SYNTHETIC_HONEST_PRIORS[_band(elo)]
    explanations: list[str] = []
    avg_cp, top1, surprisal, think, _entropy = vec.tolist()
    if top1 > prior["top1"] + 0.15:
        explanations.append(
            f"Top-1 engine agreement {top1:.0%} is high vs synthetic {prior['top1']:.0%} band prior"
        )
    if avg_cp < prior["avg_cp_loss"] * 0.5:
        explanations.append(
            f"Average CP loss {avg_cp:.0f} is unusually low vs synthetic prior {prior['avg_cp_loss']}"
        )
    if think < prior["think"] * 0.4:
        explanations.append(
            f"Mean think time {think:.1f}s is low vs synthetic prior {prior['think']}s (clock quality dependent)"
        )
    if not explanations:
        explanations.append("Metrics within broad synthetic honest envelope for this rating band")

    explanations.append(
        "Synthetic baselines ≠ real platform ground truth. Do not treat as a cheat verdict."
    )

    return AnomalyResult(
        score=round(score, 4),
        percentile=round(percentile, 2),
        method="isolation-forest+zdist+synthetic-logistic-prototype",
        components={
            "zdist": round(zdist, 4),
            "isolation_raw": round(raw, 4),
            "synthetic_prototype": round(proto, 4),
            "avg_cp_loss": round(avg_cp, 2),
            "top1_agreement": round(top1, 4),
            "mean_surprisal": round(surprisal, 4),
            "mean_think_s": round(think, 3),
        },
        explanation=explanations,
        label_status="no-verified-cheat-labels",
    )
