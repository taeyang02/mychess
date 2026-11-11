"""Chess Move Advisor API."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from detector import DetectionError, detect_position
from engine import EngineError, analyze_position, iter_analyze_progressive
from errors import log_exception, public_engine_error
from limits import (
    ANALYZE_RATE,
    DETECT_RATE,
    BusyError,
    check_rate_limit,
    client_ip,
    detect_slot,
)
from settings import (
    ALLOWED_HOSTS,
    ALLOWED_ORIGINS,
    ENABLE_DOCS,
    IS_PROD,
    MAX_UPLOAD_BYTES,
)
from upload_security import UploadError, safe_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("advisor")

app = FastAPI(
    title="Chess Move Advisor",
    version="1.0.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if IS_PROD:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)

if ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


class AnalyzeRequest(BaseModel):
    fen: str = Field(..., min_length=1, max_length=128)
    turn: Literal["white", "black"] | None = None
    depth: int | None = Field(default=None, ge=1, le=30)
    movetime_ms: int | None = Field(default=None, ge=50, le=10000)
    max_time_s: float = Field(default=10.0, ge=0.5, le=10.0)


def _busy_http(exc: BusyError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "2"})


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {"status": "ok", "prod": IS_PROD}


@app.post("/api/detect")
async def detect(request: Request, image: UploadFile = File(...)) -> dict:
    ip = client_ip(request)
    try:
        check_rate_limit(f"detect:{ip}", DETECT_RATE)
    except BusyError as exc:
        raise _busy_http(exc) from exc

    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")

    try:
        with detect_slot():
            return detect_position(data, filename=safe_filename(image.filename))
    except BusyError as exc:
        raise _busy_http(exc) from exc
    except DetectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_exception("detect", exc)
        raise HTTPException(status_code=500, detail="Detection failed") from None


@app.post("/api/analyze")
def analyze(request: Request, body: AnalyzeRequest) -> dict:
    ip = client_ip(request)
    try:
        check_rate_limit(f"analyze:{ip}", ANALYZE_RATE)
        return analyze_position(
            fen=body.fen,
            turn=body.turn,
            depth=body.depth if body.movetime_ms is None else None,
            movetime_ms=body.movetime_ms,
        )
    except BusyError as exc:
        raise _busy_http(exc) from exc
    except EngineError as exc:
        raise HTTPException(status_code=422, detail=public_engine_error(exc)) from exc
    except Exception as exc:
        log_exception("analyze", exc)
        raise HTTPException(status_code=500, detail="Analysis failed") from None


@app.post("/api/analyze/stream")
def analyze_stream(request: Request, body: AnalyzeRequest) -> StreamingResponse:
    """NDJSON stream: Stockfish thinks 0→max_time_s, emits updates when suggestion changes."""
    ip = client_ip(request)
    try:
        check_rate_limit(f"analyze:{ip}", ANALYZE_RATE)
    except BusyError as exc:
        raise _busy_http(exc) from exc

    def generate():
        try:
            for update in iter_analyze_progressive(
                fen=body.fen,
                turn=body.turn,
                max_time_s=body.max_time_s,
            ):
                yield json.dumps(update, ensure_ascii=False) + "\n"
        except BusyError as exc:
            yield json.dumps({"error": str(exc), "done": True}, ensure_ascii=False) + "\n"
        except EngineError as exc:
            yield json.dumps(
                {"error": public_engine_error(exc), "done": True},
                ensure_ascii=False,
            ) + "\n"
        except Exception as exc:
            log_exception("analyze_stream", exc)
            yield json.dumps({"error": "Analysis failed", "done": True}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
