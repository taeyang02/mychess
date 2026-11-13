from fastapi.testclient import TestClient

from app.main import app
from app.services.human_model import nearest_elo_band, suggest_human_moves
from app.services.stockfish_worker import analyze_position
import chess

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "move-advisor-v2"


def test_elo_bands():
    assert nearest_elo_band(1550) == 1600
    assert nearest_elo_band(900) == 800


def test_suggest_endpoint():
    r = client.post(
        "/api/v1/suggest",
        json={
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "elo": 1500,
            "depth": 8,
            "multipv": 3,
        },
    )
    if r.status_code == 503:
        return
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stockfish_best"]["san"]
    assert body["human_typical"]["san"]
    assert body["human_typical"]["probability"] is not None
    assert "evading" in body["disclaimer"].lower() or "anti-cheat" in body["disclaimer"].lower()
    assert body["engine"]["role"] == "best_play"
    assert body["human"]["role"] == "human_typical"


def test_human_ranking_uses_probabilities():
    try:
        analysis = analyze_position(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            multipv=3,
            depth=8,
        )
    except FileNotFoundError:
        return
    board = chess.Board()
    human = suggest_human_moves(board, analysis, 1200)
    assert human.lines
    probs = [p for _, p in human.lines]
    assert abs(sum(probs) - 1.0) < 1e-5
    assert probs == sorted(probs, reverse=True)
