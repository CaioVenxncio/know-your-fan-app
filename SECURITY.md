# Security Policy

## Scope

Know Your Fan is an independent, **synthetic-data-only demonstration**. It does not collect personal data,
accept file uploads, or provide authentication. It is not an identity-verification,
document-authentication, or fraud-detection system and must not be used as one. It has not had
a formal security audit and is not production software.

## Supported versions

Only the latest commit on `main` is maintained.

## Reporting a vulnerability

Please report security issues privately rather than in a public issue:

1. Use [GitHub's private vulnerability reporting](https://github.com/CaioVenxncio/know-your-fan-app/security/advisories/new)
   if it is available for this repository.
2. Otherwise, open a public issue titled "Security contact request" **without any vulnerability
   details**, and the maintainer will arrange a private channel.

Include steps to reproduce and the affected commit. The maintainer aims to acknowledge reports
within 7 days, on a best-effort basis.

Please do **not** include real personal data in reports.

## Security design

- **No secrets in code.** The app needs no credentials. The admin password used before Phase 1
  appears in Git history; it is considered compromised and must never be reused.
- **No real personal data.** Public workflows offer no fields for CPF, identity documents,
  addresses, or passwords, and no file upload widget.
- **Write path restricted to synthetic records.** The repository accepts a profile only if every
  value comes from the generator's own vocabulary (an allowlist), and caps the dataset at 500 profiles.
- **Safe rendering.** Values are shown with plain-text widgets, never interpolated into
  Markdown or HTML.
- **Bounded OCR.** Images are limited to 4 megapixels, and Tesseract runs with a 15-second timeout.
  Failures produce friendly messages instead of stack traces (`client.showErrorDetails = "none"`).
- **Parameterized SQL.** All queries use bound parameters, and each connection is short-lived.
- **Repository hygiene.** Databases, environment files, Streamlit secrets and Python caches are
  ignored by Git.
- **Automated checks.** On every push to the development branch, CI runs `pip-audit` on the
  locked dependencies and gitleaks on the full Git history. GitHub Actions are pinned to commit
  SHAs and run with a read-only token. Pre-commit runs gitleaks before each local commit.
- **Container.** The optional Docker image runs as a non-root user.

The full analysis is in [docs/threat-model.md](docs/threat-model.md).

## Known gaps

- The app does no rate limiting. OCR requests are bounded per request (image size, 15-second
  timeout) but not per visitor.
- Dependency audits run only when CI runs; there are no scheduled audits yet.
