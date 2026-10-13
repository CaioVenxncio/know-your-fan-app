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
CARD_PROFILES = PROFILES + ACCENTED_PROFILES

STATIC_LABELS = ("KNOW YOUR FAN", "SPECIMEN", "DEMO ID", "CITY")

# Sanity threshold for clean, synthetic cards. Calibration from CI runs: the font bug
# (accents drawn as placeholder glyphs) gave about 83% token recall, and Ubuntu 24.04's
# Tesseract 5.3.4 currently gives 32/33 (it reads one "ç" as "g").
MIN_NAME_TOKEN_RECALL = 0.90


def test_accented_profiles_are_valid_synthetic_data() -> None:
    accented_words = {w for w in (*GIVEN_NAMES, *SURNAMES) if not w.isascii()}
    used = {w for name in ACCENTED_NAMES for w in name.split()}
    assert accented_words <= used
    assert all(synthetic_violations(p) == [] for p in ACCENTED_PROFILES)


def test_engine_version_and_language_data() -> None:
    assert pytesseract.get_tesseract_version().major >= 5
    languages = set(pytesseract.get_languages(config=""))
    assert {"por", "eng"} <= languages, languages


@pytest.fixture(scope="module")
def clean_card_texts() -> list[tuple[FanProfile, str]]:
    """OCR output for every clean card, computed once with the real engine."""
    return [(p, ocr.extract_text(ocr.render_specimen(p))) for p in CARD_PROFILES]


def test_static_card_labels_are_recognized(clean_card_texts: list[tuple[FanProfile, str]]) -> None:
    for profile, text in clean_card_texts:
        upper = text.upper()
        for label in STATIC_LABELS:
            assert label in upper, (profile.name, label, text)


def test_name_token_recall_on_clean_cards(clean_card_texts: list[tuple[FanProfile, str]]) -> None:
    """Aggregate recognition check; individual misreads are reported, not hidden.

    This is a sanity threshold for the integration, not an accuracy claim:
    OCR accuracy has not been measured yet (planned research work).
    """
    results = [(p.name, match_name(p.name, text)) for p, text in clean_card_texts]
    expected = sum(len(r.expected_tokens) for _, r in results)
    found = sum(len(r.found_tokens) for _, r in results)
    recall = found / expected
    misses = {name: r.missing_tokens for name, r in results if r.missing_tokens}
    assert recall >= MIN_NAME_TOKEN_RECALL, f"recall {recall:.2%} ({found}/{expected}); {misses}"


def test_name_absent_from_card_is_not_found(
    clean_card_texts: list[tuple[FanProfile, str]],
) -> None:
    for _, text in clean_card_texts:
        assert not match_name("Zeferino Quixadá", text).found_tokens


def test_service_pipeline_with_real_engine() -> None:
    profile = PROFILES[0]
    image = services.render_card(profile, blur_radius=0, rotation_degrees=0)
    outcome = services.run_text_matching(image, profile.name)
    assert "SPECIMEN" in outcome.extracted_text.upper()
    assert outcome.match.words.expected_tokens == match_name(profile.name, "").expected_tokens
    assert outcome.match.words.found_tokens, outcome.extracted_text
