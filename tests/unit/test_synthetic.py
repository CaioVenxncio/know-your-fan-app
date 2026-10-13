from __future__ import annotations

import dataclasses
import random
import re
from collections.abc import Callable

import pytest

from know_your_fan.models import FanProfile
from know_your_fan.synthetic import (
    DEMO_ID_PATTERN,
    generate_demo_id,
    generate_profile,
    generate_profiles,
    synthetic_violations,
)

CPF_LIKE = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")


def test_generation_is_deterministic_for_a_seed() -> None:
    assert generate_profiles(10, seed=7) == generate_profiles(10, seed=7)
    assert generate_profiles(10, seed=7) != generate_profiles(10, seed=8)


def test_single_profile_generation_matches_seeded_rng() -> None:
    assert generate_profile(random.Random(42)) == generate_profile(random.Random(42))


def test_zero_profiles_and_negative_count() -> None:
    assert generate_profiles(0, seed=1) == []
    with pytest.raises(ValueError, match="non-negative"):
        generate_profiles(-1, seed=1)


def test_demo_ids_are_well_formed_and_never_cpf_like() -> None:
    for p in generate_profiles(1000, seed=1):
        assert DEMO_ID_PATTERN.fullmatch(p.demo_id)
        assert not CPF_LIKE.search(p.demo_id)
        assert any(ch.isalpha() for ch in p.demo_id.removeprefix("KYF-DEMO-"))


def test_demo_ids_are_unique_in_a_large_sample() -> None:
    ids = [p.demo_id for p in generate_profiles(5000, seed=3)]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    "candidate",
    [
        "529.982.247-25",  # CPF formatting
        "52998224725",
        "KYF-DEMO-AAAA-AAA",  # too short
        "KYF-DEMO-AAAA-AAAI",  # 'I' is excluded from the alphabet
        "KYF-DEMO-AAAA-AAA0",  # '0' is excluded from the alphabet
        "kyf-demo-aaaa-aaaa",
        " KYF-DEMO-AAAA-AAAA",
    ],
)
def test_demo_id_pattern_rejects_other_formats(candidate: str) -> None:
    assert not DEMO_ID_PATTERN.fullmatch(candidate)


def test_generate_demo_id_uses_only_the_restricted_alphabet() -> None:
    rng = random.Random(0)
    assert all(DEMO_ID_PATTERN.fullmatch(generate_demo_id(rng)) for _ in range(500))


def test_links_use_the_reserved_example_domain() -> None:
    for p in generate_profiles(300, seed=2):
        for link in p.social_links + p.esports_profiles:
            assert link.split("/")[2].endswith(".example"), link


def test_every_generated_profile_passes_the_allowlist() -> None:
    assert all(synthetic_violations(p) == [] for p in generate_profiles(2000, seed=5))


Mutator = Callable[[FanProfile], FanProfile]


@pytest.mark.parametrize(
    ("mutate", "expected_problem"),
    [
        (lambda p: dataclasses.replace(p, demo_id="529.982.247-25"), "demo_id"),
        (lambda p: dataclasses.replace(p, name="Maria"), "name"),
        (lambda p: dataclasses.replace(p, name="Ana Lima Rua das Flores 123"), "name"),
        (lambda p: dataclasses.replace(p, city="Rua Exemplo, 123 - São Paulo"), "city"),
        (lambda p: dataclasses.replace(p, interests=()), "interests"),
        (lambda p: dataclasses.replace(p, interests=("My home address is ...",)), "interests"),
        (lambda p: dataclasses.replace(p, activities=("Valorant", "Valorant")), "activities"),
        (lambda p: dataclasses.replace(p, purchases=("Card ending 1234",)), "purchases"),
        (
            lambda p: dataclasses.replace(p, social_links=("https://social-network.com/someone",)),
            "social_links",
        ),
        (lambda p: dataclasses.replace(p, social_links=()), "social_links"),
        (
            lambda p: dataclasses.replace(p, esports_profiles=("javascript:alert(1)",)),
            "esports_profiles",
        ),
    ],
)
def test_allowlist_rejects_free_text_and_real_looking_values(
    profile: FanProfile, mutate: Mutator, expected_problem: str
) -> None:
    problems = synthetic_violations(mutate(profile))
    assert any(expected_problem in problem for problem in problems), problems
