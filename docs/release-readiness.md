# Release readiness (Phase 6)

> **Status update:** the app has since been merged and deployed on Streamlit Community Cloud
> (https://know-your-fan-app.streamlit.app); see [deployment.md](deployment.md). The assessment below is the Phase 6 snapshot.

**Assessed:** 2026-10-13, on branch `phase-1/security-privacy-foundation`.

**Code under review:** commit `da6c1ac`. The commit that adds this document changes documentation
only.

**Statuses:**
- **PASS:** verified, evidence given.
- **PASS WITH LIMITATIONS:** verified, with stated gaps.
- **BLOCKED:** a release must not happen until this is resolved.
- **NOT VERIFIED:** could not be checked.

**Overall: ready for the owner's integration decision.** There are no release blockers for
merging into `main`. A public deployment has open NOT VERIFIED items that can only be checked by
deploying (see [deployment.md](deployment.md)). Merging, releasing, and deploying all need
separate approval.

## Checklist

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Security audit | PASS WITH LIMITATIONS | [security-review.md](security-review.md): 0 critical, high, or medium findings; 4 low (2 fixed); 9 informational | Self-review, not an independent audit or penetration test |
| Secret scanning | PASS | gitleaks over all history: no leaks (local and CI). Current tree: no secrets in tracked files | The historical admin password (F1) is in history only. It is not detectable by gitleaks and is documented without its value |
| Privacy verification | PASS | Data lifecycle traced; no upload widgets (tested); only same-origin requests, one XSRF cookie, one theme entry in local storage (browser check); logs without user data (tests) | Hosting platforms can log connection metadata; stated in PRIVACY.md |
| Dependency audit | PASS | `uv lock --check` OK; pip-audit: no known vulnerabilities; direct dependencies at latest versions; runtime licences permissive (MPL-2.0 for certifi, unmodified) | Results reflect the advisory databases on the date of the check |
| GitHub Actions | PASS | Run [38412632281](https://github.com/CaioVenxncio/know-your-fan-app/actions/runs/38412632281) on `da6c1ac`: all 4 jobs and every step succeeded. Read-only token, SHA-pinned actions, no secrets, no `pull_request_target` | The weekly scheduled audit activates only after the workflow reaches `main` |
| Docker validation | PASS WITH LIMITATIONS | CI: build, non-root, Research data loads, no data/secrets/tests/tooling in the image, Tesseract languages, real OCR, health check | Docker is not installed on the development machine, so the image was validated in CI only. Base images are pinned by tag, not digest |
| Accessibility | PASS WITH LIMITATIONS | axe-core 4.13.0 on 23 page states at 1440 px and 390 px: 0 WCAG 2.2 A/AA violations after fixes (6 rule failures fixed). Keyboard walk with visible focus | One best-practice finding (`region`) comes from Streamlit's markup. No screen-reader, zoom, or forced-colour testing. Not a certification ([ux-accessibility.md](ux-accessibility.md)) |
| Functional testing | PASS | 413 tests pass with real Tesseract (coverage 97.75 %; non-UI 98 %). Browser walk at two widths: navigation, profile browse/generate, empty state, OCR match, rate-limit message after 3 runs (session limit 3), all Research tabs; missing-Tesseract instance shows "OCR is unavailable" without details | Console: 0 errors, 0 failed requests. Only link: the repository URL |
| Resource safeguards | PASS | `validate_limits.py --real-ocr` 6/6 OK locally and in CI; new sessions do not raise the process-wide limit; cap holds across separate processes (new test) | Per-process limits; replicas multiply them (documented) |
| Research integrity | PASS | `verify_research.py --reanalyse` on a clean export installed from `uv.lock`: config hashes, fingerprints, manifests, 19,200 runs, frozen selection, and E3 test-only with frozen strategies all match. `results.md`, `research_summary.json`, and all 6 figures byte-identical; explorer equal except re-measured matching latency. Also passes in CI | PNG byte-identity on Linux CI runners is not asserted (non-strict); values are |
| Frozen record unchanged | PASS | `git diff b8649f2 HEAD -- experiments docs/research` only adds `research_explorer.json` (Phase 5) | Historical metadata kept as is, by the owner's decision |
| Documentation | PASS | README overview, security review, deployment preparation, privacy statement, threat model, operations, accessibility updated; stale statements corrected | — |
| Deployment prerequisites | PASS WITH LIMITATIONS (updated during deployment preparation) | Community Cloud requirements checked against current documentation; Debian 11 parity CI job passes (Tesseract 4.1.1, `uv.lock` install, real OCR tests, limits, start-up under the enforced configuration); error traces are suppressed even with the platform's `showErrorDetails = false` | Not verified on the platform: apt mirror, CPU, response headers of this app, writable `.data/`. See [deployment.md](deployment.md) |
| Main branch | PASS | `main` = `origin/main` = `e9224c9`, unchanged | — |

## Release blockers

None for integration into `main`.

**Before a public deployment** (not blockers for the merge):
1. A private test deployment to check the NOT VERIFIED items in deployment.md.
2. A decision on browser security headers (F3), which depend on the hosting platform.

## Known limitations carried into the release

- OCR and matching results apply to synthetic cards and one engine version. Nothing here is
  identity verification.
- Rate and concurrency limits are per process, and per-session limits can be bypassed (the
  process-wide limits still hold).
- The SQLite demo dataset is not persistent on ephemeral hosts; it reseeds itself.
- The accessibility evidence is automated plus keyboard checks only.
- The historical password and the original database schema remain in Git history.

## Rollback considerations

- **Merge:** the integration is a single PR. A problem found afterwards is fixed with a revert
  commit on `main`; history is not rewritten.
- **Deployment:** stop or delete the app in the hosting dashboard. All data is synthetic and
  recreated on start, so there is nothing to back up or restore.

## Optional improvements (not blockers)

- Pin Docker base images by digest and refresh them on a schedule.
- Add a screen-reader pass and a 400 % zoom check.
- Run the axe-core scan in CI (it needs a browser in the workflow).
- Enable GitHub private vulnerability reporting and secret scanning in the repository settings
  (owner's decision).
- A second OCR engine study (future research).
