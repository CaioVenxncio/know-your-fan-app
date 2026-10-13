# ADR 0003: SQLite for disposable demo storage

- **Status:** Accepted (Phase 1; error handling added in Phase 2)
- **Date:** 2026-10-13

## Context

The demo needs to keep a small dataset of synthetic profiles (25 seeded, at most 500) between
reruns of a Streamlit script. The data has no value beyond the demo and can be regenerated
deterministically.

## Decision

- Use the standard-library `sqlite3` module with a single local file, set by `KYF_DB_PATH`
  (default `.data/kyf_demo.db`, ignored by Git).
- Open one short-lived connection per repository operation, inside a transaction, and always
  close it.
- Wrap database and filesystem errors in `StorageError`.
- Seed deterministically when the table is empty.

## Consequences

- There is no server, credentials, or extra dependency, and tests use real SQLite files in
  temporary directories.
- On hosts with temporary filesystems the file disappears on restart. The app reseeds itself, so
  only generator-added profiles are lost. This is acceptable for a demo.
- Concurrency is limited by SQLite's single-writer lock. Short transactions and a 5-second busy
  timeout make contention errors unlikely at demo scale.
- No migrations framework exists. If the schema changes, the file can simply be deleted and
  reseeded.

## Alternatives considered

- **Hosted database (Postgres, etc.):** adds credentials, cost, and an external dependency for
  disposable data. Rejected.
- **In-memory only:** simpler, but profiles added by visitors would vanish on every rerun or
  session. Rejected.
- **ORM (SQLAlchemy/SQLModel):** one table with three queries does not justify it. Rejected.
