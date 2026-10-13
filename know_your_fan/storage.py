"""SQLite storage for the synthetic demo dataset.

Each operation opens a short-lived connection and closes it again, so no
connection outlives a Streamlit rerun. The repository only accepts profiles
whose identifier matches the synthetic ``KYF-DEMO-`` format, which keeps the
public UI from persisting anything else.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from know_your_fan.models import FanProfile
from know_your_fan.synthetic import DEMO_ID_PATTERN

DEFAULT_DB_PATH = Path(".data") / "kyf_demo.db"
MAX_PROFILES = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS synthetic_profiles (
    demo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    interests TEXT NOT NULL,
    activities TEXT NOT NULL,
    purchases TEXT NOT NULL,
    social_links TEXT NOT NULL,
    esports_profiles TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_LIST_FIELDS = ("interests", "activities", "purchases", "social_links", "esports_profiles")


class StorageLimitError(RuntimeError):
    """Raised when the demo dataset has reached :data:`MAX_PROFILES`."""


def resolve_db_path() -> Path:
    """Return the database path from ``KYF_DB_PATH`` or the default."""
    return Path(os.environ.get("KYF_DB_PATH", DEFAULT_DB_PATH))


class SyntheticProfileRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM synthetic_profiles").fetchone()[0]

    def add(self, profile: FanProfile) -> bool:
        """Insert a profile. Returns ``False`` if its identifier already exists."""
        if not DEMO_ID_PATTERN.fullmatch(profile.demo_id):
            raise ValueError("Only synthetic KYF-DEMO profiles can be stored.")
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM synthetic_profiles").fetchone()[0]
            if total >= MAX_PROFILES:
                raise StorageLimitError(f"The demo dataset is limited to {MAX_PROFILES} profiles.")
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO synthetic_profiles
                    (demo_id, name, city, interests, activities, purchases, social_links, esports_profiles)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.demo_id,
                    profile.name,
                    profile.city,
                    *(json.dumps(list(getattr(profile, f)), ensure_ascii=False) for f in _LIST_FIELDS),
                ),
            )
            return cursor.rowcount == 1

    def seed_if_empty(self, profiles: list[FanProfile]) -> None:
        if self.count() == 0:
            for profile in profiles:
                self.add(profile)

    def list_all(self) -> list[FanProfile]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM synthetic_profiles ORDER BY created_at, demo_id").fetchall()
        return [
            FanProfile(
                demo_id=row["demo_id"],
                name=row["name"],
                city=row["city"],
                **{f: tuple(json.loads(row[f])) for f in _LIST_FIELDS},
            )
            for row in rows
        ]
