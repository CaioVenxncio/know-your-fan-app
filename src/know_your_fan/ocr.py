"""Synthetic specimen rendering and OCR text extraction.

The public demo never accepts uploaded images. It renders a clearly fictional
specimen card from a synthetic profile, optionally degrades it, and runs
Tesseract on the result.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import MutableMapping
from functools import cache
from importlib import resources
from io import BytesIO

import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from know_your_fan.config import DEFAULT_MAX_IMAGE_PIXELS, DEFAULT_OCR_TIMEOUT_SECONDS
from know_your_fan.models import FanProfile
from know_your_fan.observability import LOGGER_NAME

FONT_RESOURCE = "assets/fonts/Aileron-Regular.otf"
OCR_LANGUAGE = "por+eng"
OCR_TIMEOUT_SECONDS = DEFAULT_OCR_TIMEOUT_SECONDS
MAX_IMAGE_PIXELS = DEFAULT_MAX_IMAGE_PIXELS
MAX_IMAGE_SIDE = 8_000
SPECIMEN_SIZE = (900, 520)

OMP_THREAD_LIMIT_ENV = "OMP_THREAD_LIMIT"

_logger = logging.getLogger(f"{LOGGER_NAME}.ocr")


def limit_engine_threads(environ: MutableMapping[str, str] | None = None) -> str:
    """Limit each Tesseract process to one OpenMP thread unless the operator set a value.

    Tesseract's OpenMP build starts one thread per CPU core. With several
    concurrent OCR jobs this oversubscribes the CPU: in CI, two concurrent jobs
    took about 6.3 s each with default threading versus about 0.36 s with
    ``OMP_THREAD_LIMIT=1`` (sequential runs were unaffected); see
    docs/operations.md. pytesseract passes ``os.environ`` to the Tesseract
    subprocess, so this takes effect for every later OCR call. Call it at
    application start-up, not at import time. Returns the effective value.
    """
    env = os.environ if environ is None else environ
    value = env.setdefault(OMP_THREAD_LIMIT_ENV, "1")
    _logger.info("Tesseract OpenMP thread limit: %s", value)
    return value


class OCRUnavailableError(RuntimeError):
    """Tesseract or its language data is not installed."""


class OCRFailedError(RuntimeError):
    """Text extraction failed or timed out."""


class OCRTimeoutError(OCRFailedError):
    """Tesseract exceeded the configured timeout and was terminated."""


class InvalidImageError(ValueError):
    """The object is not a usable image: empty, too large, or an unsupported mode."""


@cache
def _font_bytes() -> bytes:
    return resources.files("know_your_fan").joinpath(FONT_RESOURCE).read_bytes()


def specimen_font(size: int) -> ImageFont.FreeTypeFont:
    """Return the bundled card font (Aileron Regular, CC0) at ``size`` points.

    Pillow's built-in default font lacks accented glyphs, so the card uses a
    bundled font to draw names such as "João" or "Gonçalves" correctly on
    every platform.
    """
    return ImageFont.truetype(BytesIO(_font_bytes()), size)


SPECIMEN_TITLE = "KNOW YOUR FAN - FAN CARD"
SPECIMEN_NOTICE = "SPECIMEN - FICTIONAL DATA - NOT AN IDENTITY DOCUMENT"
SPECIMEN_FOOTER = "Synthetic sample generated for demonstration only."


def specimen_fields(profile: FanProfile) -> list[str]:
    """The labelled field lines drawn on a card, in order (e.g. ``"Name: Ana Lima"``)."""
    return [
        f"Name: {profile.name}",
        f"Demo ID: {profile.demo_id}",
        f"City: {profile.city}",
        f"Favorite game: {profile.interests[0]}",
    ]


def specimen_lines(profile: FanProfile) -> list[str]:
    """Every text line drawn on the card, in reading order (the OCR ground truth)."""
    return [SPECIMEN_TITLE, SPECIMEN_NOTICE, *specimen_fields(profile), SPECIMEN_FOOTER]


def render_specimen(profile: FanProfile) -> Image.Image:
    """Draw a fictional, watermarked fan card for ``profile``.

    The layout is intentionally generic and does not imitate any official
    identity document. The text drawn is exactly :func:`specimen_lines`.
    """
    image = Image.new("RGB", SPECIMEN_SIZE, "white")
    draw = ImageDraw.Draw(image)
    title_font = specimen_font(40)
    body_font = specimen_font(30)
    small_font = specimen_font(22)

    draw.rectangle(
        [(10, 10), (SPECIMEN_SIZE[0] - 10, SPECIMEN_SIZE[1] - 10)], outline="black", width=4
    )
    draw.text((40, 35), SPECIMEN_TITLE, fill="black", font=title_font)
    draw.text((40, 90), SPECIMEN_NOTICE, fill="dimgray", font=small_font)
    y = 160
    for line in specimen_fields(profile):
        draw.text((40, y), line, fill="black", font=body_font)
        y += 70
    draw.text((40, SPECIMEN_SIZE[1] - 60), SPECIMEN_FOOTER, fill="dimgray", font=small_font)
    return image


MAX_BLUR_RADIUS = 3.0
MAX_ROTATION_DEGREES = 10.0


def degrade(
    image: Image.Image, blur_radius: float = 0.0, rotation_degrees: float = 0.0
) -> Image.Image:
    """Apply simple capture-like degradations for demonstration.

    Parameters are bounded so a caller cannot request arbitrarily expensive work.
    """
    if not (math.isfinite(blur_radius) and 0 <= blur_radius <= MAX_BLUR_RADIUS):
        raise ValueError(f"blur_radius must be between 0 and {MAX_BLUR_RADIUS}.")
    if not (math.isfinite(rotation_degrees) and abs(rotation_degrees) <= MAX_ROTATION_DEGREES):
        raise ValueError(f"rotation_degrees must be within ±{MAX_ROTATION_DEGREES}.")
    result = image
    if rotation_degrees:
        result = result.rotate(rotation_degrees, expand=True, fillcolor="white")
    if blur_radius > 0:
        result = result.filter(ImageFilter.GaussianBlur(blur_radius))
    return result


def check_image(image: object, max_pixels: int = MAX_IMAGE_PIXELS) -> Image.Image:
    """Validate that ``image`` is a non-empty PIL image within the size limits.

    This only inspects metadata, so it is cheap enough to run before any
    rate-limit token or OCR slot is spent.
    """
    if not isinstance(image, Image.Image):
        raise InvalidImageError("Not an image.")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise InvalidImageError("Image is empty.")
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE or width * height > max_pixels:
        raise InvalidImageError("Image is too large for the demo OCR pipeline.")
    return image


def preprocess(image: Image.Image, max_pixels: int = MAX_IMAGE_PIXELS) -> Image.Image:
    """Prepare an image for OCR: size guard, orientation, grayscale, contrast."""
    image = check_image(image, max_pixels)
    try:
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        return ImageOps.autocontrast(image)
    except (ValueError, OSError) as exc:
        raise InvalidImageError("Unsupported image format.") from exc


def extract_text(
    image: Image.Image,
    *,
    timeout_seconds: float = OCR_TIMEOUT_SECONDS,
    max_pixels: int = MAX_IMAGE_PIXELS,
) -> str:
    """Preprocess ``image`` (:func:`preprocess`) and run Tesseract on it.

    On timeout pytesseract terminates the Tesseract subprocess and removes its
    temporary files before raising; this function maps that to
    :class:`OCRTimeoutError`. Logs record event types only, never image
    contents, extracted text, or engine messages.
    """
    return recognize(
        preprocess(image, max_pixels), timeout_seconds=timeout_seconds, max_pixels=max_pixels
    )


def recognize(
    prepared: Image.Image,
    *,
    timeout_seconds: float = OCR_TIMEOUT_SECONDS,
    max_pixels: int = MAX_IMAGE_PIXELS,
) -> str:
    """Run Tesseract on an already-prepared image, with the app's engine settings.

    This is the single place where the engine is invoked (language, timeout,
    error mapping). :func:`extract_text` uses it after the app's default
    preprocessing; the research harness uses it after alternative
    preprocessing, so both share identical engine behaviour.
    """
    check_image(prepared, max_pixels)
    try:
        text = pytesseract.image_to_string(prepared, lang=OCR_LANGUAGE, timeout=timeout_seconds)
    except pytesseract.TesseractNotFoundError as exc:
        _logger.error("Tesseract binary not found")
        raise OCRUnavailableError("Tesseract OCR is not installed or not on PATH.") from exc
    except pytesseract.TesseractError as exc:
        if "Failed loading language" in str(exc):
            _logger.error("Tesseract language data missing")
            raise OCRUnavailableError(
                "Tesseract language data (por/eng) is not installed."
            ) from exc
        _logger.warning("Tesseract failed (exit status %s)", exc.status)
        raise OCRFailedError("Tesseract could not process the image.") from exc
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            _logger.warning("Tesseract timed out after %.1f s and was terminated", timeout_seconds)
            raise OCRTimeoutError("OCR timed out.") from exc
        _logger.error("Unexpected OCR engine error (%s)", type(exc).__name__)
        raise OCRFailedError("OCR failed unexpectedly.") from exc
    return str(text)
