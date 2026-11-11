"""Chessboard image → FEN detection via chessvision."""

from __future__ import annotations

import base64
import io
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image
from chessvision import BoardDetector, BoardPredictor, Orientation, Turn
from chessvision.detector import DetectedBoard


class DetectionError(Exception):
    """Raised when a board cannot be recognized from an image."""


@lru_cache(maxsize=1)
def get_predictor() -> BoardPredictor:
    return BoardPredictor()


@lru_cache(maxsize=1)
def get_board_detector() -> BoardDetector:
    return BoardDetector()


def _image_to_data_url(image: Image.Image, max_side: int = 720) -> str:
    img = image.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _pick_best_board(boards: list[DetectedBoard]) -> DetectedBoard:
    # Prefer largest near-square crop with highest detector score.
    def key(board: DetectedBoard) -> tuple[float, float]:
        x, y, w, h = board.box
        area = float(w * h)
        aspect = min(w, h) / max(w, h)
        return (area * aspect, float(board.score))

    return max(boards, key=key)


def _infer_turn_from_highlights(
    board_image: Image.Image,
    piece_placement: str,
) -> str | None:
    """Infer side to move from Chess.com-style last-move yellow highlights.

    If the destination square of the last move holds a white piece → black to move,
    and vice versa.
    """
    arr = np.asarray(board_image.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    if h < 64 or w < 64:
        return None

    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    # Chess.com last-move markers are bright yellow / yellow-green.
    mask = (r > 175) & (g > 175) & (b < 150) & (((r + g) / 2.0) - b > 55)
    if int(mask.sum()) < 200:
        return None

    sq_h, sq_w = h // 8, w // 8
    scores: list[tuple[int, str]] = []
    for rank in range(8):
        for file in range(8):
            tile = mask[rank * sq_h : (rank + 1) * sq_h, file * sq_w : (file + 1) * sq_w]
            count = int(tile.sum())
            if count > 80:
                square = f"{chr(97 + file)}{8 - rank}"
                scores.append((count, square))

    if len(scores) < 1:
        return None

    scores.sort(reverse=True)
    top_squares = [sq for _, sq in scores[:2]]

    # Map piece placement to square -> piece char.
    ranks = piece_placement.split("/")
    if len(ranks) != 8:
        return None

    grid: dict[str, str] = {}
    for rank_idx, rank in enumerate(ranks):
        file_idx = 0
        for ch in rank:
            if ch.isdigit():
                file_idx += int(ch)
                continue
            grid[f"{chr(97 + file_idx)}{8 - rank_idx}"] = ch
            file_idx += 1

    # Destination square = highlighted square that still has a piece.
    occupied = [sq for sq in top_squares if sq in grid]
    if not occupied:
        return None

    dest = occupied[0]
    piece = grid[dest]
    if piece.isupper():
        return "black"  # white just moved
    if piece.islower():
        return "white"  # black just moved
    return None


def _apply_turn(fen: str, turn: str) -> str:
    parts = fen.split()
    if not parts:
        return fen
    side = "w" if turn == "white" else "b"
    if len(parts) == 1:
        return f"{parts[0]} {side} - - 0 1"
    parts[1] = side
    while len(parts) < 6:
        parts.append(["-", "-", "0", "1"][len(parts) - 2])
    return " ".join(parts)


def detect_position(image_bytes: bytes, filename: str = "board.png") -> dict[str, Any]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise DetectionError(f"Cannot read image: {exc}") from exc

    predictor = get_predictor()
    board_detector = get_board_detector()

    crop_box: tuple[int, int, int, int] | None = None
    used_crop = False
    board_image = image

    try:
        boards = board_detector.detect(image)
    except Exception:
        boards = []

    prediction = None
    if boards:
        best = _pick_best_board(boards)
        crop_box = tuple(int(v) for v in best.box)  # type: ignore[assignment]
        board_image = best.image
        used_crop = True
        try:
            prediction = predictor.predict(
                best,
                orientation=Orientation.AUTO,
                turn=Turn.AUTO,
                castling="auto",
            )
        except Exception:
            prediction = None

    # Fallback: classify the full screenshot (diagrams / already-cropped boards).
    if prediction is None:
        try:
            prediction = predictor.predict(
                image,
                orientation=Orientation.AUTO,
                turn=Turn.AUTO,
                castling="auto",
            )
            board_image = image
            used_crop = False
        except Exception as exc:  # noqa: BLE001
            raise DetectionError(
                "Could not detect a chessboard. Try cropping to only the board, "
                "or use a clearer Chess.com / Lichess screenshot."
            ) from exc

    fen = prediction.fen
    parts = fen.split()
    piece_placement = parts[0] if parts else fen

    turn_guess = "white"
    turn_source = "model"
    if len(parts) >= 2 and parts[1] in {"w", "b"}:
        turn_guess = "white" if parts[1] == "w" else "black"

    inferred = _infer_turn_from_highlights(board_image, piece_placement)
    if inferred:
        turn_guess = inferred
        turn_source = "last_move_highlight"
        fen = _apply_turn(fen, turn_guess)

    orientation = "white" if prediction.orientation is Orientation.WHITE else "black"

    return {
        "fen": fen,
        "piece_placement": piece_placement,
        "turn_guess": turn_guess,
        "turn_source": turn_source,
        "confidence": float(prediction.confidence),
        "orientation": orientation,
        "is_valid": bool(prediction.is_valid),
        "validation_errors": list(prediction.validation_errors),
        "filename": filename,
        "used_crop": used_crop,
        "crop_box": list(crop_box) if crop_box else None,
        "board_preview": _image_to_data_url(board_image),
    }
