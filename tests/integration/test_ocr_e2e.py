"""End-to-end OCR tests against the real Tesseract engine (nothing is mocked).

Locally these tests are skipped when Tesseract is not installed. In CI the
environment variable ``KYF_REQUIRE_OCR=1`` is set, and a missing engine or
missing language data makes the tests fail instead of skipping silently.
"""

from __future__ import annotations

import dataclasses
import os
import shutil

import pytesseract
import pytest

from know_your_fan import ocr, services
from know_your_fan.models import FanProfile
from know_your_fan.synthetic import GIVEN_NAMES, SURNAMES, generate_profiles, synthetic_violations
from know_your_fan.text_matching import match_name

REQUIRED = os.environ.get("KYF_REQUIRE_OCR") == "1"
AVAILABLE = shutil.which("tesseract") is not None

if not AVAILABLE:
    if REQUIRED:
        pytest.fail("KYF_REQUIRE_OCR=1 but Tesseract is not on PATH", pytrace=False)
    pytest.skip("Tesseract OCR is not installed", allow_module_level=True)

pytestmark = pytest.mark.ocr

PROFILES = generate_profiles(6, seed=2025)

# Valid vocabulary combinations that together use every accented given name and surname
# (á, é, ã, õ, ç). These regressed when cards were drawn with a font lacking those glyphs.
ACCENTED_NAMES = (
    "João Conceição Gonçalves",
    "Fábio Falcão Simões",
    "Natália Simões Conceição",
    "Otávio Gonçalves Falcão",
    "Valéria Falcão Simões",
)
ACCENTED_PROFILES = [dataclasses.replace(PROFILES[0], name=name) for name in ACCENTED_NAMES]


def test_accented_profiles_are_valid_synthetic_data() -> None:
    accented_words = {w for w in (*GIVEN_NAMES, *SURNAMES) if not w.isascii()}
    used = {w for name in ACCENTED_NAMES for w in name.split()}
    assert accented_words <= used
    assert all(synthetic_violations(p) == [] for p in ACCENTED_PROFILES)


def test_engine_version_and_language_data() -> None:
    assert pytesseract.get_tesseract_version().major >= 5
    languages = set(pytesseract.get_languages(config=""))
    assert {"por", "eng"} <= languages, languages


@pytest.mark.parametrize("profile", PROFILES + ACCENTED_PROFILES, ids=lambda p: p.name)
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
