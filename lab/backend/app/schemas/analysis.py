"""Pydantic schemas for Anti-Cheat Lab API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportGameRequest(BaseModel):
    pgn_text: str | None = Field(default=None, max_length=500_000)
    source_url: str | None = Field(default=None, max_length=500)
    platform: Literal["unknown", "lichess", "chesscom", "offline"] = "offline"
    label: str | None = Field(default=None, max_length=120)


class ImportGameResponse(BaseModel):
    game_id: str
    status: str
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any]


class AnalysisRequest(BaseModel):
    game_id: str
    multipv: int = Field(default=5, ge=1, le=10)
    depth: int = Field(default=12, ge=6, le=20)
    side: Literal["both", "white", "black"] = "both"
    note: str | None = None


class BatchAnalysisRequest(BaseModel):
    game_ids: list[str] = Field(min_length=1, max_length=20)
    multipv: int = Field(default=5, ge=1, le=10)
    depth: int = Field(default=12, ge=6, le=20)


class AnalysisJobResponse(BaseModel):
    analysis_id: str
    game_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str | None = None


class MoveFeature(BaseModel):
    ply: int
    color: Literal["white", "black"]
    fen_before: str
    san: str
    uci: str
    engine_rank: int | None
    cp_loss: float | None
    wdl_loss: float | None
    stockfish_top1: bool | None
    stockfish_top3: bool | None
    maia_probability: float | None
    maia_rank: int | None
    maia_surprisal: float | None
    human_policy_entropy: float | None
    tactical_context: bool
    phase: Literal["opening", "middlegame", "endgame"]
    clock_before: float | None
    clock_after: float | None
    think_time_seconds: float | None
    missing_fields: list[str]
    stockfish_top_moves: list[dict[str, Any]] = Field(default_factory=list)
    review_flag: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class PlayerSummary(BaseModel):
    color: Literal["white", "black"]
    elo: int | None
    elo_missing: bool
    platform: str
    avg_cp_loss: float | None
    top1_agreement: float | None
    top3_agreement: float | None
    mean_maia_probability: float | None
    mean_surprisal: float | None
    blunder_rate: float | None
    inaccuracy_rate: float | None
    mean_think_time: float | None
    move_count: int
    anomaly_percentile: float | None
    anomaly_score: float | None
    calibrated_cheat_probability: None = None  # intentionally unused without verified labels
    confidence_note: str


class AnalysisReport(BaseModel):
    analysis_id: str
    game_id: str
    synthetic_demo: bool
    status: str
    data_quality: dict[str, Any]
    metadata: dict[str, Any]
    engine_config: dict[str, Any]
    human_model: dict[str, Any]
    white: PlayerSummary
    black: PlayerSummary
    phase_breakdown: dict[str, Any]
    timing: dict[str, Any]
    expert_review_moves: list[MoveFeature]
    baseline_comparison: dict[str, Any]
    limitations: list[str]
    disclaimer: str


class PlayerBaselineResponse(BaseModel):
    player_id: str
    platform: str
    sample_games: int
    rating_band: str | None
    metrics: dict[str, Any]
    note: str
