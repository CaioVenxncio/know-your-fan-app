import re

from know_your_fan.synthetic import DEMO_ID_PATTERN, generate_profiles

CPF_LIKE = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")


def test_generation_is_deterministic():
    assert generate_profiles(10, seed=7) == generate_profiles(10, seed=7)
    assert generate_profiles(10, seed=7) != generate_profiles(10, seed=8)


def test_demo_ids_cannot_be_confused_with_cpf():
    for profile in generate_profiles(500, seed=1):
        assert DEMO_ID_PATTERN.fullmatch(profile.demo_id)
        assert not CPF_LIKE.search(profile.demo_id)
        assert any(ch.isalpha() for ch in profile.demo_id.removeprefix("KYF-DEMO-"))


def test_links_use_reserved_example_domain():
    for profile in generate_profiles(200, seed=2):
        for link in profile.social_links + profile.esports_profiles:
            host = link.split("/")[2]
            assert host.endswith(".example"), link


def test_profiles_contain_no_cpf_like_values():
    for profile in generate_profiles(200, seed=3):
        for value in (profile.name, profile.city, *profile.activities, *profile.purchases):
            assert not CPF_LIKE.search(value)
