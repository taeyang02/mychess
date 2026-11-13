"""Schemas for dual Stockfish + human-typical suggestions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SuggestRequest(BaseModel):
    fen: str = Field(..., min_length=1, max_length=128)
    turn: Literal["white", "black"] | None = None
    elo: int = Field(default=1500, ge=600, le=2800)
    depth: int = Field(default=14, ge=6, le=22)
    multipv: int = Field(default=5, ge=3, le=10)
    max_time_s: float = Field(default=10.0, ge=0.5, le=10.0)


class MoveLine(BaseModel):
    rank: int
    san: str
    uci: str
    score_cp: int | None = None
    mate: int | None = None
    eval_text: str | None = None
    probability: float | None = None
    pv_san: list[str] = Field(default_factory=list)


class SuggestResponse(BaseModel):
    fen: str
    turn: Literal["white", "black"]
    elo_band: int
    depth: int = 0
    elapsed_ms: int = 0
    max_ms: int = 0
    done: bool = True
    engine: dict[str, Any]
    human: dict[str, Any]
    stockfish_best: MoveLine
    stockfish_lines: list[MoveLine]
    human_typical: MoveLine
    human_lines: list[MoveLine]
    disclaimer: str
