# Chess Human Behavior & Anti-Cheat Lab — Research Pack

**Status legend**
- **Tested**: implemented and covered by automated tests or local Stockfish runs
- **Proposed**: designed, not fully implemented
- **Needs real data**: requires verified corpora / labels before claims

---

## Part 1 — Research findings (with sources)

1. Engine–human agreement rises with rating, but even masters deviate from MultiPV top-1 frequently in complex positions (see public Lichess / Chess.com methodology notes and academic cheat-detection literature such as Barnes & Hernandez-Castro style CPL analyses; platform blogs on Fair Play). **Needs real data** for our own fitted curves.
2. Centipawn loss is unstable under mate scores; win-probability / WDL loss is preferred when mates appear (Stockfish WDL / Lichess win% logistic family). **Tested** in MVP (`cp_loss` null when mate involved; `wdl_loss` used).
3. Move-time alone is a weak discriminator: players spike on tactics and blitz on forced recaptures. **Proposed** full timing model; MVP extracts `[%clk]` think times only.
4. Rare strong moves with low human-policy probability require **context** (prep, only-move, endgame tablebase). MVP flags for expert review, never auto-labels. **Tested** flag logic.
5. Cross-platform Elo is not interchangeable (Lichess vs Chess.com). MVP stores `platform` and refuses silent remapping. **Tested** schema/docs.

---

## Part 2 — System architecture

```
PGN Import → Parser/Validator → Position Queue (sync MVP)
        → Stockfish Worker (MultiPV, cached by FEN+depth+multipv)
        → Human Policy Worker (surrogate; Maia plug-in proposed)
        → Feature Store (in-memory MVP; Postgres proposed)
        → Statistical Detector (IsolationForest + z-distance + synthetic logistic prototype)
        → Report API → Vue Dashboard (v2)
```

Move Advisor (`advisor/`) remains a separate app/process. Lab listens on **8100** / UI **5174**.

---

## Part 3 — Database schema (proposed Postgres)

MVP uses in-memory store. Target schema:

```sql
CREATE TABLE games (
  game_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  pgn TEXT NOT NULL,
  headers JSONB NOT NULL,
  white_elo INT,
  black_elo INT,
  time_control TEXT,
  missing_fields JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analyses (
  analysis_id TEXT PRIMARY KEY,
  game_id TEXT REFERENCES games(game_id),
  status TEXT NOT NULL,
  engine_config JSONB NOT NULL,
  human_model JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE move_features (
  analysis_id TEXT REFERENCES analyses(analysis_id),
  ply INT,
  fen_before TEXT,
  san TEXT,
  uci TEXT,
  features JSONB NOT NULL,
  PRIMARY KEY (analysis_id, ply)
);

CREATE TABLE player_baselines (
  player_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  rating_band INT,
  metrics JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
```

Redis: queue + FEN analysis cache (**proposed** via compose profile `full`).

---

## Part 4 — Feature specification

Per move (implemented):  
`ply, fen_before, san, uci, engine_rank, cp_loss, wdl_loss, stockfish_top1, stockfish_top3, maia_probability, maia_rank, maia_surprisal, human_policy_entropy, tactical_context, phase, clock_before, clock_after, think_time_seconds, missing_fields, stockfish_top_moves, review_flag, review_reasons`.

No future-move leakage: each ply analyzed from `fen_before` only.

---

## Part 5 — Detection methodology

1. Build player vector: mean CP loss, top-1 rate, surprisal, think time, policy entropy.
2. Compare to **synthetic** honest bootstrap cloud for rating band.
3. Score = blend(z-distance, IsolationForest anomaly, synthetic logistic prototype).
4. Emit **percentile + score**, never calibrated P(cheat) without verified labels.
5. Expert-review moves: high surprisal + top-1 and/or low-p + fast think — contextual only.

Train/val/test by player+time, ROC/PR, calibration — **Needs real data**.

---

## Part 6 — Example input PGN

See `lab/samples/synthetic_example.pgn` (marked synthetic).

---

## Part 7 — Example report JSON

See `lab/docs/example_report.synthetic.json` (synthetic).

---

## Part 8 — UI dashboard specification

Vue 3 screen at port 5174:
- Import PGN / load synthetic sample
- Configure depth & MultiPV
- Report: metadata, per-side anomaly percentile, CP/top1, board (chessground), move table with review highlights, limitations & disclaimer
- Explicit copy: not a cheat verdict; no live coaching

---

## Part 9 — Source structure

```
lab/
  backend/app/{api,services,store,schemas,config,main}
  backend/tests/
  frontend/src/{views,components,api.ts}
  docs/
  samples/
  docker-compose.yml
```

---

## Part 10 — Automated tests

- `tests/test_pgn_parser.py` — clocks, Elo missing flags
- `tests/test_detector.py` — unlabeled scores; engine-like > honest synthetic score
- `tests/test_api.py` — health, import, analysis smoke (skips if Stockfish missing)

---

## Part 11 — Benchmark methodology

**Proposed** when labeled data exists:
- Split by player & time
- Metrics: ROC-AUC, PR-AUC, precision/recall, TPR/FPR, Brier, reliability curves, bootstrap CIs
- Slice FP rates: high Elo, brilliant games, forced-move heavy games
- Ablations: missing clock, missing Elo, depth 8/12/16
- Game-count curves: 1/5/20/50/100
- Synthetic stress tests held out from real test sets
- **Do not claim superiority to Chess.com Fair Play without matched benchmark**

---

## Part 12 — Limits & non-claims

- Surrogate ≠ Maia-3 until weights loaded
- Synthetic priors ≠ honest population
- No single-game cheat label
- No live-move advice API
- No evasion optimizer
- Mate CP “100” comparisons rejected
- Platform Elo not equated
- Unverified accuracy claims are out of scope
