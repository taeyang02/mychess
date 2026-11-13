from pathlib import Path

from app.services.pgn_parser import parse_pgn_text

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "synthetic_example.pgn"


def test_parse_synthetic_sample():
    text = SAMPLE.read_text()
    game = parse_pgn_text(text, platform="offline")
    assert game.metadata["white_elo"] == 1620
    assert game.metadata["black_elo"] == 1580
    assert len(game.moves) >= 20
    assert game.moves[0].uci == "e2e4"
    assert game.moves[0].fen_before.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")
    # clocks present → think times derived
    assert any(t is not None for t in game.think_times)


def test_missing_elo_flagged():
    pgn = """
[Event "Test"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 *
"""
    game = parse_pgn_text(pgn)
    assert game.missing["WhiteElo"] is True
    assert "WhiteElo" in game.metadata["missing_fields"]
