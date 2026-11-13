import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.human_model import nearest_elo_band

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "move-advisor-v2"


def test_elo_bands():
    assert nearest_elo_band(1550) == 1600
    assert nearest_elo_band(900) == 800


def test_suggest_stream_progressive():
    with client.stream(
        "POST",
        "/api/v1/suggest/stream",
        json={
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "elo": 1500,
            "multipv": 3,
            "max_time_s": 1.0,
        },
    ) as res:
        if res.status_code == 503:
            return
        assert res.status_code == 200, res.text
        lines = [ln for ln in res.iter_lines() if ln]
        assert lines
        updates = [json.loads(ln) for ln in lines]
        if updates and updates[-1].get("error"):
            # Stockfish missing in some environments
            return
        assert updates[-1]["done"] is True
        assert updates[-1]["elapsed_ms"] >= 500
        assert updates[-1]["max_ms"] == 1000
        assert updates[-1]["stockfish_best"]["san"]
        assert updates[-1]["depth"] >= 1
