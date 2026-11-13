from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "synthetic_example.pgn"
client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["advisor_untouched"] is True


def test_import_and_analysis_smoke():
    pgn = SAMPLE.read_text()
    # Shorter game for CI speed — take first 8 plies via truncated parse by using mini pgn
    mini = """
[Event "Synthetic Anti-Cheat Lab Example"]
[White "HonestPlayerA"]
[Black "HonestPlayerB"]
[Result "*"]
[WhiteElo "1620"]
[BlackElo "1580"]
[TimeControl "600+0"]
[Annotator "synthetic-demo"]

1. e4 {[%clk 0:09:50]} e5 {[%clk 0:09:48]} 2. Nf3 {[%clk 0:09:40]} Nc6 {[%clk 0:09:30]}
3. Bc4 {[%clk 0:09:20]} Bc5 {[%clk 0:09:10]} *
"""
    imp = client.post("/api/v1/games/import", json={"pgn_text": mini, "platform": "offline"})
    assert imp.status_code == 200, imp.text
    game_id = imp.json()["game_id"]

    an = client.post(
        "/api/v1/analysis",
        json={"game_id": game_id, "multipv": 3, "depth": 8},
    )
    # Stockfish may be missing in some CI — accept 503
    if an.status_code == 503:
        return
    assert an.status_code == 200, an.text
    analysis_id = an.json()["analysis_id"]
    report = client.get(f"/api/v1/analysis/{analysis_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["synthetic_demo"] is True
    assert body["white"]["calibrated_cheat_probability"] is None
    assert "not cheat verdicts" in body["disclaimer"].lower()
