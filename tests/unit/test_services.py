from __future__ import annotations

import pytest
from PIL import Image

from know_your_fan import ocr, services
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


def test_run_text_matching_defaults_to_the_ocr_module(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    monkeypatch.setattr(ocr, "extract_text", lambda image: "nothing relevant")
    outcome = services.run_text_matching(services.render_card(profile, 0, 0), profile.name)
    assert outcome.extracted_text == "nothing relevant"
    assert not outcome.match.found_tokens


def test_ocr_errors_propagate_to_the_caller(
    monkeypatch: pytest.MonkeyPatch, profile: FanProfile
) -> None:
    def unavailable(image: Image.Image) -> str:
        raise ocr.OCRUnavailableError("missing")

    with pytest.raises(ocr.OCRUnavailableError):
        services.run_text_matching(services.render_card(profile, 0, 0), profile.name, unavailable)
