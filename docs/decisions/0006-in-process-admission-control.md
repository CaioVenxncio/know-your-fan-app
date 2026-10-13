# ADR 0006: In-process admission control for OCR

- **Status:** Accepted (Phase 3)
- **Date:** 2026-10-13

## Context

OCR is the demo's most expensive operation: a Tesseract subprocess per request. Before Phase 3,
the number of requests and of concurrent processes was unbounded. The demo runs as a single
Streamlit process (local, Docker, or a single Streamlit Community Cloud instance), and the project
avoids extra infrastructure ([ADR 0001](0001-streamlit-modular-monolith.md)).

## Decision

- Enforce limits **inside the Python process**, shared by all sessions through
  `st.cache_resource`:
  - a per-session sliding-window rate limit;
  - a process-wide sliding-window rate limit;
  - a bounded semaphore for concurrent OCR jobs, with a short bounded wait and no queue.
- Run the cheap checks first: the name, the image metadata, then rate limits, then capacity.
  Tesseract starts only after all of them pass.
- Limit each Tesseract process to one OpenMP thread (`OMP_THREAD_LIMIT=1` unless the operator sets
  it). CI showed that without this, two concurrent jobs took about 6.3 s each instead of about
  0.36 s.
- Keep the profile cap in SQLite (`BEGIN IMMEDIATE`) rather than in memory, so it also holds
  across processes.

## Consequences

- There are no new services or dependencies, and behaviour is deterministic and testable with a
  fake clock.
- Limits do not add up across replicas. N replicas allow N times the global rate and concurrency.
  This is documented as a limitation.
- Per-session limits are only a fairness measure, because new sessions get new identifiers.

## Alternatives considered

- **Redis or another shared store:** this would provide limits across replicas, but it is an extra
  service, credentials, and failure mode for a single-instance demo. Revisit if the demo ever runs
  multiple replicas.
- **A task queue (Celery, RQ):** it would add a worker framework and an unbounded backlog to manage.
  Rejected: rejecting work quickly is simpler and bounds latency.
- **Session-state-only limits:** trivially bypassed. Kept only as a fairness layer on top of the
  global limit.
