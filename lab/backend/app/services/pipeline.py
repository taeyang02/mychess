"""Analysis orchestration: features → detector → report."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.schemas.analysis import AnalysisReport
from app.services.detector import score_player
from app.services.features import (
    build_move_features,
    human_model_meta,
    phase_breakdown,
    summarize_player,
)
from app.services.pgn_parser import ParsedGame
from app.store.memory import LabStore


def run_analysis(
    store: LabStore,
    analysis_id: str,
    game: ParsedGame,
    *,
    multipv: int,
    depth: int,
    side: str = "both",
    platform: str = "offline",
) -> AnalysisReport:
    store.update_analysis(analysis_id, status="running")
    try:
        moves = build_move_features(game, multipv=multipv, depth=depth, side=side)
        white_moves = [m for m in moves if m.color == "white"]
        black_moves = [m for m in moves if m.color == "black"]
        white_ano = score_player(white_moves, game.metadata.get("white_elo"))
        black_ano = score_player(black_moves, game.metadata.get("black_elo"))

        white = summarize_player(
            "white",
            moves,
            game.metadata.get("white_elo"),
            platform,
            white_ano.score,
            white_ano.percentile,
        )
        black = summarize_player(
            "black",
            moves,
            game.metadata.get("black_elo"),
            platform,
            black_ano.score,
            black_ano.percentile,
        )

        synthetic = "synthetic" in (game.headers.get("Annotator") or "").lower() or (
            "synthetic" in (game.headers.get("Event") or "").lower()
        )

        timing = {
            "clock_present": not game.missing.get("clock_comments", True),
            "think_times_available": sum(1 for t in game.think_times if t is not None),
            "think_times_missing": sum(1 for t in game.think_times if t is None),
            "white_mean_think": white.mean_think_time,
            "black_mean_think": black.mean_think_time,
            "note": "Timing signals alone never imply engine use.",
        }

        baseline_comparison = {
            "white": {
                "anomaly": white_ano.__dict__,
                "rating_band_note": "Lichess and Chess.com ratings are NOT interchangeable",
            },
            "black": {
                "anomaly": black_ano.__dict__,
                "rating_band_note": "Lichess and Chess.com ratings are NOT interchangeable",
            },
            "baseline_type": "synthetic-honest-priors",
            "baseline_status": "proposed-until-fitted-on-verified-honest-corpora",
        }

        report = AnalysisReport(
            analysis_id=analysis_id,
            game_id=store.get_analysis(analysis_id).game_id if store.get_analysis(analysis_id) else "",
            synthetic_demo=synthetic,
            status="completed",
            data_quality={
                "warnings": game.warnings,
                "missing_fields": game.metadata.get("missing_fields", []),
                "validated_moves": len(game.moves),
                "analyzed_moves": len(moves),
            },
            metadata=game.metadata,
            engine_config={
                "multipv": multipv,
                "depth": depth,
                "seed": settings.seed,
                "hash": "engine-default",
                "note": "Version captured at analysis time from UCI id",
            },
            human_model=human_model_meta(),
            white=white,
            black=black,
            phase_breakdown=phase_breakdown(moves),
            timing=timing,
            expert_review_moves=[m for m in moves if m.review_flag][:30],
            baseline_comparison=baseline_comparison,
            limitations=[
                "MVP human policy is a Stockfish-MultiPV surrogate, not Maia-3 weights.",
                "Anomaly percentiles use synthetic honest priors — not platform ground truth.",
                "No verified cheat labels → no calibrated cheat probability.",
                "Single-game anomaly is insufficient for any disciplinary claim.",
                "Missing clock/Elo fields reduce timing and rating-band validity.",
                "Search-budget sensitivity not fully swept in MVP (single depth).",
            ],
            disclaimer=(
                "Research / education tool. Outputs are anomaly scores and review flags, "
                "not cheat verdicts. Do not use to optimize evasion of anti-cheat systems "
                "or to advise moves in live rated games."
            ),
        )

        # Fix game_id on report
        arec = store.get_analysis(analysis_id)
        if arec:
            report.game_id = arec.game_id

        store.update_analysis(
            analysis_id,
            status="completed",
            moves=moves,
            report=report,
            error=None,
        )
        return report
    except Exception as exc:
        store.update_analysis(analysis_id, status="failed", error=str(exc))
        raise


def player_baseline_payload(store: LabStore, player_id: str) -> dict[str, Any]:
    base = store.player_baseline(player_id)
    platform = player_id.split(":", 1)[0] if ":" in player_id else "unknown"
    return {
        "player_id": player_id,
        "platform": platform,
        "sample_games": base["sample_games"],
        "rating_band": None,
        "metrics": {
            "imported_game_ids": base["game_ids"],
            "status": "insufficient-history" if base["sample_games"] < 5 else "partial",
        },
        "note": (
            "Player baselines require many honest games on the SAME platform. "
            "Cross-platform Elo comparison is disabled by design."
        ),
    }
