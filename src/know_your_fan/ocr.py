"""Synthetic specimen rendering and OCR text extraction.

The public demo never accepts uploaded images. It renders a clearly fictional
specimen card from a synthetic profile, optionally degrades it, and runs
Tesseract on the result.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from io import BytesIO

import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from know_your_fan.models import FanProfile

FONT_RESOURCE = "assets/fonts/Aileron-Regular.otf"
OCR_LANGUAGE = "por+eng"
OCR_TIMEOUT_SECONDS = 15
MAX_IMAGE_PIXELS = 4_000_000
SPECIMEN_SIZE = (900, 520)


class OCRUnavailableError(RuntimeError):
    """Tesseract or its language data is not installed."""


class OCRFailedError(RuntimeError):
    """Text extraction failed or timed out."""


class InvalidImageError(ValueError):
    """The image is empty or too large for the demo OCR pipeline."""


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


def render_specimen(profile: FanProfile) -> Image.Image:
    """Draw a fictional, watermarked fan card for ``profile``.

    The layout is intentionally generic and does not imitate any official
    identity document.
    """
    image = Image.new("RGB", SPECIMEN_SIZE, "white")
    draw = ImageDraw.Draw(image)
    title_font = specimen_font(40)
    body_font = specimen_font(30)
    small_font = specimen_font(22)

    draw.rectangle(
        [(10, 10), (SPECIMEN_SIZE[0] - 10, SPECIMEN_SIZE[1] - 10)], outline="black", width=4
    )
    draw.text((40, 35), "KNOW YOUR FAN - FAN CARD", fill="black", font=title_font)
    draw.text(
        (40, 90),
        "SPECIMEN - FICTIONAL DATA - NOT AN IDENTITY DOCUMENT",
        fill="dimgray",
        font=small_font,
    )
    lines = [
        ("Name", profile.name),
        ("Demo ID", profile.demo_id),
        ("City", profile.city),
        ("Favorite game", profile.interests[0]),
    ]
    y = 160
    for label, value in lines:
        draw.text((40, y), f"{label}: {value}", fill="black", font=body_font)
        y += 70
    draw.text(
        (40, SPECIMEN_SIZE[1] - 60),
        "Synthetic sample generated for demonstration only.",
        fill="dimgray",
        font=small_font,
    )
    return image


MAX_BLUR_RADIUS = 3.0
MAX_ROTATION_DEGREES = 10.0


def degrade(
    image: Image.Image, blur_radius: float = 0.0, rotation_degrees: float = 0.0
) -> Image.Image:
    """Apply simple capture-like degradations for demonstration.

    Parameters are bounded so a caller cannot request arbitrarily expensive work.
    """
    if not 0 <= blur_radius <= MAX_BLUR_RADIUS:
        raise ValueError(f"blur_radius must be between 0 and {MAX_BLUR_RADIUS}.")
    if abs(rotation_degrees) > MAX_ROTATION_DEGREES:
        raise ValueError(f"rotation_degrees must be within ±{MAX_ROTATION_DEGREES}.")
    result = image
    if rotation_degrees:
        result = result.rotate(rotation_degrees, expand=True, fillcolor="white")
    if blur_radius > 0:
        result = result.filter(ImageFilter.GaussianBlur(blur_radius))
    return result


def preprocess(image: Image.Image) -> Image.Image:
    """Prepare an image for OCR: orientation, size guard, grayscale, contrast."""
    width, height = image.size
    if width == 0 or height == 0:
        raise InvalidImageError("Image is empty.")
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidImageError("Image is too large for the demo OCR pipeline.")
    image = ImageOps.exif_transpose(image)
    image = ImageOps.grayscale(image)
    return ImageOps.autocontrast(image)


def extract_text(image: Image.Image) -> str:
    """Run Tesseract on ``image`` and return the extracted text."""
    prepared = preprocess(image)
    try:
        text = pytesseract.image_to_string(prepared, lang=OCR_LANGUAGE, timeout=OCR_TIMEOUT_SECONDS)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError("Tesseract OCR is not installed or not on PATH.") from exc
    except pytesseract.TesseractError as exc:
        if "Failed loading language" in str(exc):
            raise OCRUnavailableError(
                "Tesseract language data (por/eng) is not installed."
            ) from exc
        raise OCRFailedError("Tesseract could not process the image.") from exc
    except RuntimeError as exc:  # pytesseract raises RuntimeError on timeout
        raise OCRFailedError("OCR timed out.") from exc
    return str(text)
