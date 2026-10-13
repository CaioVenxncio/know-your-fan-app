from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from know_your_fan import config
from know_your_fan.config import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    ENVIRONMENT_VARIABLES,
    ConfigurationError,
    Settings,
    load_settings,
)


def test_defaults_when_environment_is_empty() -> None:
    settings = load_settings({})
    assert settings == Settings()
    assert settings.db_path == DEFAULT_DB_PATH
    assert settings.ocr_timeout_seconds == 15.0
    assert (settings.ocr_session_limit, settings.ocr_global_limit) == (5, 30)
    assert settings.ocr_window_seconds == 60.0
    assert settings.ocr_max_concurrency == 2
    assert settings.max_profiles == 500
    assert settings.max_image_pixels == 4_000_000
    assert settings.sqlite_busy_timeout_seconds == 5.0


def test_every_operational_setting_has_an_environment_variable() -> None:
    names = {f.name for f in fields(Settings)} - {"db_path"}
    assert names == set(config._LIMITS)
    assert len(ENVIRONMENT_VARIABLES) == len(names) + 1


def test_database_path_from_environment(tmp_path: Path) -> None:
    target = tmp_path / "custom.db"
    assert load_settings({DB_PATH_ENV: str(target)}).db_path == target


def test_blank_values_fall_back_to_defaults() -> None:
    env = dict.fromkeys(ENVIRONMENT_VARIABLES, "   ")
    assert load_settings(env) == Settings()


def test_valid_overrides_are_parsed() -> None:
    settings = load_settings(
        {
            "KYF_OCR_TIMEOUT_SECONDS": "7.5",
            "KYF_OCR_SESSION_LIMIT": "3",
            "KYF_OCR_GLOBAL_LIMIT": " 12 ",
            "KYF_OCR_WINDOW_SECONDS": "30",
            "KYF_OCR_MAX_CONCURRENCY": "1",
            "KYF_MAX_PROFILES": "100",
            "KYF_MAX_IMAGE_PIXELS": "2000000",
            "KYF_SQLITE_BUSY_TIMEOUT_SECONDS": "0.5",
        }
    )
    assert settings.ocr_timeout_seconds == 7.5
    assert (settings.ocr_session_limit, settings.ocr_global_limit) == (3, 12)
    assert settings.ocr_window_seconds == 30.0
    assert settings.ocr_max_concurrency == 1
    assert settings.max_profiles == 100
    assert settings.max_image_pixels == 2_000_000
    assert settings.sqlite_busy_timeout_seconds == 0.5


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("KYF_OCR_SESSION_LIMIT", "five"),
        ("KYF_OCR_SESSION_LIMIT", "2.5"),  # integers only
        ("KYF_OCR_SESSION_LIMIT", "0"),
        ("KYF_OCR_SESSION_LIMIT", "-1"),
        ("KYF_OCR_MAX_CONCURRENCY", "64"),  # above the safe maximum
        ("KYF_OCR_TIMEOUT_SECONDS", "nan"),
        ("KYF_OCR_TIMEOUT_SECONDS", "inf"),
        ("KYF_OCR_TIMEOUT_SECONDS", "0"),
        ("KYF_OCR_WINDOW_SECONDS", "1e9"),
        ("KYF_MAX_PROFILES", "10"),  # below the 25 seeded profiles
        ("KYF_MAX_IMAGE_PIXELS", "100"),  # a rotated specimen card would not fit
        ("KYF_SQLITE_BUSY_TIMEOUT_SECONDS", "-0.1"),
    ],
)
def test_invalid_values_fail_closed_and_name_the_variable(variable: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=variable):
        load_settings({variable: value})


def test_error_message_does_not_echo_the_raw_value() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({"KYF_OCR_SESSION_LIMIT": "s3cr3t-looking-value"})
    assert "s3cr3t" not in str(excinfo.value)


def test_global_limit_must_not_be_below_session_limit() -> None:
    with pytest.raises(ConfigurationError, match="KYF_OCR_GLOBAL_LIMIT"):
        load_settings({"KYF_OCR_SESSION_LIMIT": "10", "KYF_OCR_GLOBAL_LIMIT": "5"})


def test_reads_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "x.db"))
    monkeypatch.setenv("KYF_OCR_MAX_CONCURRENCY", "3")
    settings = load_settings()
    assert settings.db_path == tmp_path / "x.db"
    assert settings.ocr_max_concurrency == 3
