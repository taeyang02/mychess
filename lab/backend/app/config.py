"""Advisor v2 configuration."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAB_", extra="ignore")

    app_env: str = "development"
    allowed_origins: str = "http://127.0.0.1:5174,http://localhost:5174"
    stockfish_path: str = ""
    multipv: int = 5
    analysis_depth: int = 14
    human_model_backend: str = "surrogate"  # surrogate until Maia weights configured
    maia_weights_path: str = ""
    default_elo: int = 1500
    enable_docs: bool = True
    seed: int = 42

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()


def resolve_stockfish() -> Path:
    if settings.stockfish_path:
        path = Path(settings.stockfish_path)
    else:
        env = os.getenv("STOCKFISH_PATH", "").strip()
        candidates = [
            Path(env) if env else None,
            ROOT / "stockfish" / "stockfish-macos-universal",
            ROOT / "stockfish" / "stockfish-ubuntu-x86-64-avx2",
            ROOT / "stockfish" / "stockfish",
            Path("/usr/bin/stockfish"),
            Path("/usr/local/bin/stockfish"),
            Path("/usr/games/stockfish"),
        ]
        path = next((p for p in candidates if p and p.is_file()), None)
        if path is None:
            raise FileNotFoundError("Stockfish not found; set LAB_STOCKFISH_PATH or STOCKFISH_PATH")
    if not path.is_file():
        raise FileNotFoundError(f"Stockfish not found at {path}")
    return path
