"""Storage tests against real SQLite files in per-test temporary directories."""

from __future__ import annotations

import dataclasses
import logging
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from know_your_fan import storage
from know_your_fan.models import FanProfile
from know_your_fan.storage import (
    StorageBusyError,
    StorageError,
    StorageLimitError,
    SyntheticProfileRepository,
    UnsafeProfileError,
)
from know_your_fan.synthetic import generate_profiles


def test_round_trip_preserves_every_field(repo: SyntheticProfileRepository) -> None:
    profiles = generate_profiles(5, seed=11)
    assert all(repo.add(p) for p in profiles)
    assert sorted(repo.list_all(), key=lambda p: p.demo_id) == sorted(
        profiles, key=lambda p: p.demo_id
    )


def test_accented_text_is_stored_unchanged(repo: SyntheticProfileRepository) -> None:
    accented = next(p for p in generate_profiles(200, seed=4) if not p.name.isascii())
    repo.add(accented)
    assert repo.list_all() == [accented]


def test_initialize_is_idempotent_and_creates_parent_dirs(tmp_path: Path) -> None:
    repository = SyntheticProfileRepository(tmp_path / "a" / "b" / "demo.db")
    repository.initialize()
    repository.initialize()
    assert repository.count() == 0


def test_duplicate_identifier_is_ignored(repo: SyntheticProfileRepository) -> None:
    profile = generate_profiles(1, seed=12)[0]
    assert repo.add(profile)
    assert not repo.add(profile)
    assert repo.count() == 1


def test_data_persists_across_repository_instances(tmp_path: Path) -> None:
    path = tmp_path / "demo.db"
    first = SyntheticProfileRepository(path)
    first.initialize()
    first.add(generate_profiles(1, seed=13)[0])
    second = SyntheticProfileRepository(path)
    assert second.count() == 1


def test_separate_databases_are_isolated(tmp_path: Path) -> None:
    a = SyntheticProfileRepository(tmp_path / "a.db")
    b = SyntheticProfileRepository(tmp_path / "b.db")
    a.initialize()
    b.initialize()
    a.add(generate_profiles(1, seed=14)[0])
    assert (a.count(), b.count()) == (1, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"demo_id": "12345678909"},
        {"city": "Rua Exemplo, 123"},
        {"name": "Real Person Name"},
        {"social_links": ("https://real-network.com/user",)},
    ],
)
def test_non_synthetic_profiles_are_never_persisted(
    repo: SyntheticProfileRepository, profile: FanProfile, changes: dict[str, Any]
) -> None:
    with pytest.raises(UnsafeProfileError) as excinfo:
        repo.add(dataclasses.replace(profile, **changes))
    assert excinfo.value.problems
    assert repo.count() == 0


def test_capacity_limit_is_enforced(tmp_path: Path) -> None:
    repository = SyntheticProfileRepository(tmp_path / "demo.db", max_profiles=3)
    repository.initialize()
    profiles = generate_profiles(4, seed=15)
    for p in profiles[:3]:
        repository.add(p)
    with pytest.raises(StorageLimitError, match="limited to 3"):
        repository.add(profiles[3])
    assert repository.count() == 3


def test_default_capacity_matches_module_constant(repo: SyntheticProfileRepository) -> None:
    assert repo.max_profiles == storage.MAX_PROFILES == 500


def test_seed_if_empty_only_seeds_once(repo: SyntheticProfileRepository) -> None:
    repo.seed_if_empty(generate_profiles(4, seed=16))
    repo.seed_if_empty(generate_profiles(4, seed=17))
    assert repo.count() == 4


def test_every_connection_is_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    repository = SyntheticProfileRepository(tmp_path / "demo.db")
    repository.initialize()
    repository.add(generate_profiles(1, seed=18)[0])
    repository.list_all()
    repository.count()
    with pytest.raises(UnsafeProfileError):
        repository.add(dataclasses.replace(generate_profiles(1, seed=19)[0], city="x"))

    assert len(opened) == 4  # the rejected profile never opened a connection
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_failed_write_rolls_back(repo: SyntheticProfileRepository) -> None:
    repo.add(generate_profiles(1, seed=20)[0])

    def delete_then_fail() -> None:
        with repo._write_transaction() as conn:
            conn.execute("DELETE FROM synthetic_profiles")
            conn.execute("SELECT * FROM no_such_table")

    with pytest.raises(StorageError, match="operation failed"):
        delete_then_fail()
    assert repo.count() == 1


def test_database_path_that_is_a_directory_raises_storage_error(tmp_path: Path) -> None:
    directory = tmp_path / "is_a_dir.db"
    directory.mkdir()
    with pytest.raises(StorageError, match="could not be opened"):
        SyntheticProfileRepository(directory).initialize()


def test_parent_that_is_a_file_raises_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(StorageError):
        SyntheticProfileRepository(blocker / "demo.db").initialize()


def test_corrupt_database_file_raises_storage_error(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"this is not an sqlite database" * 200)
    with pytest.raises(StorageError, match="operation failed"):
        SyntheticProfileRepository(path).initialize()


def test_uninitialized_database_raises_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        SyntheticProfileRepository(tmp_path / "empty.db").count()


# ------------------------------------------------------------------ Phase 3: concurrency


def _run_concurrently(workers: int, target: Callable[[int], None]) -> None:
    """Start ``workers`` threads together (barrier) and wait for all of them."""
    start = threading.Barrier(workers)

    def run(index: int) -> None:
        start.wait()
        target(index)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_concurrent_writers_cannot_exceed_the_cap(tmp_path: Path) -> None:
    cap, workers, per_worker = 30, 8, 10
    path = tmp_path / "demo.db"
    SyntheticProfileRepository(path).initialize()
    profiles = generate_profiles(workers * per_worker, seed=31)
    outcomes: list[str] = []
    lock = threading.Lock()

    def writer(index: int) -> None:
        repo = SyntheticProfileRepository(path, max_profiles=cap, busy_timeout_seconds=10)
        for profile in profiles[index * per_worker : (index + 1) * per_worker]:
            try:
                outcome = "added" if repo.add(profile) else "duplicate"
            except StorageLimitError:
                outcome = "limit"
            with lock:
                outcomes.append(outcome)

    _run_concurrently(workers, writer)
    assert SyntheticProfileRepository(path).count() == cap
    assert outcomes.count("added") == cap
    assert outcomes.count("limit") == workers * per_worker - cap


_PROCESS_WRITER = """
import sys
from pathlib import Path
from know_your_fan.storage import StorageLimitError, SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles
path, cap, seed, count = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
repo = SyntheticProfileRepository(path, max_profiles=cap, busy_timeout_seconds=20)
for profile in generate_profiles(count, seed=seed):
    try:
        print("added" if repo.add(profile) else "duplicate")
    except StorageLimitError:
        print("limit")
"""


def test_writers_in_separate_processes_cannot_exceed_the_cap(tmp_path: Path) -> None:
    # Several app processes or containers sharing one database file (for example,
    # replicas on a shared volume) serialize on SQLite's file lock, not a Python lock.
    cap, processes, per_process = 25, 4, 15
    path = tmp_path / "demo.db"
    SyntheticProfileRepository(path).initialize()
    commands = [
        [sys.executable, "-c", _PROCESS_WRITER, str(path), str(cap), str(100 + i), str(per_process)]
        for i in range(processes)
    ]
    # Fixed arguments built by the test itself; no shell.
    running = [subprocess.Popen(c, stdout=subprocess.PIPE, text=True) for c in commands]  # noqa: S603
    outcomes = [line for p in running for line in p.communicate(timeout=120)[0].split()]
    assert all(p.returncode == 0 for p in running)
    assert SyntheticProfileRepository(path).count() == cap
    assert outcomes.count("added") == cap
    assert outcomes.count("limit") == processes * per_process - cap


def test_concurrent_seeding_inserts_exactly_once(tmp_path: Path) -> None:
    path = tmp_path / "demo.db"
    SyntheticProfileRepository(path).initialize()
    seeds = generate_profiles(25, seed=2025)
    results: list[bool] = []
    lock = threading.Lock()

    def seeder(_: int) -> None:
        seeded = SyntheticProfileRepository(path, busy_timeout_seconds=10).seed_if_empty(seeds)
        with lock:
            results.append(seeded)

    _run_concurrently(6, seeder)
    assert results.count(True) == 1
    assert SyntheticProfileRepository(path).count() == 25


def test_locked_database_raises_busy_error_after_timeout(tmp_path: Path) -> None:
    path = tmp_path / "demo.db"
    repo = SyntheticProfileRepository(path, busy_timeout_seconds=0.1)
    repo.initialize()
    blocker = sqlite3.connect(path, isolation_level=None)
    try:
        blocker.execute("BEGIN EXCLUSIVE")  # another writer holds the database
        with pytest.raises(StorageBusyError, match="busy"):
            repo.add(generate_profiles(1, seed=32)[0])
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert repo.add(generate_profiles(1, seed=32)[0])  # usable again once the lock is gone


def test_seed_rejects_non_synthetic_profiles_without_writing(
    repo: SyntheticProfileRepository, profile: FanProfile
) -> None:
    with pytest.raises(UnsafeProfileError):
        repo.seed_if_empty([profile, dataclasses.replace(profile, city="Rua Real, 1")])
    assert repo.count() == 0


def test_seed_larger_than_cap_is_refused(tmp_path: Path) -> None:
    repository = SyntheticProfileRepository(tmp_path / "demo.db", max_profiles=3)
    repository.initialize()
    with pytest.raises(StorageLimitError):
        repository.seed_if_empty(generate_profiles(4, seed=33))
    assert repository.count() == 0


def test_duplicate_at_capacity_reports_duplicate_not_limit(tmp_path: Path) -> None:
    repository = SyntheticProfileRepository(tmp_path / "demo.db", max_profiles=1)
    repository.initialize()
    only = generate_profiles(1, seed=34)[0]
    assert repository.add(only)
    assert repository.add(only) is False


def test_storage_logs_contain_error_codes_but_no_profile_data(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, profile: FanProfile
) -> None:
    path = tmp_path / "demo.db"
    repo = SyntheticProfileRepository(path, busy_timeout_seconds=0.1)
    repo.initialize()
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with caplog.at_level(logging.DEBUG, logger="know_your_fan"):
            with pytest.raises(StorageBusyError):
                repo.add(profile)
            with pytest.raises(UnsafeProfileError):
                repo.add(dataclasses.replace(profile, city="Rua Secreta 42"))
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert "SQLITE_BUSY" in caplog.text
    for sensitive in (profile.name, profile.demo_id, "Rua Secreta", str(path)):
        assert sensitive not in caplog.text
