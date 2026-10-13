import shutil

import pytest
import pytesseract
from PIL import Image

from know_your_fan import ocr
from know_your_fan.synthetic import generate_profiles
from know_your_fan.text_matching import match_name

PROFILE = generate_profiles(1, seed=21)[0]
tesseract_missing = shutil.which("tesseract") is None


def test_specimen_is_rendered_and_labelled():
    image = ocr.render_specimen(PROFILE)
    assert image.size == ocr.SPECIMEN_SIZE


def test_degrade_rotation_expands_canvas():
    image = ocr.render_specimen(PROFILE)
    rotated = ocr.degrade(image, blur_radius=1.0, rotation_degrees=5)
    assert rotated.size[0] > image.size[0]


def test_preprocess_rejects_oversized_images():
    with pytest.raises(ValueError):
        ocr.preprocess(Image.new("RGB", (3000, 3000)))


def test_preprocess_returns_grayscale():
    assert ocr.preprocess(ocr.render_specimen(PROFILE)).mode == "L"


def test_missing_tesseract_raises_friendly_error(monkeypatch):
    def boom(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(ocr.OCRUnavailableError):
        ocr.extract_text(ocr.render_specimen(PROFILE))


def test_missing_language_data_raises_friendly_error(monkeypatch):
    def boom(*args, **kwargs):
        raise pytesseract.TesseractError(1, "Failed loading language 'por'")

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(ocr.OCRUnavailableError):
        ocr.extract_text(ocr.render_specimen(PROFILE))


def test_timeout_raises_friendly_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    with pytest.raises(ocr.OCRFailedError):
        ocr.extract_text(ocr.render_specimen(PROFILE))


@pytest.mark.skipif(tesseract_missing, reason="Tesseract OCR is not installed")
def test_end_to_end_ocr_finds_name_on_clean_specimen():
    text = ocr.extract_text(ocr.render_specimen(PROFILE))
    assert match_name(PROFILE.name, text).all_found
