# Know Your Fan

**An independent, esports-themed software engineering project for exploring fictional fan profiles and OCR-based text matching, built with Python and Streamlit.**

> **Synthetic data only.** Every profile and document in this application is fictional.
> The app does not accept real names, CPF numbers, addresses, or identity documents.
> Its OCR and name matching are **not** identity verification, document authentication, or fraud detection.
>
> Know Your Fan is an independent project. It is not an official product of, partnership with, or
> initiative of any esports organization, and it is not endorsed or sponsored by one.

---

## Purpose

The author originally built Know Your Fan, independently, as an entry to a technology and esports challenge. It was a
fan-registration app that collected personal data and ran OCR on uploaded identity documents.
It is now a standalone portfolio and research-foundation project. It keeps the original ideas
(fan profiles and document-text processing) but is redesigned so that it never handles real personal information.

Current scope:

- esports-themed synthetic fan profiles;
- generating and exploring fictional profiles;
- OCR text extraction from synthetic specimen documents;
- text-matching experiments on the extracted text;
- privacy-conscious application design;
- a foundation for future reproducible research (see *Planned work*).

## Implemented features

| Page | What it does |
|---|---|
| **About** | Explains the scope and limits of the demo. |
| **Fan explorer** | Browse and filter a seeded dataset of fictional fan profiles. |
| **Profile generator** | Generate a fictional profile from a numeric seed and optionally add it to the local demo dataset. There are no free-text fields. |
| **Text-matching demo** | Render a fictional, watermarked fan card, optionally blur or rotate it, run Tesseract OCR, and report which words of a name appear in the extracted text. |

### Synthetic-only data policy

- The app has no form for real personal data and no file upload. All profiles come from a
  deterministic generator.
- Demo identifiers look like `KYF-DEMO-7FQA-91CZ`. They always contain letters, so they cannot be
  confused with an 11-digit CPF or another government number.
- Cities are fictional, and links use the reserved `.example` domain (RFC 2606).
- Names are random combinations of common given names and surnames. Any resemblance to a real
  person is coincidental.
- The specimen card is a generic layout labelled *"SPECIMEN - FICTIONAL DATA - NOT AN IDENTITY
  DOCUMENT"*. It does not imitate any official document.

### About the text matching

*Text matching demonstration — not identity verification.*

The matcher folds accents and case, splits the expected name into words, and reports which whole
words appear in the OCR output. A full match only means the OCR engine recognized those words in
an image the app generated itself. It does **not** show that a document is genuine or unaltered,
or that it belongs to the person presenting it. The app makes no claims about OCR accuracy;
accuracy has not been measured yet.

## Planned work (not implemented)

Later modernization phases are expected to add the following. **None of it exists yet.**

- a reproducible OCR evaluation harness: preprocessing ablations, engine comparisons, and
  name-matching error rates on synthetic documents;
- further hardening of the public demo (for example, rate limiting).

## Architecture

The app is a small modular monolith: one Streamlit process and one package in `src/know_your_fan/`.
Presentation (`app.py`) is separate from workflows (`services.py`) and from the domain and
infrastructure modules.

- [docs/architecture.md](docs/architecture.md): modules, workflows, data and OCR flows, error handling, testing strategy
- [docs/threat-model.md](docs/threat-model.md): STRIDE analysis, mitigations, residual risks
- [docs/decisions/](docs/decisions/): architecture decision records

```
main.py                     Streamlit entry point
src/know_your_fan/
  app.py                    Streamlit pages (presentation only)
  services.py               Workflows: seeding, filtering, OCR + matching
  config.py                 Settings from environment variables
  synthetic.py              Deterministic generator and synthetic-data allowlist
  storage.py                SQLite repository (synthetic profiles only)
  ocr.py                    Specimen rendering, preprocessing, Tesseract wrapper
  text_matching.py          Accent-insensitive whole-word name matching
  models.py                 FanProfile dataclass
tests/unit/, tests/integration/
docs/                       Architecture, threat model, ADRs
pyproject.toml, uv.lock     Packaging, dependencies, tool configuration
requirements.txt            Generated from uv.lock for pip-only hosts
packages.txt, Dockerfile    Tesseract system dependency
```

## Requirements

- **Python 3.13** (`requires-python = ">=3.13"`; CI tests 3.13 only).
- **[uv](https://docs.astral.sh/uv/)** for development. Running the app also works with plain pip.
- **Tesseract OCR 5.x** (a system program, not a Python package) with English and Portuguese language
  data. Only the text-matching page needs it. Without it, the other pages work normally and the
  text-matching page shows an "OCR is unavailable" message.

| OS | Install Tesseract |
|---|---|
| Debian / Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng` |
| macOS (Homebrew) | `brew install tesseract tesseract-lang` |
| Windows | Install the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki), select *Portuguese* under additional language data, and add the install folder to `PATH`. |
| Any OS with Docker | Use the provided `Dockerfile` (see below); it includes Tesseract and the language data. |

Check the installation with `tesseract --list-langs`; the output should include `eng` and `por`.
CI tests the Tesseract 5.x packages from Ubuntu 24.04 and, through Docker, Debian 13. The Windows
and macOS installs are documented but not tested in CI.

## Running locally

With uv (recommended):

```bash
git clone https://github.com/CaioVenxncio/know-your-fan-app.git
cd know-your-fan-app
uv sync --locked            # creates .venv from uv.lock, including dev tools
uv run streamlit run main.py
```

With pip only:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run main.py
```

With Docker (includes Tesseract):

```bash
docker build -t know-your-fan .
docker run --rm -p 8501:8501 know-your-fan
```

Then open http://localhost:8501. On first start the app creates a local SQLite file at
`.data/kyf_demo.db` and seeds it with 25 fictional profiles. Set `KYF_DB_PATH` to use another
location. Database files are ignored by Git.

## Development

| Task | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` (check only: `--check`) |
| Type-check (strict) | `uv run mypy` |
| Tests | `uv run pytest` |
| Tests with coverage | `uv run pytest --cov` (fails below 90%) |
| Non-UI coverage | `uv run coverage report --omit=src/know_your_fan/app.py --fail-under=90` |
| Dependency audit | `uv run pip-audit --skip-editable` |
| Pre-commit hooks | `uv run pre-commit install`, then `uv run pre-commit run --all-files` |
| Update dependencies | `uv lock --upgrade`, then regenerate `requirements.txt` with the `uv export` command in its header |

The end-to-end OCR tests (`tests/integration/test_ocr_e2e.py`) run the real Tesseract engine.
They are skipped locally when Tesseract is not installed. Setting `KYF_REQUIRE_OCR=1` makes a
missing engine fail the run instead, which is how CI runs them.

## Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes to the development branch, on pull
requests to `main`, and on manual dispatch. It has four jobs:

- **quality:**
  - install from `uv.lock`, and check that `requirements.txt` matches it;
  - Ruff lint and format check, and mypy;
  - real-Tesseract OCR tests (which must not skip), and the full test suite;
  - coverage thresholds.
- **dependency-audit:** `pip-audit` on the locked environment.
- **secret-scan:** gitleaks on the full Git history (the binary's checksum is verified).
- **docker:** builds the image, checks it runs as non-root, runs real OCR inside it, and checks
  that the app reports healthy.

Actions are pinned to commit SHAs, and the workflow token is read-only. There is no deployment
workflow.

## Security and privacy design

These measures limit risk for a public demo. They are not a formal security audit, and the
project is not production software.

- There is no authentication, because nothing private is stored: the only stored data is
  generated by the app itself.
- There are no file uploads. OCR runs only on images the app renders from synthetic profiles.
- The only free-text inputs (search box, expected name) are length-limited and never stored.
- Stored profiles must pass an allowlist (every value comes from the generator), and the dataset is capped at 500 profiles.
- User-visible values are rendered as plain text, never as Markdown or HTML.

See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md) and the [threat model](docs/threat-model.md).

## Known limitations

- Name matching is a simple whole-word check with no tuned threshold. It does not tolerate OCR
  character errors. For example, in CI, Ubuntu 24.04's Tesseract 5.3.4 reads the "ç" on one card as
  "g", so "Gonçalves" is reported as missing.
- OCR accuracy has not been measured and depends on the installed Tesseract version and language data.
- The degradations (blur, rotation) are illustrative, not a realistic capture model.
- The local SQLite file isn't persistent on hosts with temporary filesystems. The demo reseeds itself,
  so only profiles added through the generator would be lost.
- There is no rate limiting. Writes are bounded only by the 500-profile cap.

## History

Before Phase 1, the repository collected personal data in real formats (such as CPF numbers), stored it in SQLite, and
protected an admin view with a password that was hardcoded and published. That workflow has been
removed. The old password must be considered compromised and must never be reused. Git history
is preserved unchanged.

## License

Know Your Fan is released under the [MIT License](LICENSE). Copyright (c) 2026 Caio Venancio.

The MIT License covers this project's own source code and documentation only. Third-party
software keeps its own license, including:

| Component | How it is used | License |
|---|---|---|
| Streamlit | Python dependency | Apache-2.0 |
| Pillow | Python dependency | MIT-CMU |
| pytesseract | Python dependency | Apache-2.0 |
| Tesseract OCR and its language data | System program, installed separately | Apache-2.0 |
| Ruff, mypy, pytest, pytest-cov, pip-audit, pre-commit | Development dependencies | MIT or Apache-2.0 |
| Aileron Regular font (`src/know_your_fan/assets/fonts/`) | Bundled, unmodified; draws the specimen cards | CC0 1.0 (public domain dedication) |

The font is the only third-party file stored in this repository. Its source and checksum are
recorded in [`assets/fonts/README.md`](src/know_your_fan/assets/fonts/README.md). No third-party
source code, images, or logos are included.

Game titles that appear in synthetic profiles are trademarks of their respective owners. They are used only to describe
fan interests and do not imply affiliation or endorsement.
