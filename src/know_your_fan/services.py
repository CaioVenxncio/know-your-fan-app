"""Application workflows, independent of the Streamlit presentation layer."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from PIL import Image

from know_your_fan import ocr
from know_your_fan.config import Settings
from know_your_fan.models import FanProfile
from know_your_fan.storage import SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles
from know_your_fan.text_matching import MatchResult, match_name

SEED_DATASET_SIZE = 25
SEED_DATASET_SEED = 2025
MAX_SEARCH_LENGTH = 50

TextExtractor = Callable[[Image.Image], str]


def open_repository(settings: Settings) -> SyntheticProfileRepository:
    """Create the demo database if needed and seed it with fictional profiles."""
    repo = SyntheticProfileRepository(settings.db_path)
    repo.initialize()
    repo.seed_if_empty(generate_profiles(SEED_DATASET_SIZE, seed=SEED_DATASET_SEED))
    return repo


def filter_profiles(
    profiles: Iterable[FanProfile], query: str = "", games: Sequence[str] = ()
) -> list[FanProfile]:
    """Filter by a case-insensitive name/city substring and by any selected game."""
    needle = query.strip().casefold()[:MAX_SEARCH_LENGTH]
    wanted = set(games)
    return [
        p
        for p in profiles
        if (not needle or needle in p.name.casefold() or needle in p.city.casefold())
        and (not wanted or wanted & set(p.interests))
    ]


def render_card(profile: FanProfile, blur_radius: float, rotation_degrees: float) -> Image.Image:
    """Render the fictional specimen card for ``profile`` with optional degradations."""
    return ocr.degrade(
        ocr.render_specimen(profile), blur_radius=blur_radius, rotation_degrees=rotation_degrees
    )


@dataclass(frozen=True, slots=True)
class TextMatchingOutcome:
    extracted_text: str
    match: MatchResult


def run_text_matching(
    image: Image.Image, expected_name: str, extract: TextExtractor | None = None
) -> TextMatchingOutcome:
    """Run OCR on ``image`` and report which words of ``expected_name`` were found.

    This is a text-matching demonstration, not identity verification. The
    expected name is validated before any OCR work is done.

    Raises:
        ValueError: the expected name is blank, too long, or not alphabetic.
        ocr.OCRUnavailableError, ocr.OCRFailedError, ocr.InvalidImageError.
    """
    match_name(expected_name, "")  # validate input cheaply before running OCR
    text = (extract or ocr.extract_text)(image)
    return TextMatchingOutcome(extracted_text=text, match=match_name(expected_name, text))
