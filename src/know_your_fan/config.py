"""Runtime configuration read from environment variables.

Settings are loaded on demand by :func:`load_settings`; importing this module
has no side effects.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DB_PATH_ENV = "KYF_DB_PATH"
DEFAULT_DB_PATH = Path(".data") / "kyf_demo.db"


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``environ`` (defaults to ``os.environ``)."""
    env = os.environ if environ is None else environ
    raw_path = env.get(DB_PATH_ENV, "").strip()
    return Settings(db_path=Path(raw_path) if raw_path else DEFAULT_DB_PATH)
