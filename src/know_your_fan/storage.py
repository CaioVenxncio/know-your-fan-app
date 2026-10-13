"""SQLite storage for the synthetic demo dataset.

Concurrency model:

* Each operation opens a short-lived connection in autocommit mode and always
  closes it, so no connection outlives a Streamlit rerun or crosses threads.
* Writes run inside ``BEGIN IMMEDIATE`` transactions, which take SQLite's
  write lock *before* the duplicate and capacity checks. The check and the
  insert are therefore atomic across threads, processes, and containers that
  share the database file, and concurrent writers cannot exceed the cap.
* A busy or locked database is retried by SQLite for ``busy_timeout_seconds``
  and then reported as :class:`StorageBusyError`.

Before anything is written, every profile must pass
:func:`know_your_fan.synthetic.synthetic_violations`, so the public UI cannot
persist anything except generator output.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from know_your_fan.models import FanProfile
from know_your_fan.observability import LOGGER_NAME
from know_your_fan.synthetic import synthetic_violations

MAX_PROFILES = 500
DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0

_logger = logging.getLogger(f"{LOGGER_NAME}.storage")

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
_INSERT = """
INSERT INTO synthetic_profiles
    (demo_id, name, city, interests, activities, purchases, social_links, esports_profiles)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""
_LIST_FIELDS = ("interests", "activities", "purchases", "social_links", "esports_profiles")
_BUSY_CODES = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


class StorageError(RuntimeError):
    """The demo database could not be opened, read, or written."""


class StorageBusyError(StorageError):
    """The database stayed locked by other writers for longer than the busy timeout."""


class StorageLimitError(StorageError):
    """The demo dataset has reached its configured maximum size."""


class UnsafeProfileError(ValueError):
    """A profile failed the synthetic-data allowlist and was not stored."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("Refusing to store a non-synthetic profile: " + "; ".join(problems))
        self.problems = problems


def _translate(exc: sqlite3.Error) -> StorageError:
    """Map a sqlite3 error to a safe StorageError, logging only its error code."""
    code = getattr(exc, "sqlite_errorname", type(exc).__name__)
    if getattr(exc, "sqlite_errorcode", None) in _BUSY_CODES:
        _logger.warning("Demo database busy (%s)", code)
        return StorageBusyError("The demo database is busy. Please try again.")
    _logger.error("Demo database operation failed (%s)", code)
    return StorageError("A demo database operation failed.")


def _validate(profile: FanProfile) -> None:
    problems = synthetic_violations(profile)
    if problems:
        _logger.warning("Rejected a non-synthetic profile (%d allowlist violations)", len(problems))
        raise UnsafeProfileError(problems)


def _row_values(profile: FanProfile) -> tuple[str, ...]:
    return (
        profile.demo_id,
        profile.name,
        profile.city,
        *(json.dumps(list(getattr(profile, f)), ensure_ascii=False) for f in _LIST_FIELDS),
    )


class SyntheticProfileRepository:
    def __init__(
        self,
        db_path: Path,
        max_profiles: int = MAX_PROFILES,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
    ) -> None:
        self.db_path = db_path
        self.max_profiles = max_profiles
        self.busy_timeout_seconds = busy_timeout_seconds

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.db_path, timeout=self.busy_timeout_seconds, isolation_level=None
            )
        except (OSError, sqlite3.Error) as exc:
            _logger.error("Demo database could not be opened (%s)", type(exc).__name__)
            raise StorageError("The demo database could not be opened.") from exc
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except sqlite3.Error as exc:
            raise _translate(exc) from exc
        finally:
            conn.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Run the body in ``BEGIN IMMEDIATE``; commit on success, roll back on any error."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def initialize(self) -> None:
        """Create the schema. Safe to run concurrently from several processes."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def count(self) -> int:
        with self._connect() as conn:
            return _count(conn)

    def add(self, profile: FanProfile) -> bool:
        """Insert a profile. Returns ``False`` if its identifier already exists.

        Raises :class:`UnsafeProfileError` before touching the database if the
        profile is not synthetic, and :class:`StorageLimitError` at capacity.
        """
        _validate(profile)
        with self._write_transaction() as conn:
            if _exists(conn, profile.demo_id):
                return False
            if _count(conn) >= self.max_profiles:
                _logger.info("Demo dataset is at capacity (%d profiles)", self.max_profiles)
                raise StorageLimitError(
                    f"The demo dataset is limited to {self.max_profiles} profiles."
                )
            conn.execute(_INSERT, _row_values(profile))
            return True

    def seed_if_empty(self, profiles: Sequence[FanProfile]) -> bool:
        """Insert ``profiles`` atomically if the table is empty. Returns whether it seeded.

        Concurrent callers serialize on the write lock, so exactly one of them seeds.
        """
        for profile in profiles:
            _validate(profile)
        if len(profiles) > self.max_profiles:
            raise StorageLimitError(f"The demo dataset is limited to {self.max_profiles} profiles.")
        with self._write_transaction() as conn:
            if _count(conn) > 0:
                return False
            conn.executemany(_INSERT, [_row_values(p) for p in profiles])
            return True

    def list_all(self) -> list[FanProfile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM synthetic_profiles ORDER BY created_at, demo_id"
            ).fetchall()
        return [_row_to_profile(row) for row in rows]


def _count(conn: sqlite3.Connection) -> int:
    total: int = conn.execute("SELECT COUNT(*) FROM synthetic_profiles").fetchone()[0]
    return total


def _exists(conn: sqlite3.Connection, demo_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM synthetic_profiles WHERE demo_id = ?", (demo_id,)).fetchone()
    return row is not None


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
