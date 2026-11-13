# mychess

Upload / ⌘V ảnh bàn cờ (Chess.com, Lichess…) → nhận diện thế cờ → Stockfish gợi ý nước đi.

## Move Advisor v2 (separate app)

Dual suggestions: **Stockfish best** + **human-typical (Maia-style by Elo)**. Educational only — does not modify Ver1 (`advisor/`).

See [`lab/README.md`](lab/README.md) — API `:8100`, UI `:5174`.

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

App tìm binary tại `stockfish/stockfish-macos-universal` (hoặc set `STOCKFISH_PATH`).

## Deploy (production)

Không chạy `uvicorn --reload` / không mở `--host 0.0.0.0` trực tiếp ra internet. Nên:

1. Build frontend: `cd advisor/frontend && npm ci && npm run build`
2. Serve `advisor/frontend/dist` bằng nginx/Caddy
3. Proxy `/api/` → uvicorn (1–2 workers)
4. TLS ở reverse proxy. Để giới hạn theo IP hoạt động đúng, proxy cần ghi đè `X-Forwarded-For` bằng IP client đã xác thực. Chỉ cấu hình Uvicorn tin địa chỉ của reverse proxy qua `--forwarded-allow-ips`.

Ví dụ env backend:

```bash
export APP_ENV=production
export ALLOWED_ORIGINS=https://your.domain
export ALLOWED_HOSTS=your.domain,localhost
export STOCKFISH_PATH=/usr/local/bin/stockfish
export MAX_ENGINE_CONCURRENCY=2
export MAX_DETECT_CONCURRENCY=1
export ANALYZE_RATE_PER_MIN=30
export DETECT_RATE_PER_MIN=20
export MAX_RATE_LIMIT_KEYS=10000
```

Chạy API:

```bash
cd advisor/backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --forwarded-allow-ips=127.0.0.1
```

Bảo vệ sẵn có: rate limit theo IP, giới hạn Stockfish/detect concurrent, validate upload (magic bytes + pixel limit), tắt `/docs` khi `APP_ENV=production`, CORS theo `ALLOWED_ORIGINS`, security headers.

## Tính năng

- Nhận diện bàn từ screenshot (crop + đoán lượt đi)
- Click-to-move kiểu Chess.com (ô tròn nước đi)
- Stockfish suy nghĩ progressive 0→10s, cập nhật mũi tên
- Undo / Reset / Xoay bàn
- Đi quân bất cứ lúc nào (kể cả khi đang suy nghĩ)
