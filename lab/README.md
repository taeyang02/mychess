# Anti-Cheat Lab v2 (offline)

Chess Human Behavior & Anti-Cheat Lab — **separate** from Move Advisor.

- Advisor (unchanged): port `8000` / UI `5173`
- Lab v2: API `8100` / UI `5174`

This app analyzes **completed PGN games** offline. It does **not** suggest moves in live games and does **not** output calibrated cheat probabilities without verified labels.

## Quick start

### Backend

```bash
cd lab/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

### Frontend

```bash
cd lab/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5174

### Tests

```bash
cd lab/backend
source .venv/bin/activate
pytest -q
```

## API

- `POST /api/v1/games/import`
- `POST /api/v1/analysis`
- `GET /api/v1/analysis/{id}`
- `GET /api/v1/analysis/{id}/moves`
- `GET /api/v1/analysis/{id}/report`
- `POST /api/v1/batch-analysis`
- `GET /api/v1/players/{id}/baseline`

## Docs pack

Full 12-part research pack: [`docs/RESEARCH.md`](docs/RESEARCH.md)

## Human model note

MVP uses an Elo-conditioned **surrogate** policy from Stockfish MultiPV (softmax). Maia-3 weights can be plugged later via `LAB_HUMAN_MODEL_BACKEND=maia` + `LAB_MAIA_WEIGHTS_PATH` without changing the API surface.
