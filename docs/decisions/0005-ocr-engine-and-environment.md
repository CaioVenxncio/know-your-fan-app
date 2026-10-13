# ADR 0005: OCR engine and reproducible OCR environment

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-13

## Context

OCR is the system dependency that is hardest to reproduce. In the Phase 1 audit, Tesseract was
missing locally, so the end-to-end OCR test was skipped, and a skipped test proves nothing.

## Decision

- **Engine:** Tesseract **5.x** through `pytesseract`, with the `por` and `eng` language data
  (`lang="por+eng"`). It is open source (Apache-2.0), runs offline, is packaged by all major
  operating systems, and has no per-request cost.
- **CI (source of truth):** `ubuntu-24.04` installs `tesseract-ocr`, `tesseract-ocr-por`, and
  `tesseract-ocr-eng` from apt. The workflow prints `tesseract --version`, fails if `por` or `eng`
  is missing, and runs the end-to-end tests with `KYF_REQUIRE_OCR=1`. In that mode a missing
  engine **fails** the run instead of skipping.
- **Docker (local reproducibility):** a `Dockerfile` based on `python:3.13-slim-trixie` installs
  the same packages, runs as a non-root user, and is built and smoke-tested in CI. This includes
  real OCR on a synthetic specimen inside the image. It is a reproducible local runtime, not a
  deployment configuration.
- **Streamlit Community Cloud:** `packages.txt` lists the same apt packages.
- **Rendering font:** specimen cards use a bundled font (Aileron Regular, CC0) instead of a
  system font or Pillow's default. Pillow's default lacks accented glyphs, and the first CI run
  with a real engine exposed this: "João" was drawn and read as "JoXo". A bundled font gives
  identical card images on every platform.

## Consequences

- Versions differ by platform. Ubuntu 24.04 and Debian 13 ship different 5.x releases, and both
  are tested in CI (directly and via Docker). Windows and macOS installs are documented but not
  tested in CI.
- End-to-end OCR assertions are limited to clean specimens, where recognition is reliable.
  Measuring accuracy under degradation is research work (Phase 4), not a pass/fail test.
- Locally, without Tesseract or Docker, the OCR tests skip with a visible reason.

## Alternatives considered

- **Cloud OCR APIs:** these need credentials, send data to third parties, cost money, and
  produce non-reproducible results. Rejected.
- **Deep-learning OCR (PaddleOCR, docTR, EasyOCR):** heavier dependencies, which suit the Phase 4
  engine comparison but not the baseline demo. Deferred.
