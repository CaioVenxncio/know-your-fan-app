"""End-to-end OCR tests against the real Tesseract engine (nothing is mocked).

Locally these tests are skipped when Tesseract is not installed. In CI the
environment variable ``KYF_REQUIRE_OCR=1`` is set, and a missing engine or
missing language data makes the tests fail instead of skipping silently.
"""

from __future__ import annotations

import os
import shutil

import pytesseract
import pytest

from know_your_fan import ocr, services
from know_your_fan.models import FanProfile
from know_your_fan.synthetic import generate_profiles
from know_your_fan.text_matching import match_name

REQUIRED = os.environ.get("KYF_REQUIRE_OCR") == "1"
AVAILABLE = shutil.which("tesseract") is not None

if not AVAILABLE:
    if REQUIRED:
        pytest.fail("KYF_REQUIRE_OCR=1 but Tesseract is not on PATH", pytrace=False)
    pytest.skip("Tesseract OCR is not installed", allow_module_level=True)

pytestmark = pytest.mark.ocr

# Seeds chosen to include accented given names and surnames.
PROFILES = generate_profiles(6, seed=2025)


def test_engine_version_and_language_data() -> None:
    assert pytesseract.get_tesseract_version().major >= 5
    languages = set(pytesseract.get_languages(config=""))
    assert {"por", "eng"} <= languages, languages


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.demo_id)
def test_clean_specimen_name_is_recognized(profile: FanProfile) -> None:
    text = ocr.extract_text(ocr.render_specimen(profile))
    result = match_name(profile.name, text)
    assert result.all_found, (profile.name, text)


def test_name_absent_from_card_is_not_found() -> None:
    text = ocr.extract_text(ocr.render_specimen(PROFILES[0]))
    assert not match_name("Zeferino Quixadá", text).found_tokens


def test_service_pipeline_with_real_engine() -> None:
    profile = PROFILES[0]
    image = services.render_card(profile, blur_radius=0, rotation_degrees=0)
    outcome = services.run_text_matching(image, profile.name)
    assert outcome.match.all_found
    assert "SPECIMEN" in outcome.extracted_text.upper()
