from app.schemas.analysis import MoveFeature
from app.services.detector import score_player


def _mv(**kwargs):
    base = dict(
        ply=1,
        color="white",
        fen_before="start",
        san="e4",
        uci="e2e4",
        engine_rank=1,
        cp_loss=40.0,
        wdl_loss=0.02,
        stockfish_top1=True,
        stockfish_top3=True,
        maia_probability=0.2,
        maia_rank=2,
        maia_surprisal=1.6,
        human_policy_entropy=2.5,
        tactical_context=False,
        phase="opening",
        clock_before=600.0,
        clock_after=590.0,
        think_time_seconds=10.0,
        missing_fields=[],
    )
    base.update(kwargs)
    return MoveFeature(**base)


def test_anomaly_not_cheat_probability():
    moves = [_mv(ply=i, cp_loss=40 + i) for i in range(1, 12)]
    result = score_player(moves, 1600)
    assert result.label_status == "no-verified-cheat-labels"
    assert 0 <= result.percentile <= 100


def test_engine_like_pattern_higher_score():
    honest = [
        _mv(ply=i, engine_rank=3, cp_loss=50, stockfish_top1=False, think_time_seconds=8)
        for i in range(1, 15)
    ]
    engineish = [
        _mv(
            ply=i,
            engine_rank=1,
            cp_loss=5,
            stockfish_top1=True,
            maia_surprisal=4.0,
            think_time_seconds=1.0,
        )
        for i in range(1, 15)
    ]
    h = score_player(honest, 1600)
    e = score_player(engineish, 1600)
    assert e.score >= h.score
