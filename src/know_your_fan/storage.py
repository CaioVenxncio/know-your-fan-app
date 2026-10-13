"""SQLite storage for the synthetic demo dataset.

Each operation opens a short-lived connection and closes it again, so no
connection outlives a Streamlit rerun. Before anything is written, the profile
must pass :func:`know_your_fan.synthetic.synthetic_violations`, which keeps the
public UI from persisting anything except generator output.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from know_your_fan.models import FanProfile
from know_your_fan.synthetic import synthetic_violations

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


class StorageError(RuntimeError):
    """The demo database could not be opened, read, or written."""


class StorageLimitError(StorageError):
    """The demo dataset has reached its configured maximum size."""


class UnsafeProfileError(ValueError):
    """A profile failed the synthetic-data allowlist and was not stored."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("Refusing to store a non-synthetic profile: " + "; ".join(problems))
        self.problems = problems


class SyntheticProfileRepository:
    def __init__(self, db_path: Path, max_profiles: int = MAX_PROFILES) -> None:
        self.db_path = db_path
        self.max_profiles = max_profiles

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=5)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("The demo database could not be opened.") from exc
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        except sqlite3.Error as exc:
            raise StorageError("A demo database operation failed.") from exc
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def count(self) -> int:
        with self._connect() as conn:
            total: int = conn.execute("SELECT COUNT(*) FROM synthetic_profiles").fetchone()[0]
        return total

    def add(self, profile: FanProfile) -> bool:
        """Insert a profile. Returns ``False`` if its identifier already exists."""
        problems = synthetic_violations(profile)
        if problems:
            raise UnsafeProfileError(problems)
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM synthetic_profiles").fetchone()[0]
            if total >= self.max_profiles:
                raise StorageLimitError(
                    f"The demo dataset is limited to {self.max_profiles} profiles."
                )
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO synthetic_profiles
                    (demo_id, name, city, interests, activities, purchases,
                     social_links, esports_profiles)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.demo_id,
                    profile.name,
                    profile.city,
                    *(
                        json.dumps(list(getattr(profile, f)), ensure_ascii=False)
                        for f in _LIST_FIELDS
                    ),
                ),
            )
            return cursor.rowcount == 1

    def seed_if_empty(self, profiles: list[FanProfile]) -> None:
        if self.count() == 0:
            for profile in profiles:
                self.add(profile)

    def list_all(self) -> list[FanProfile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM synthetic_profiles ORDER BY created_at, demo_id"
            ).fetchall()
        return [_row_to_profile(row) for row in rows]


def _row_to_profile(row: sqlite3.Row) -> FanProfile:
    lists = {f: tuple(json.loads(row[f])) for f in _LIST_FIELDS}
    return FanProfile(
        demo_id=row["demo_id"],
        name=row["name"],
        city=row["city"],
        interests=lists["interests"],
        activities=lists["activities"],
        purchases=lists["purchases"],
        social_links=lists["social_links"],
        esports_profiles=lists["esports_profiles"],
    )
