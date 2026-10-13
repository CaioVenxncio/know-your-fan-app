from __future__ import annotations

from pathlib import Path

import pytest

from know_your_fan.models import FanProfile
from know_your_fan.storage import SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles


@pytest.fixture
def profile() -> FanProfile:
    return generate_profiles(1, seed=21)[0]


@pytest.fixture
def repo(tmp_path: Path) -> SyntheticProfileRepository:
    """A repository backed by a fresh database file in a per-test directory."""
    repository = SyntheticProfileRepository(tmp_path / "nested" / "demo.db")
    repository.initialize()
    return repository


@pytest.fixture(autouse=True)
def _isolate_engine_thread_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_runtime() sets OMP_THREAD_LIMIT in os.environ; restore it after each test."""
    monkeypatch.delenv("OMP_THREAD_LIMIT", raising=False)
