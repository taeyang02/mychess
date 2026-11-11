"""Validate uploaded images by magic bytes and decode limits."""

from __future__ import annotations

import io

from PIL import Image, ImageFile

from settings import MAX_IMAGE_PIXELS, MAX_IMAGE_SIDE, MAX_UPLOAD_BYTES

# Refuse truncated / streaming bombs.
ImageFile.LOAD_TRUNCATED_IMAGES = False
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "webp"),  # need WEBP at offset 8
]


class UploadError(Exception):
    """Invalid or unsafe upload."""


def _sniff_image(data: bytes) -> str:
    if len(data) < 12:
        raise UploadError("File too small to be an image")
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    raise UploadError("Unsupported or invalid image format (use JPEG/PNG/GIF/WEBP)")


def validate_and_load_image(data: bytes) -> Image.Image:
    if not data:
        raise UploadError("Empty image upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"Image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")

    _sniff_image(data)

    try:
        with Image.open(io.BytesIO(data)) as image:
            w, h = image.size
            if w < 32 or h < 32:
                raise UploadError("Image too small")
            if w > MAX_IMAGE_SIDE or h > MAX_IMAGE_SIDE:
                raise UploadError(f"Image too large (max {MAX_IMAGE_SIDE}px per side)")
            if w * h > MAX_IMAGE_PIXELS:
                raise UploadError("Image has too many pixels")

            image.load()
            return image.convert("RGB")
    except UploadError:
        raise
    except Image.DecompressionBombError as exc:
        raise UploadError("Image dimensions too large") from exc
    except (OSError, ValueError) as exc:
        raise UploadError("Cannot decode image") from exc


def safe_filename(name: str | None) -> str:
    base = (name or "board.png").split("/")[-1].split("\\")[-1]
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._-")[:80]
    return cleaned or "board.png"
