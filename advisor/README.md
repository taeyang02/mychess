# Move Advisor

Web app local: **upload ảnh bàn cờ → nhận diện FEN → chọn bên đi → Stockfish gợi ý nước tiếp theo**.

## Yêu cầu

- Python 3.11+
- Node.js 20+
- Binary Stockfish tại [`../stockfish/stockfish-macos-universal`](../stockfish/stockfish-macos-universal)

Nếu thiếu binary (macOS Apple Silicon):

```bash
curl -sL "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-macos-m1-apple-silicon.tar" -o /tmp/sf.tar
tar -xf /tmp/sf.tar -C /tmp
cp /tmp/stockfish/stockfish-macos-m1-apple-silicon stockfish/stockfish-macos-universal
chmod +x stockfish/stockfish-macos-universal
```

## Chạy backend

```bash
cd advisor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Chạy frontend

```bash
cd advisor/frontend
npm install
npm run dev
```

Mở http://127.0.0.1:5173 — Vite proxy `/api` sang backend `:8000`.

## Luồng dùng

1. Upload screenshot / diagram bàn cờ (Chess.com, Lichess…).
2. Kiểm tra bàn tương tác; kéo quân để sửa nếu nhận diện lệch.
3. Chọn **Trắng đi** / **Đen đi**.
4. Bấm **Phân tích với Stockfish** để xem nước gợi ý, eval và PV.

## API

- `POST /api/detect` — multipart field `image`
- `POST /api/analyze` — JSON `{ "fen", "turn": "white"|"black", "depth"? }`
- `GET /api/health`

## Giới hạn

- Ảnh chụp bàn thật kém chính xác hơn screenshot/diagram.
- Ảnh tĩnh không luôn chắc lượt đi — luôn xác nhận lại bên đi trước khi phân tích.
