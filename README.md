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

- packaging metadata (`pyproject.toml`, lockfile), continuous integration, linting and type checking;
- a reproducible OCR evaluation harness: preprocessing ablations, engine comparisons, and
  name-matching error rates on synthetic documents;
- containerized local execution.

## Requirements

- **Python 3.13.** This is the version used for testing; other recent versions may work but are untested.
- **Tesseract OCR** (a system program, not a Python package) with English and Portuguese language
  data. Only the text-matching page needs it. Without it, the other pages work normally and the text-matching
  page shows an "OCR is unavailable" message.

| OS | Install Tesseract |
|---|---|
| Debian / Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-por` |
| macOS (Homebrew) | `brew install tesseract tesseract-lang` |
| Windows | Install the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki), select *Portuguese* under additional language data, and add the install folder to `PATH`. |

Check the installation with `tesseract --list-langs`; the output should include `eng` and `por`.
`packages.txt` lists the same system packages for Debian-based hosts such as Streamlit Community
Cloud. No public deployment exists at present.

## Running locally

```bash
git clone https://github.com/CaioVenxncio/know-your-fan-app.git
cd know-your-fan-app
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run main.py
```

Then open http://localhost:8501.

On first start the app creates a local SQLite file at `.data/kyf_demo.db` and seeds it with 25
fictional profiles. Set the `KYF_DB_PATH` environment variable to use a different location.
Database files are ignored by Git.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers the synthetic generator, storage, text matching, OCR error handling, and the
Streamlit pages (via `streamlit.testing`). The end-to-end OCR test is skipped automatically
when Tesseract is not installed. There is no continuous integration yet.

## Project layout

```
main.py                     Streamlit entry point
know_your_fan/
  app.py                    Streamlit pages
  synthetic.py              Deterministic fictional-profile generator
  storage.py                SQLite repository (synthetic profiles only)
  ocr.py                    Specimen rendering, preprocessing, Tesseract wrapper
  text_matching.py          Accent-insensitive whole-word name matching
  models.py                 FanProfile dataclass
tests/                      pytest suite
.streamlit/config.toml      Hides error details from visitors, disables usage stats
packages.txt                Tesseract system packages for Debian-based hosts
```

## Security and privacy design

These measures limit risk for a public demo. They are not a formal security audit, and the
project is not production software.

- There is no authentication, because nothing private is stored: the only stored data is
  generated by the app itself.
- There are no file uploads. OCR runs only on images the app renders from synthetic profiles.
- The only free-text inputs (search box, expected name) are length-limited and never stored.
- Stored records must carry a synthetic `KYF-DEMO-` identifier, and the dataset is capped at 500 profiles.
- User-visible values are rendered as plain text, never as Markdown or HTML.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).

## Known limitations

- Name matching is a simple whole-word check. It does not handle OCR character errors (for example
  `0` read instead of `O`) and has no tuned threshold.
- OCR accuracy has not been measured and depends on the installed Tesseract version and language data.
- The degradations (blur, rotation) are illustrative, not a realistic capture model.
- The local SQLite file isn't persistent on hosts with temporary filesystems. The demo reseeds itself,
  so only profiles added through the generator would be lost.
- There is no rate limiting. Writes are bounded only by the 500-profile cap.
- There is no continuous integration yet. Tests run locally.

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
| pytest | Development dependency | MIT |

Specimen cards are drawn with the default font bundled in Pillow (Aileron Regular). No third-party
source code, fonts, images, or logos are stored in this repository.

Game titles that appear in synthetic profiles are trademarks of their respective owners. They are used only to describe
fan interests and do not imply affiliation or endorsement.
