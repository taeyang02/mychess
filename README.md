# mychess

Upload / ⌘V ảnh bàn cờ (Chess.com, Lichess…) → nhận diện thế cờ → Stockfish gợi ý nước đi.

## Chạy local

### Backend

```bash
cd advisor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd advisor/frontend
npm install
npm run dev
```

Mở http://127.0.0.1:5173

### Stockfish binary (macOS Apple Silicon)

```bash
curl -sL "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-macos-m1-apple-silicon.tar" -o /tmp/sf.tar
tar -xf /tmp/sf.tar -C /tmp
cp /tmp/stockfish/stockfish-macos-m1-apple-silicon stockfish/stockfish-macos-universal
chmod +x stockfish/stockfish-macos-universal
```

App tìm binary tại `stockfish/stockfish-macos-universal`.

## Tính năng

- Nhận diện bàn từ screenshot (crop + đoán lượt đi)
- Click-to-move kiểu Chess.com (ô tròn nước đi)
- Stockfish suy nghĩ progressive 0→10s, cập nhật mũi tên
- Undo / Reset / Xoay bàn
- Đi quân bất cứ lúc nào (kể cả khi đang suy nghĩ)
