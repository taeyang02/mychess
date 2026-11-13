FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends stockfish \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV LAB_ENABLE_DOCS=true
ENV STOCKFISH_PATH=/usr/games/stockfish
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
