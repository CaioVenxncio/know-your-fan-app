import dataclasses

import pytest

from know_your_fan import storage
from know_your_fan.storage import StorageLimitError, SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles


@pytest.fixture
def repo(tmp_path):
    repository = SyntheticProfileRepository(tmp_path / "nested" / "demo.db")
    repository.initialize()
    return repository


def test_round_trip(repo):
    profiles = generate_profiles(5, seed=11)
    for profile in profiles:
        assert repo.add(profile)
    assert sorted(repo.list_all(), key=lambda p: p.demo_id) == sorted(profiles, key=lambda p: p.demo_id)


def test_duplicate_is_ignored(repo):
    profile = generate_profiles(1, seed=12)[0]
    assert repo.add(profile)
    assert not repo.add(profile)
    assert repo.count() == 1


def test_rejects_non_synthetic_identifiers(repo):
    profile = dataclasses.replace(generate_profiles(1, seed=13)[0], demo_id="12345678909")
    with pytest.raises(ValueError):
        repo.add(profile)
    assert repo.count() == 0


def test_enforces_size_limit(repo, monkeypatch):
    monkeypatch.setattr(storage, "MAX_PROFILES", 3)
    profiles = generate_profiles(4, seed=14)
    for profile in profiles[:3]:
        repo.add(profile)
    with pytest.raises(StorageLimitError):
        repo.add(profiles[3])


def test_seed_if_empty_only_seeds_once(repo):
    repo.seed_if_empty(generate_profiles(4, seed=15))
    repo.seed_if_empty(generate_profiles(4, seed=16))
    assert repo.count() == 4


def test_resolve_db_path_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KYF_DB_PATH", str(tmp_path / "x.db"))
    assert storage.resolve_db_path() == tmp_path / "x.db"
