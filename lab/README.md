# Move Advisor v2

Dual suggestions for training:

1. **Stockfish** — strongest / eval / MultiPV  
2. **Human-typical (Maia-style)** — Elo-band style suggestion  

Educational only. **Not** an anti-cheat evasion tool. Ver1 Move Advisor (`advisor/`) stays untouched.

## Run

```bash
# API :8100
cd lab/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100

# UI :5174
cd lab/frontend
npm install
npm run dev
```

Open http://localhost:5174

## API

`POST /api/v1/suggest`

```json
{ "fen": "...", "elo": 1500, "depth": 14, "multipv": 5 }
```

Returns `stockfish_best` + `human_typical` (separate fields).

Human model MVP = Elo surrogate over MultiPV. Set `LAB_HUMAN_MODEL_BACKEND=maia` + `LAB_MAIA_WEIGHTS_PATH` when real Maia weights are available.
