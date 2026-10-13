from __future__ import annotations

from pathlib import Path

import pytest

from know_your_fan.config import DB_PATH_ENV, DEFAULT_DB_PATH, load_settings


def test_default_database_path() -> None:
    assert load_settings({}).db_path == DEFAULT_DB_PATH


def test_database_path_from_environment(tmp_path: Path) -> None:
    target = tmp_path / "custom.db"
    assert load_settings({DB_PATH_ENV: str(target)}).db_path == target


def test_blank_environment_value_falls_back_to_default() -> None:
    assert load_settings({DB_PATH_ENV: "   "}).db_path == DEFAULT_DB_PATH


def test_reads_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "x.db"))
    assert load_settings().db_path == tmp_path / "x.db"
