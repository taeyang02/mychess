# Move Advisor v2

Giao diện giống **ver1** (upload/⌘V, click-to-move, undo/reset, progress bar) + gợi ý kép:

- **Stockfish** (mũi tên xanh)
- **Human-typical / Maia-style** theo Elo (mũi tên vàng)

Ver1 (`advisor/`) không bị đụng.

## Chạy

```bash
# API v2 :8100
cd lab/backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100

# UI v2 :5174
cd lab/frontend && npm install && npm run dev
```

Nhận diện ảnh (`/api/detect`) proxy sang advisor ver1 `:8000` — cần chạy thêm ver1 backend nếu dùng upload ảnh:

```bash
cd advisor/backend && source .venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Không có ảnh vẫn dùng được: startpos → auto suggest → click đi quân.
