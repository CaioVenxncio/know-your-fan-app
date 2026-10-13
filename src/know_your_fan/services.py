"""Application workflows, independent of the Streamlit presentation layer."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial

from PIL import Image

from know_your_fan import ocr
from know_your_fan.config import Settings
from know_your_fan.limits import Clock, OCRGuard, SlidingWindowRateLimiter
from know_your_fan.models import FanProfile
from know_your_fan.storage import SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles
from know_your_fan.text_matching import MatchResult, match_name

SEED_DATASET_SIZE = 25
SEED_DATASET_SEED = 2025
MAX_SEARCH_LENGTH = 50

# Per-session limit on adding generated profiles to the shared dataset. It slows a
# single visitor from filling the dataset; the hard bound remains max_profiles.
PROFILE_WRITE_LIMIT = 10
PROFILE_WRITE_WINDOW_SECONDS = 600.0

TextExtractor = Callable[[Image.Image], str]


@dataclass(frozen=True, slots=True)
class Runtime:
    """Process-wide objects shared by all sessions (created once per process)."""

    settings: Settings
    repository: SyntheticProfileRepository
    ocr_guard: OCRGuard
    profile_write_limiter: SlidingWindowRateLimiter


def open_repository(settings: Settings) -> SyntheticProfileRepository:
    """Create the demo database if needed and seed it with fictional profiles."""
    repo = SyntheticProfileRepository(
        settings.db_path,
        max_profiles=settings.max_profiles,
        busy_timeout_seconds=settings.sqlite_busy_timeout_seconds,
    )
    repo.initialize()
    repo.seed_if_empty(generate_profiles(SEED_DATASET_SIZE, seed=SEED_DATASET_SEED))
    return repo


def build_runtime(settings: Settings, *, clock: Clock = time.monotonic) -> Runtime:
    """Create the process-wide runtime. Also caps Tesseract's per-process threads."""
    ocr.limit_engine_threads()
    return Runtime(
        settings=settings,
        repository=open_repository(settings),
        ocr_guard=OCRGuard.from_settings(settings, clock=clock),
        profile_write_limiter=SlidingWindowRateLimiter(
            PROFILE_WRITE_LIMIT, PROFILE_WRITE_WINDOW_SECONDS, clock=clock
        ),
    )


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


def add_generated_profile(runtime: Runtime, profile: FanProfile, session_key: str) -> bool:
    """Add a generated profile, subject to the per-session write limit.

    Raises :class:`~know_your_fan.limits.RateLimitedError` before touching the
    database when the session exceeds its write budget.
    """
    runtime.profile_write_limiter.acquire(session_key)
    return runtime.repository.add(profile)


@dataclass(frozen=True, slots=True)
class TextMatchingOutcome:
    extracted_text: str
    match: MatchResult


def run_text_matching(
    image: Image.Image,
    expected_name: str,
    extract: TextExtractor | None = None,
    *,
    guard: OCRGuard | None = None,
    session_key: str = "local",
    settings: Settings | None = None,
) -> TextMatchingOutcome:
    """Run OCR on ``image`` and report which words of ``expected_name`` were found.

    This is a text-matching demonstration, not identity verification. Cheap
    checks (name and image metadata) run first; then ``guard`` (if given)
    applies rate and concurrency limits before Tesseract starts.

    Raises:
        ValueError: the expected name is blank, too long, or not alphabetic.
        ocr.InvalidImageError: the image is empty, too large, or unsupported.
        limits.RateLimitedError, limits.CapacityExceededError: request refused.
        ocr.OCRUnavailableError, ocr.OCRFailedError (incl. OCRTimeoutError).
    """
    config = settings or Settings()
    match_name(expected_name, "")  # validate input cheaply before running OCR
    ocr.check_image(image, config.max_image_pixels)
    extractor = extract or partial(
        ocr.extract_text,
        timeout_seconds=config.ocr_timeout_seconds,
        max_pixels=config.max_image_pixels,
    )
    if guard is None:
        text = extractor(image)
    else:
        with guard.admit(session_key):
            text = extractor(image)
    return TextMatchingOutcome(extracted_text=text, match=match_name(expected_name, text))
