# Security and privacy review (Phase 6)

**Date:** 2026-10-13. **Baseline:** commit `96ccf07`, compared with `main` (`e9224c9`): 28 commits, 103 files.

**Reviewer:** the project maintainer, with an AI coding assistant. This is not an independent audit
or a penetration test. Testing used local instances only and small, bounded, synthetic workloads.
No external system was tested.

Severity scale: CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL. **No CRITICAL, HIGH, or MEDIUM findings
were identified.** That does not mean the application cannot be compromised.

## Scope and method

| Area | What was done |
|---|---|
| Source and configuration | Read the app, storage, OCR, limits, config, logging, research and UI modules, the scripts, Streamlit config, Dockerfile, `.dockerignore`, `.gitignore`, and the workflow |
| Secrets | gitleaks 8.30.1 (checksum-verified) over all reachable history (31 commits) and over the working tree, with `--redact` |
| Historical credential | Searched every reachable commit for the pre-Phase-1 admin password, printing only its length and the files that contain it |
| Personal data | Searched tracked files for e-mail addresses, home-directory paths, and CPF-like patterns. Inspected the historical database file's schema, row count, and raw pages |
| Application | Ran the app with real Tesseract in headless Chromium. Probed HTTP paths; recorded cookies, browser storage, and every request origin; triggered the rate-limit and "OCR unavailable" paths |
| Resource safeguards | `scripts/validate_limits.py --real-ocr`, plus a new test with writers in separate processes |
| Dependencies | `uv lock --check`, pip-audit, outdated check, and licence metadata for all 38 runtime packages |
| Research record | `scripts/verify_research.py --reanalyse` on a clean export of `HEAD` installed from `uv.lock` |

## Findings

| ID | Severity | Component | Finding | Status |
|---|---|---|---|---|
| F1 | LOW | Git history | The pre-Phase-1 admin password is in Git history (`main.py`, `README.md`, and a committed `.pyc` in the three original commits on `main`). gitleaks does not flag it because it is a plain string comparison | Documented. Not used by any current file or configuration (verified: 0 tracked files contain it). History not rewritten |
| F2 | LOW | Profile writes | Only a per-session write limit existed. Opening new sessions resets it, so many sessions could fill the shared dataset to its cap within seconds | **Fixed:** process-wide limit of 60 per 10 min, with a test |
| F3 | LOW | HTTP responses | Streamlit sends no `Content-Security-Policy`, `X-Frame-Options`, or `X-Content-Type-Options` headers, so the app can be framed by other sites | Open. Needs the host or a reverse proxy (see [deployment.md](deployment.md)). Impact is limited: no accounts, and the only state change is adding a synthetic profile |
| F4 | LOW | Research reproducibility | `research_summary.json` key order depended on `PYTHONHASHSEED` because a `set` was iterated, so regeneration was not byte-identical (values were identical) | **Fixed.** Byte-identical under four hash seeds; checked in CI |
| F5 | INFO | UI helpers | `ui.eyebrow`, `hero`, and `step` interpolated their arguments into HTML without escaping. All current callers pass static strings, so nothing was exposed | **Fixed** (defence in depth): arguments are escaped; a test blocks raw HTML outside `ui.py` |
| F6 | INFO | Historical data | `fans.db` on `main` has the original schema, including CPF and address columns | Verified harmless: 0 rows, 2 pages, empty freelist, no CPF-like or e-mail-like bytes |
| F7 | INFO | Frozen research metadata | The four `run_metadata.json` files record the local tessdata path, which includes a generic Windows account name. No hostname, MAC address, or other unique identifier is recorded; the CPU field is a model string | Kept unchanged by the owner's decision (provenance). Runs since Phase 5 record `~/...` |
| F8 | INFO | Streamlit endpoints | `/_stcore/health`, `/_stcore/host-config` (allowed embedding origins), and `/_stcore/metrics` (cache memory statistics) are public. Requests for repository paths such as `main.py`, `.streamlit/config.toml`, or `.data/*.db` return the app's HTML shell, not the files | Accepted. Nothing sensitive is exposed |
| F9 | INFO | Local development | Streamlit listens on all interfaces by default and prints LAN and public addresses on start-up | README now recommends `--server.address localhost` for local runs |
| F10 | INFO | Docker | Base images are referenced by tag (`python:3.13-slim-trixie`, `uv:0.13.0`), not by digest, so rebuilds are not bit-for-bit reproducible | Accepted trade-off: tags pick up security updates. Pin digests if exact rebuilds are needed |
| F11 | INFO | Error handling | `_run_ocr` maps known OCR and limit errors to messages. An unexpected `OSError` (for example from temporary files) would reach Streamlit, which shows a generic error without details (`showErrorDetails = "none"`) | Accepted |
| F12 | INFO | Working-tree scan | gitleaks reports 216 `generic-api-key` matches, all inside the untracked local `.venv` (third-party package files) | Not tracked, not in the image. No action |
| F13 | INFO | Hosting | On Streamlit Community Cloud, `uv.lock` takes priority over `requirements.txt`. The documentation does not say which dependency groups are installed, so the development tools may be installed | NOT VERIFIED; listed as a deployment prerequisite |

## Area summaries

**Secrets.**
- gitleaks found no leaks in history.
- There is no `.env` file and no `.streamlit/secrets.toml`, and the app needs no credentials.
- `.gitignore` covers databases, environment files, Streamlit secrets, keys, caches, and derived
  research files.
- No credentials were rotated or revoked. If the old password (F1) was ever reused anywhere else,
  the owner must change it there.

**Privacy.** The data lifecycle was traced end to end:
- **Generation:** a seeded generator with allowlisted vocabularies.
- **Input:** two length-limited text fields; no uploads (tested).
- **Processing:** in memory per session.
- **Persistence:** SQLite, allowlist enforced before every write.
- **OCR:** on app-rendered images only.
- **Logging:** fixed messages and error codes (tested).
- **Errors:** fixed messages.
- **Research:** synthetic names and card text only.
- **Visualization:** precomputed aggregates.
- **Container:** no data files in the image (checked in CI).

In the browser, every request went to the app's own origin. The app sets one XSRF cookie and one
theme entry in local storage. PRIVACY.md now says this, and that hosting platforms can log
connection metadata.

**Streamlit.**
- Per-session state is isolated by Streamlit. The shared runtime (`st.cache_resource`) holds
  limits and storage only.
- `st.cache_data` returns copies, so sessions cannot change each other's research data.
- Error details are hidden, the toolbar is minimal, and usage statistics are off.
- There is no admin, debug, or upload feature.
- Raw HTML is static and escaped (F5).

**OCR safeguards.** Measured with real Tesseract:

| Check | Result |
|---|---|
| Sessions vs the process-wide limit | 50 requests from 10 sessions: 25 accepted. New sessions did not raise the process-wide total |
| Concurrency (8 simultaneous requests, capacity 2) | Never more than 2 running at once; 6 rejected as busy |
| Recovery after 4 forced timeouts | 0 slots held, 0 Tesseract temporary files left, next request succeeded |
| Browser, session limit set to 3 | The 4th request showed the rate-limit message, at desktop and phone widths |

**SQLite.**
- All statements use bound parameters.
- Writes run in `BEGIN IMMEDIATE`.
- 200 concurrent threaded writes against a cap of 100 added exactly 100 rows.
- 4 separate processes writing 60 profiles against a cap of 25 added exactly 25 (new test).
- The file is created with the process umask and holds synthetic data only. It is not persistent
  on ephemeral hosts; the app reseeds itself.

**Dependencies.**
- The lockfile is consistent (`uv lock --check`).
- pip-audit: no known vulnerabilities on 2026-10-13.
- All direct dependencies are at their latest versions.
- Runtime licences are permissive: MIT, BSD, Apache-2.0, PSF, and MPL-2.0 for certifi, which is
  used unmodified.
- No dependency needs private credentials.
- Remaining risk: trust in PyPI and upstream maintainers, and the time between lock refreshes.

**GitHub Actions.**
- The token is read-only (`contents: read`), and no job raises it.
- Pull requests use the `pull_request` event, not `pull_request_target`, and no secrets are used.
- Checkout does not keep credentials. Third-party actions are pinned to commit SHAs, and the
  gitleaks binary is checksum-verified.
- No artifacts are uploaded. Logs show tool output and synthetic test data only.
- The weekly audit takes effect only after the workflow reaches the default branch.

**Docker.**
- Maintained Debian 13 slim base, with only the Tesseract packages added.
- Runs as non-root (UID 10001); only `/app/.data` is writable.
- No credentials. One exposed port (8501). Health check uses `/_stcore/health`.
- CI checks that the image has no databases, environment files, secrets, CSV data, tests,
  scripts, or `.git`, and exactly the two Research data files.
- Docker is not installed on the review machine, so image checks ran in CI only.

## Remediation that needs the owner's approval (not done)

- **Rewriting history** to remove F1 and the historical `fans.db` and `.pyc`. This is destructive,
  would rewrite `main` and every clone, and cannot remove copies that already exist elsewhere.
  Not recommended: the password protects nothing today. Rotating it wherever it might have been
  reused is the effective remedy.
- **Sanitising the frozen research metadata (F7).** The owner's default is to keep it.
- **GitHub repository settings** (private vulnerability reporting, secret scanning, branch
  protection) were not changed.
