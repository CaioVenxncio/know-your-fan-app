# Security Policy

## Scope

Know Your Fan is an independent, **synthetic-data-only demonstration**. It does not collect personal data,
accept file uploads, or provide authentication. It is not an identity-verification,
document-authentication, or fraud-detection system and must not be used as one. It has not had
an independent security audit and is not production software. The maintainer's own Phase 6
review is in [docs/security-review.md](docs/security-review.md).

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
  Markdown or HTML. Static HTML snippets exist only in `ui.py` and escape their text; a test
  enforces both rules.
- **Bounded OCR.** Images are limited to 4 megapixels, and Tesseract runs with a 15-second timeout.
  Failures produce friendly messages instead of stack traces (`client.showErrorDetails = "none"`).
- **Parameterized SQL.** All queries use bound parameters, and each connection is short-lived.
- **Repository hygiene.** Databases, environment files, Streamlit secrets and Python caches are
  ignored by Git.
- **Automated checks.** On every push to the development branch, CI runs `pip-audit` on the
  locked dependencies and gitleaks on the full Git history. GitHub Actions are pinned to commit
  SHAs and run with a read-only token. Pre-commit runs gitleaks before each local commit.
- **Container.** The optional Docker image runs as a non-root user, and CI checks that it
  contains no databases, environment files, secrets, tests, or tooling.
- **Resource limits.** OCR requests are rate-limited (per session and per process) and limited to
  2 concurrent jobs per process; Tesseract runs with one thread per process. Profile writes are
  rate-limited per session and per process, and the dataset cap is enforced in SQLite
  transactions (tested with writers in separate processes). See
  [docs/operations.md](docs/operations.md).
- **Privacy-safe logging.** Logs contain event types and error codes only.

The full analysis is in [docs/threat-model.md](docs/threat-model.md).

## Known gaps

- Limits are enforced per process and per browser session, not per client IP. Several replicas
  multiply the limits, and new sessions bypass the per-session limits.
- The weekly scheduled dependency audit activates only once the workflow reaches the default
  branch; until then, audits run on every push.
- Streamlit does not send security headers such as `Content-Security-Policy` or
  `X-Frame-Options`. A hosting platform or reverse proxy should add them.
- Hosted behaviour (for example on Streamlit Community Cloud) has not been verified, because
  nothing has been deployed.
