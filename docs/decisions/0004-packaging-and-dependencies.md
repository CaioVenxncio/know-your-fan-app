# ADR 0004: Packaging and dependency management

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-13

## Context

Phase 1 left a flat package and two hand-written requirements files. Phase 2 needs reproducible
installs, separate development tooling, and a single place for tool configuration. The app must
still start with `streamlit run main.py`, including on hosts that only run
`pip install -r requirements.txt`.

## Decision

1. **`pyproject.toml` is the single source of truth.** It holds project metadata, runtime
   dependencies, a `dev` dependency group, and the configuration for Ruff, mypy, pytest, and
   coverage. The build backend is hatchling.
2. **`uv` with a committed `uv.lock`.** It resolves exact versions with hashes. CI installs with
   `uv sync --locked`, which fails if the lock is out of date.
3. **Lower bounds only for runtime dependencies,** each one justified:
   - `streamlit>=1.60`: the `width="stretch"` API used by the app; the lowest version tested.
   - `pillow>=11.3`: includes the CVE-2025-48379 fix, plus `ImageFont.load_default(size=...)`.
   - `pytesseract>=0.3.13`: the `timeout` argument and Python 3.13 support.

   The lockfile, not upper caps, provides reproducibility. These lower bounds were verified by
   installing with `--resolution lowest-direct` and running the full test suite.
4. **`src/` layout.** Tests import the installed package instead of the working directory, which
   catches packaging mistakes. `main.py` adds `src/` to the import path only when the package
   is not installed.
5. **`requirements.txt` is generated,** not edited:
   `uv export --no-dev --no-emit-project --no-hashes --format requirements-txt -o requirements.txt`.
   It exists for hosts that expect it, such as Streamlit Community Cloud. CI fails if it drifts
   from `uv.lock`.
6. **Python 3.13** is the supported version (`requires-python = ">=3.13"`) and the only one
   tested in CI.

## Consequences

- Contributors need `uv` (or can use pip with `requirements.txt` for running the app only).
- `requirements-dev.txt` was removed in favour of `[dependency-groups].dev`.
- How Streamlit Community Cloud handles `uv.lock` and `requirements.txt` together has not been
  verified, because nothing has been deployed.

## Alternatives considered

- **Poetry / PDM:** both are capable, but uv is faster, supports the standard `dependency-groups`
  table, and offers lockfile export for compatibility. Chosen: uv.
- **pip-tools:** this needs separate files for each group and has no project management.
  Rejected.
