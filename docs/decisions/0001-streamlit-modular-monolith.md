# ADR 0001: Streamlit modular monolith

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-13

## Context

The original application was a single Streamlit script, and an earlier version had briefly
split into Streamlit plus FastAPI. The project is a small, single-user-type demo with no external
API consumers. Its goals are clarity, testability, and reproducibility for a portfolio and
research foundation.

## Decision

Keep **one Streamlit process and one Python package**, organized as a modular monolith:

- `app.py` holds presentation only, and is the only module that imports Streamlit;
- `services.py` holds the workflows;
- domain and infrastructure modules (`synthetic`, `storage`, `ocr`, `text_matching`, `config`,
  `models`) have no UI dependencies and no import-time side effects.

Plain functions and constructor parameters are used instead of a dependency-injection framework.
For example, `run_text_matching(..., extract=...)` accepts an alternative OCR function.

## Consequences

- Business logic is unit-testable without Streamlit. The UI is still tested end to end with
  `streamlit.testing.AppTest`.
- No network API exists. If a real consumer ever needs one, `services.py` is the seam to expose,
  and that would need a new ADR.
- Scaling is limited to one process per instance, which is acceptable for a demo.

## Alternatives considered

- **FastAPI backend plus Streamlit frontend:** it adds a network boundary, deployment, and
  authentication concerns without any consumer that needs them. Rejected.
- **Keeping the single script:** cannot be tested without running the UI. Rejected.
