# Security Policy

## Scope

Know Your Fan is a **synthetic-data-only demonstration**. It does not collect personal data,
accept file uploads, or provide authentication. It is not an identity-verification or
document-authentication system and must not be used as one.

## Supported versions

Only the latest commit on `main` is maintained.

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/CaioVenxncio/know-your-fan-app/security/advisories/new)
rather than in a public issue. Include steps to reproduce and the affected commit. You should
receive an acknowledgement within 7 days.

Please do **not** include real personal data in reports.

## Security design

- **No secrets in code.** The app needs no credentials. The admin password used before Phase 1
  appears in Git history; it is considered compromised and must never be reused.
- **No real personal data.** Public workflows offer no fields for CPF, identity documents,
  addresses, or passwords, and no file upload widget.
- **Write path restricted to synthetic records.** The repository rejects any record without a
  `KYF-DEMO-` identifier and caps the dataset at 500 profiles.
- **Safe rendering.** Values are shown with plain-text widgets, never interpolated into
  Markdown or HTML.
- **Bounded OCR.** Images are limited to 4 megapixels, and Tesseract runs with a 15-second timeout.
  Failures produce friendly messages instead of stack traces (`client.showErrorDetails = "none"`).
- **Parameterized SQL.** All queries use bound parameters, and each connection is short-lived.
- **Repository hygiene.** Databases, environment files, Streamlit secrets and Python caches are
  ignored by Git.

## Known gaps

- There is no automated dependency or secret scanning in CI yet (planned for Phase 2).
- The app does no rate limiting. Generator writes are capped by dataset size only.
