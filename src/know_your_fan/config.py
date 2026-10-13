"""Runtime configuration read from environment variables.

Settings are loaded on demand by :func:`load_settings`; importing this module
has no side effects. Every operational limit has a safe default and an allowed
range. Invalid or out-of-range values raise :class:`ConfigurationError` instead
of being silently replaced, so a misconfigured deployment fails closed.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DB_PATH_ENV = "KYF_DB_PATH"
DEFAULT_DB_PATH = Path(".data") / "kyf_demo.db"

DEFAULT_OCR_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_IMAGE_PIXELS = 4_000_000


class ConfigurationError(ValueError):
    """An environment variable holds an invalid or unsafe value."""


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    # OCR
    ocr_timeout_seconds: float = DEFAULT_OCR_TIMEOUT_SECONDS
    ocr_session_limit: int = 5
    ocr_global_limit: int = 30
    ocr_window_seconds: float = 60.0
    ocr_max_concurrency: int = 2
    max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS
    # Storage
    max_profiles: int = 500
    sqlite_busy_timeout_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class _Limit:
    env: str
    kind: type[int] | type[float]
    minimum: float
    maximum: float


# Allowed ranges. Lower bounds keep the demo usable (for example, the profile
# cap must hold the 25 seeded profiles, and the pixel cap must fit a rotated
# specimen card); upper bounds keep a typo from disabling a safeguard.
_LIMITS: dict[str, _Limit] = {
    "ocr_timeout_seconds": _Limit("KYF_OCR_TIMEOUT_SECONDS", float, 1, 60),
    "ocr_session_limit": _Limit("KYF_OCR_SESSION_LIMIT", int, 1, 100),
    "ocr_global_limit": _Limit("KYF_OCR_GLOBAL_LIMIT", int, 1, 10_000),
    "ocr_window_seconds": _Limit("KYF_OCR_WINDOW_SECONDS", float, 1, 3600),
    "ocr_max_concurrency": _Limit("KYF_OCR_MAX_CONCURRENCY", int, 1, 8),
    "max_image_pixels": _Limit("KYF_MAX_IMAGE_PIXELS", int, 1_000_000, 16_000_000),
    "max_profiles": _Limit("KYF_MAX_PROFILES", int, 25, 10_000),
    "sqlite_busy_timeout_seconds": _Limit("KYF_SQLITE_BUSY_TIMEOUT_SECONDS", float, 0.1, 30),
}

ENVIRONMENT_VARIABLES = (DB_PATH_ENV, *(limit.env for limit in _LIMITS.values()))


def _parse(limit: _Limit, raw: str) -> int | float:
    allowed = (
        f"{limit.env} must be a {limit.kind.__name__} "
        f"between {limit.minimum:g} and {limit.maximum:g}"
    )
    try:
        value: int | float = limit.kind(raw.strip())
    except ValueError:
        raise ConfigurationError(allowed) from None
    if not math.isfinite(value) or not limit.minimum <= value <= limit.maximum:
        raise ConfigurationError(allowed)
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``environ`` (defaults to ``os.environ``).

    Unset or blank variables use the defaults. Raises :class:`ConfigurationError`
    for malformed, non-finite, or out-of-range values.
    """
    env = os.environ if environ is None else environ
    values: dict[str, Any] = {}  # each value is type-checked by _parse
    raw_path = env.get(DB_PATH_ENV, "").strip()
    if raw_path:
        values["db_path"] = Path(raw_path)
    for name, limit in _LIMITS.items():
        raw = env.get(limit.env, "")
        if raw.strip():
            values[name] = _parse(limit, raw)
    settings = replace(Settings(), **values)
    if settings.ocr_global_limit < settings.ocr_session_limit:
        raise ConfigurationError(
            f"{_LIMITS['ocr_global_limit'].env} must be at least {_LIMITS['ocr_session_limit'].env}"
        )
    return settings
