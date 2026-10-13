from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from know_your_fan import ocr, services
from know_your_fan.config import Settings
from know_your_fan.limits import CapacityExceededError, OCRGuard, RateLimitedError
from know_your_fan.models import FanProfile
from know_your_fan.synthetic import generate_profiles

PROFILES = generate_profiles(30, seed=99)


def test_empty_filter_returns_everything() -> None:
    assert services.filter_profiles(PROFILES) == PROFILES


def test_query_matches_name_or_city_case_insensitively() -> None:
    target = PROFILES[0]
    by_name = services.filter_profiles(PROFILES, query=f"  {target.name.upper()}  ")
    assert target in by_name
    assert all(target.name.casefold() in p.name.casefold() for p in by_name)
    by_city = services.filter_profiles(PROFILES, query=target.city.lower())
    assert by_city
    assert all(p.city == target.city for p in by_city)


def test_query_without_matches_returns_empty_list() -> None:
    assert services.filter_profiles(PROFILES, query="zzz-no-such-fan") == []


def test_game_filter_keeps_profiles_with_any_selected_game() -> None:
    games = ("Valorant", "Dota 2")
    result = services.filter_profiles(PROFILES, games=games)
    assert result
    assert all(set(games) & set(p.interests) for p in result)
    assert len(result) == sum(bool(set(games) & set(p.interests)) for p in PROFILES)


def test_query_and_game_filters_combine() -> None:
    target = PROFILES[0]
    result = services.filter_profiles(PROFILES, query=target.name, games=[target.interests[0]])
    assert target in result


def test_render_card_applies_degradations(profile: FanProfile) -> None:
    clean = services.render_card(profile, blur_radius=0, rotation_degrees=0)
    rotated = services.render_card(profile, blur_radius=0, rotation_degrees=5)
    assert clean.size == ocr.SPECIMEN_SIZE
    assert rotated.size != clean.size


def test_run_text_matching_uses_extractor_output(profile: FanProfile) -> None:
    image = services.render_card(profile, 0, 0)
    outcome = services.run_text_matching(image, profile.name, extract=lambda _: profile.name)
    assert outcome.extracted_text == profile.name
    assert outcome.match.all_found


def test_run_text_matching_reports_partial_matches(profile: FanProfile) -> None:
    image = services.render_card(profile, 0, 0)
    first = profile.name.split()[0]
    outcome = services.run_text_matching(image, profile.name, extract=lambda _: first)
    assert not outcome.match.all_found
    assert outcome.match.found_tokens


@pytest.mark.parametrize("bad_name", ["", "   ", "1234"])
def test_invalid_name_is_rejected_before_ocr_runs(profile: FanProfile, bad_name: str) -> None:
    calls: list[Image.Image] = []

    def extractor(image: Image.Image) -> str:
        calls.append(image)
        return ""

    with pytest.raises(ValueError, match="at least one letter"):
        services.run_text_matching(services.render_card(profile, 0, 0), bad_name, extractor)
    assert calls == []


def test_run_text_matching_defaults_to_the_ocr_module_with_configured_limits(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    seen: dict[str, object] = {}

    def fake_extract(image: Image.Image, **kwargs: object) -> str:
        seen.update(kwargs)
        return "nothing relevant"

    monkeypatch.setattr(ocr, "extract_text", fake_extract)
    settings = Settings(ocr_timeout_seconds=7.0, max_image_pixels=2_000_000)
    outcome = services.run_text_matching(
        services.render_card(profile, 0, 0), profile.name, settings=settings
    )
    assert outcome.extracted_text == "nothing relevant"
    assert not outcome.match.found_tokens
    assert seen == {"timeout_seconds": 7.0, "max_pixels": 2_000_000}


def test_ocr_errors_propagate_to_the_caller(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    def unavailable(image: Image.Image) -> str:
        raise ocr.OCRUnavailableError("missing")

    with pytest.raises(ocr.OCRUnavailableError):
        services.run_text_matching(services.render_card(profile, 0, 0), profile.name, unavailable)


# ------------------------------------------------------------------ Phase 3: admission control


class CountingExtractor:
    def __init__(self, text: str = "") -> None:
        self.calls = 0
        self.text = text

    def __call__(self, image: Image.Image) -> str:
        self.calls += 1
        return self.text


def _guard(session_limit: int = 2, global_limit: int = 10) -> OCRGuard:
    settings = Settings(ocr_session_limit=session_limit, ocr_global_limit=global_limit)
    guard = OCRGuard.from_settings(settings, clock=lambda: 0.0)
    guard.concurrency.wait_seconds = 0
    return guard


def test_rate_limited_requests_never_reach_the_ocr_engine(profile: FanProfile) -> None:
    guard, extractor = _guard(session_limit=2), CountingExtractor(profile.name)
    image = services.render_card(profile, 0, 0)
    for _ in range(2):
        services.run_text_matching(image, profile.name, extractor, guard=guard, session_key="s")
    with pytest.raises(RateLimitedError):
        services.run_text_matching(image, profile.name, extractor, guard=guard, session_key="s")
    assert extractor.calls == 2


def test_busy_engine_rejects_without_running_ocr(profile: FanProfile) -> None:
    guard, extractor = _guard(), CountingExtractor()
    image = services.render_card(profile, 0, 0)
    guard.concurrency.acquire()  # simulate another session holding the only free slots
    guard.concurrency.acquire()
    with pytest.raises(CapacityExceededError):
        services.run_text_matching(image, profile.name, extractor, guard=guard, session_key="s")
    assert extractor.calls == 0


@pytest.mark.parametrize(
    ("name", "image"),
    [("   ", None), ("Ana", Image.new("L", (0, 0))), ("Ana", Image.new("L", (9000, 10)))],
)
def test_invalid_input_does_not_consume_rate_limit_budget(
    profile: FanProfile, name: str, image: Image.Image | None
) -> None:
    guard = _guard(session_limit=1)
    card = image if image is not None else services.render_card(profile, 0, 0)
    with pytest.raises(ValueError, match=r"letter|empty|too large"):  # incl. InvalidImageError
        services.run_text_matching(card, name, CountingExtractor(), guard=guard, session_key="s")
    # The single allowed request is still available.
    services.run_text_matching(
        services.render_card(profile, 0, 0),
        profile.name,
        CountingExtractor(),
        guard=guard,
        session_key="s",
    )


def test_ocr_timeout_releases_capacity(profile: FanProfile) -> None:
    guard = _guard()

    def timing_out(image: Image.Image) -> str:
        raise ocr.OCRTimeoutError("OCR timed out.")

    image = services.render_card(profile, 0, 0)
    with pytest.raises(ocr.OCRTimeoutError):
        services.run_text_matching(image, profile.name, timing_out, guard=guard, session_key="s")
    assert guard.concurrency.active == 0
    outcome = services.run_text_matching(
        image, profile.name, CountingExtractor(profile.name), guard=guard, session_key="s"
    )
    assert outcome.match.all_found


def test_profile_writes_are_rate_limited_per_session(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "demo.db")
    runtime = services.build_runtime(settings, clock=lambda: 0.0)
    fresh = generate_profiles(services.PROFILE_WRITE_LIMIT + 1, seed=12345)
    for p in fresh[:-1]:
        assert services.add_generated_profile(runtime, p, "visitor")
    with pytest.raises(RateLimitedError):
        services.add_generated_profile(runtime, fresh[-1], "visitor")
    assert services.add_generated_profile(runtime, fresh[-1], "another-session")
    assert runtime.repository.count() == services.SEED_DATASET_SIZE + len(fresh)


def test_build_runtime_applies_settings(tmp_path: Path) -> None:
    settings = Settings(
        db_path=tmp_path / "demo.db",
        max_profiles=40,
        ocr_max_concurrency=3,
        sqlite_busy_timeout_seconds=1.5,
    )
    runtime = services.build_runtime(settings)
    assert runtime.repository.max_profiles == 40
    assert runtime.repository.busy_timeout_seconds == 1.5
    assert runtime.ocr_guard.concurrency.capacity == 3
    assert runtime.repository.count() == services.SEED_DATASET_SIZE
