"""OCR module tests that do not need Tesseract (the engine is replaced where noted).

The real engine is exercised in tests/integration/test_ocr_e2e.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import NoReturn

import pytesseract
import pytest
from PIL import Image, ImageChops

from know_your_fan import ocr
from know_your_fan.models import FanProfile
from know_your_fan.synthetic import (
    _ID_ALPHABET,
    FICTIONAL_CITIES,
    GAMES,
    GIVEN_NAMES,
    SURNAMES,
)


def test_specimen_has_fixed_size_and_is_not_blank(profile: FanProfile) -> None:
    image = ocr.render_specimen(profile)
    assert image.size == ocr.SPECIMEN_SIZE
    assert image.convert("L").getextrema() == (0, 255)


def test_specimen_rendering_is_deterministic(profile: FanProfile) -> None:
    first, second = ocr.render_specimen(profile), ocr.render_specimen(profile)
    assert ImageChops.difference(first, second).getbbox() is None


def test_degrade_without_parameters_returns_identical_image(profile: FanProfile) -> None:
    image = ocr.render_specimen(profile)
    assert ocr.degrade(image) is image


def test_rotation_expands_canvas_and_blur_changes_pixels(profile: FanProfile) -> None:
    image = ocr.render_specimen(profile)
    rotated = ocr.degrade(image, rotation_degrees=5)
    assert rotated.size[0] > image.size[0]
    blurred = ocr.degrade(image, blur_radius=1.5)
    assert blurred.size == image.size
    assert ImageChops.difference(image, blurred).getbbox() is not None


@pytest.mark.parametrize(
    ("blur", "rotation"),
    [(-0.1, 0), (ocr.MAX_BLUR_RADIUS + 0.1, 0), (0, ocr.MAX_ROTATION_DEGREES + 1), (0, -45)],
)
def test_degrade_rejects_out_of_range_parameters(
    profile: FanProfile, blur: float, rotation: float
) -> None:
    with pytest.raises(ValueError, match="must be"):
        ocr.degrade(ocr.render_specimen(profile), blur_radius=blur, rotation_degrees=rotation)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P", "L", "CMYK"])
def test_preprocess_returns_grayscale_for_common_modes(mode: str) -> None:
    image = Image.new("RGB", (40, 20), "white").convert(mode)
    assert ocr.preprocess(image).mode == "L"


def test_preprocess_stretches_contrast() -> None:
    image = Image.new("L", (10, 10), 100)
    image.putpixel((0, 0), 150)
    assert ocr.preprocess(image).getextrema() == (0, 255)


def test_preprocess_applies_exif_orientation() -> None:
    image = Image.new("RGB", (60, 20), "white")
    image.getexif()[0x0112] = 6  # EXIF orientation: rotated 90 degrees
    assert ocr.preprocess(image).size == (20, 60)


@pytest.mark.parametrize("size", [(0, 0), (0, 10), (10, 0)])
def test_preprocess_rejects_empty_images(size: tuple[int, int]) -> None:
    with pytest.raises(ocr.InvalidImageError, match="empty"):
        ocr.preprocess(Image.new("RGB", size))


def test_preprocess_rejects_oversized_images() -> None:
    with pytest.raises(ocr.InvalidImageError, match="too large"):
        ocr.preprocess(Image.new("L", (2001, 2000)))


def test_invalid_image_error_is_raised_before_tesseract_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: calls.append(a))
    with pytest.raises(ocr.InvalidImageError):
        ocr.extract_text(Image.new("RGB", (0, 0)))
    assert calls == []


def test_extract_text_passes_language_and_timeout(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    seen: dict[str, object] = {}

    def fake(image: Image.Image, **kwargs: object) -> str:
        seen.update(kwargs, mode=image.mode)
        return "text"

    monkeypatch.setattr(pytesseract, "image_to_string", fake)
    assert ocr.extract_text(ocr.render_specimen(profile)) == "text"
    assert seen == {"lang": ocr.OCR_LANGUAGE, "timeout": ocr.OCR_TIMEOUT_SECONDS, "mode": "L"}


def _raiser(exc: BaseException) -> Callable[..., NoReturn]:
    def boom(*args: object, **kwargs: object) -> NoReturn:
        raise exc

    return boom


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (pytesseract.TesseractNotFoundError(), ocr.OCRUnavailableError),
        (pytesseract.TesseractError(1, "Failed loading language 'por'"), ocr.OCRUnavailableError),
        (pytesseract.TesseractError(1, "Image too small to scale"), ocr.OCRFailedError),
        (RuntimeError("Tesseract process timeout"), ocr.OCRFailedError),
    ],
)
def test_engine_failures_map_to_friendly_errors(
    monkeypatch: pytest.MonkeyPatch,
    profile: FanProfile,
    raised: BaseException,
    expected: type[Exception],
) -> None:
    monkeypatch.setattr(pytesseract, "image_to_string", _raiser(raised))
    with pytest.raises(expected):
        ocr.extract_text(ocr.render_specimen(profile))


def test_card_font_has_a_real_glyph_for_every_character_used() -> None:
    """Regression: Pillow's default font drew accented letters as placeholder glyphs."""
    font = ocr.specimen_font(30)
    placeholder = bytes(font.getmask(""))  # private-use code point: never in the font
    vocabulary = (*GIVEN_NAMES, *SURNAMES, *FICTIONAL_CITIES, *GAMES)
    labels = "KNOW YOUR FAN - FAN CARD SPECIMEN FICTIONAL DATA Name Demo ID City Favorite game:"
    characters = {c for c in "".join(vocabulary) + labels + _ID_ALPHABET if not c.isspace()}
    missing = sorted(c for c in characters if bytes(font.getmask(c)) == placeholder)
    assert missing == []


def test_card_font_is_loaded_from_package_resources() -> None:
    assert ocr.specimen_font(12).getname() == ("Aileron", "Regular")


# ------------------------------------------------------------------ Phase 3: image safety


@pytest.mark.parametrize("not_an_image", [None, b"\x89PNG", "card.png", object()])
def test_non_image_objects_are_rejected(not_an_image: object) -> None:
    with pytest.raises(ocr.InvalidImageError, match="Not an image"):
        ocr.check_image(not_an_image)


@pytest.mark.parametrize("size", [(ocr.MAX_IMAGE_SIDE + 1, 10), (10, ocr.MAX_IMAGE_SIDE + 1)])
def test_extreme_aspect_ratios_are_rejected_even_under_the_pixel_cap(
    size: tuple[int, int],
) -> None:
    image = Image.new("L", size)
    assert size[0] * size[1] < ocr.MAX_IMAGE_PIXELS
    with pytest.raises(ocr.InvalidImageError, match="too large"):
        ocr.check_image(image)


def test_configured_pixel_limit_is_respected() -> None:
    image = Image.new("L", (1200, 1000))
    ocr.check_image(image)  # 1.2 MP is under the default 4 MP cap
    with pytest.raises(ocr.InvalidImageError):
        ocr.check_image(image, max_pixels=1_000_000)


@pytest.mark.parametrize("mode", ["La", "LAB"])  # modes Pillow cannot convert to grayscale
def test_unsupported_modes_become_invalid_image_errors(mode: str) -> None:
    with pytest.raises(ocr.InvalidImageError, match="Unsupported"):
        ocr.preprocess(Image.new(mode, (8, 4)))


@pytest.mark.parametrize("mode", ["1", "I", "I;16", "F", "PA", "YCbCr", "HSV"])
def test_less_common_modes_are_converted(mode: str) -> None:
    assert ocr.preprocess(Image.new(mode, (8, 4))).mode == "L"


@pytest.mark.parametrize(
    ("blur", "rotation"), [(float("nan"), 0), (0, float("nan")), (float("inf"), 0)]
)
def test_degrade_rejects_non_finite_parameters(
    profile: FanProfile, blur: float, rotation: float
) -> None:
    with pytest.raises(ValueError, match="must be"):
        ocr.degrade(ocr.render_specimen(profile), blur_radius=blur, rotation_degrees=rotation)


def test_timeout_has_its_own_error_type(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    monkeypatch.setattr(
        pytesseract, "image_to_string", _raiser(RuntimeError("Tesseract process timeout"))
    )
    with pytest.raises(ocr.OCRTimeoutError):
        ocr.extract_text(ocr.render_specimen(profile), timeout_seconds=1)


def test_unexpected_runtime_error_is_not_reported_as_timeout(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    monkeypatch.setattr(pytesseract, "image_to_string", _raiser(RuntimeError("other problem")))
    with pytest.raises(ocr.OCRFailedError) as excinfo:
        ocr.extract_text(ocr.render_specimen(profile))
    assert not isinstance(excinfo.value, ocr.OCRTimeoutError)


def test_configured_timeout_is_passed_to_tesseract(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    seen: dict[str, object] = {}

    def fake(image: Image.Image, **kwargs: object) -> str:
        seen.update(kwargs)
        return ""

    monkeypatch.setattr(pytesseract, "image_to_string", fake)
    ocr.extract_text(ocr.render_specimen(profile), timeout_seconds=3.5)
    assert seen["timeout"] == 3.5


@pytest.mark.parametrize(
    "raised",
    [
        pytesseract.TesseractNotFoundError(),
        pytesseract.TesseractError(1, "Failed loading language 'por' /tmp/tess_SECRET"),
        pytesseract.TesseractError(2, "Error in /tmp/tess_SECRET with Name: Ana SECRET"),
        RuntimeError("Tesseract process timeout"),
        RuntimeError("weird failure mentioning SECRET"),
    ],
)
def test_ocr_failure_logs_contain_no_engine_messages_or_paths(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    profile: FanProfile,
    raised: BaseException,
) -> None:
    monkeypatch.setattr(pytesseract, "image_to_string", _raiser(raised))
    with (
        caplog.at_level(logging.DEBUG, logger="know_your_fan"),
        pytest.raises((ocr.OCRUnavailableError, ocr.OCRFailedError)),
    ):
        ocr.extract_text(ocr.render_specimen(profile))
    assert caplog.records, "a technical event should be logged"
    logged = caplog.text
    assert "SECRET" not in logged
    assert "tess_" not in logged  # pytesseract temporary-file prefix
    assert profile.name not in logged
