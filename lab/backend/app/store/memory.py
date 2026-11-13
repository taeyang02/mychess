"""In-memory store for MVP (swap for PostgreSQL via same interface)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas.analysis import AnalysisReport, MoveFeature
from app.services.pgn_parser import ParsedGame


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GameRecord:
    game_id: str
    parsed: ParsedGame
    platform: str
    label: str | None
    created_at: str
    source: str


@dataclass
class AnalysisRecord:
    analysis_id: str
    game_id: str
    status: str
    created_at: str
    updated_at: str
    config: dict[str, Any] = field(default_factory=dict)
    moves: list[MoveFeature] = field(default_factory=list)
    report: AnalysisReport | None = None
    error: str | None = None


class LabStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.games: dict[str, GameRecord] = {}
        self.analyses: dict[str, AnalysisRecord] = {}
        self.player_games: dict[str, list[str]] = {}

    def import_game(self, parsed: ParsedGame, *, platform: str, label: str | None, source: str) -> GameRecord:
        gid = _id("game")
        rec = GameRecord(
            game_id=gid,
            parsed=parsed,
            platform=platform,
            label=label,
            created_at=_now(),
            source=source,
        )
        with self._lock:
            self.games[gid] = rec
            for name_key in ("White", "Black"):
                name = parsed.headers.get(name_key) or "unknown"
                pid = f"{platform}:{name}".lower()
                self.player_games.setdefault(pid, []).append(gid)
        return rec

    def get_game(self, game_id: str) -> GameRecord | None:
        return self.games.get(game_id)

    def create_analysis(self, game_id: str, config: dict[str, Any]) -> AnalysisRecord:
        aid = _id("an")
        rec = AnalysisRecord(
            analysis_id=aid,
            game_id=game_id,
            status="queued",
            created_at=_now(),
            updated_at=_now(),
            config=config,
        )
        with self._lock:
            self.analyses[aid] = rec
        return rec

    def update_analysis(self, analysis_id: str, **kwargs: Any) -> AnalysisRecord:
        with self._lock:
            rec = self.analyses[analysis_id]
            for k, v in kwargs.items():
                setattr(rec, k, v)
            rec.updated_at = _now()
            return rec

    def get_analysis(self, analysis_id: str) -> AnalysisRecord | None:
        return self.analyses.get(analysis_id)

    def player_baseline(self, player_id: str) -> dict[str, Any]:
        gids = self.player_games.get(player_id.lower(), [])
        return {
            "player_id": player_id,
            "sample_games": len(gids),
            "game_ids": gids[-50:],
        }


store = LabStore()
