"""Chess Move Advisor API."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from detector import DetectionError, detect_position
from engine import EngineError, analyze_position, iter_analyze_progressive

app = FastAPI(title="Chess Move Advisor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    fen: str = Field(..., min_length=1)
    turn: Literal["white", "black"] | None = None
    depth: int | None = Field(default=None, ge=1, le=30)
    movetime_ms: int | None = Field(default=None, ge=50, le=15000)
    max_time_s: float = Field(default=10.0, ge=0.5, le=15.0)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/detect")
async def detect(image: UploadFile = File(...)) -> dict:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image upload")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 15MB)")

    try:
        return detect_position(data, filename=image.filename or "board.png")
    except DetectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}") from exc


@app.post("/api/analyze")
def analyze(body: AnalyzeRequest) -> dict:
    try:
        return analyze_position(
            fen=body.fen,
            turn=body.turn,
            depth=body.depth if body.movetime_ms is None else None,
            movetime_ms=body.movetime_ms,
        )
    except EngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.post("/api/analyze/stream")
def analyze_stream(body: AnalyzeRequest) -> StreamingResponse:
    """NDJSON stream: Stockfish thinks 0→max_time_s, emits updates when suggestion changes."""

    def generate():
        try:
            for update in iter_analyze_progressive(
                fen=body.fen,
                turn=body.turn,
                max_time_s=body.max_time_s,
            ):
                yield json.dumps(update, ensure_ascii=False) + "\n"
        except EngineError as exc:
            yield json.dumps({"error": str(exc), "done": True}, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            yield json.dumps(
                {"error": f"Analysis failed: {exc}", "done": True},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
