"""REST API v1 — offline research only (no live-move advice)."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.schemas.analysis import (
    AnalysisJobResponse,
    AnalysisReport,
    AnalysisRequest,
    BatchAnalysisRequest,
    ImportGameRequest,
    ImportGameResponse,
    MoveFeature,
    PlayerBaselineResponse,
)
from app.services.pipeline import player_baseline_payload, run_analysis
from app.services.pgn_parser import parse_pgn_text
from app.store.memory import store

logger = logging.getLogger("lab.api")
router = APIRouter(prefix="/api/v1")

LICHESS_API = "https://lichess.org/game/export"


def _fetch_lichess_pgn(url: str) -> str:
    # Accept https://lichess.org/xxxxxx or /game/export/xxxxxx
    game_id = url.rstrip("/").split("/")[-1].split("#")[0]
    if not game_id or len(game_id) < 6:
        raise HTTPException(400, "Invalid Lichess URL")
    export_url = f"{LICHESS_API}/{game_id}?clocks=true&evals=false"
    try:
        resp = httpx.get(export_url, timeout=20.0, headers={"Accept": "application/x-chess-pgn"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Lichess fetch failed: {exc}") from exc
    return resp.text


@router.post("/games/import", response_model=ImportGameResponse)
async def import_game(body: ImportGameRequest) -> ImportGameResponse:
    warnings: list[str] = []
    platform = body.platform
    source = "pgn_text"

    if body.source_url:
        url = body.source_url.strip()
        if "lichess.org" in url:
            pgn_text = _fetch_lichess_pgn(url)
            platform = "lichess"
            source = url
        elif "chess.com" in url:
            raise HTTPException(
                400,
                "Chess.com URL import requires an official API token/flow — not enabled in MVP. "
                "Paste PGN text instead.",
            )
        else:
            raise HTTPException(400, "Unsupported URL host. Use Lichess URL or PGN text.")
    elif body.pgn_text:
        pgn_text = body.pgn_text
    else:
        raise HTTPException(400, "Provide pgn_text or source_url")

    try:
        parsed = parse_pgn_text(pgn_text, platform=platform, max_plies=settings.max_plies)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    warnings.extend(parsed.warnings)
    rec = store.import_game(parsed, platform=platform, label=body.label, source=source)
    return ImportGameResponse(
        game_id=rec.game_id,
        status="imported",
        warnings=warnings,
        metadata=parsed.metadata,
    )


@router.post("/games/import-file", response_model=ImportGameResponse)
async def import_game_file(file: UploadFile = File(...)) -> ImportGameResponse:
    raw = await file.read()
    if len(raw) > 500_000:
        raise HTTPException(400, "PGN file too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "PGN must be UTF-8") from exc
    return await import_game(ImportGameRequest(pgn_text=text, platform="offline"))


@router.post("/analysis", response_model=AnalysisJobResponse)
async def start_analysis(body: AnalysisRequest) -> AnalysisJobResponse:
    game = store.get_game(body.game_id)
    if not game:
        raise HTTPException(404, "game_id not found")

    rec = store.create_analysis(
        body.game_id,
        {"multipv": body.multipv, "depth": body.depth, "side": body.side, "note": body.note},
    )
    try:
        run_analysis(
            store,
            rec.analysis_id,
            game.parsed,
            multipv=body.multipv,
            depth=body.depth,
            side=body.side,
            platform=game.platform,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        logger.exception("analysis failed")
        raise HTTPException(500, f"Analysis failed: {exc}") from exc

    return AnalysisJobResponse(
        analysis_id=rec.analysis_id,
        game_id=body.game_id,
        status="completed",
        message="Offline analysis completed",
    )


@router.post("/batch-analysis")
async def batch_analysis(body: BatchAnalysisRequest) -> dict:
    results = []
    for gid in body.game_ids[: settings.max_games_batch]:
        try:
            job = await start_analysis(
                AnalysisRequest(game_id=gid, multipv=body.multipv, depth=body.depth)
            )
            results.append(job.model_dump())
        except HTTPException as exc:
            results.append({"game_id": gid, "status": "failed", "error": exc.detail})
    return {"results": results, "count": len(results)}


@router.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str) -> dict:
    rec = store.get_analysis(analysis_id)
    if not rec:
        raise HTTPException(404, "analysis not found")
    return {
        "analysis_id": rec.analysis_id,
        "game_id": rec.game_id,
        "status": rec.status,
        "config": rec.config,
        "error": rec.error,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "move_count": len(rec.moves),
    }


@router.get("/analysis/{analysis_id}/moves", response_model=list[MoveFeature])
async def get_moves(analysis_id: str) -> list[MoveFeature]:
    rec = store.get_analysis(analysis_id)
    if not rec:
        raise HTTPException(404, "analysis not found")
    return rec.moves


@router.get("/analysis/{analysis_id}/report", response_model=AnalysisReport)
async def get_report(analysis_id: str) -> AnalysisReport:
    rec = store.get_analysis(analysis_id)
    if not rec or not rec.report:
        raise HTTPException(404, "report not found")
    return rec.report


@router.get("/players/{player_id}/baseline", response_model=PlayerBaselineResponse)
async def get_baseline(player_id: str) -> PlayerBaselineResponse:
    payload = player_baseline_payload(store, player_id)
    return PlayerBaselineResponse(**payload)
