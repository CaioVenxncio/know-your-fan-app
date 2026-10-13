# Deployment: Streamlit Community Cloud

**Nothing has been deployed.** There is no public URL, and no hosting account is connected by this
project. Creating a deployment, and making it public, each need the owner's explicit approval.

**Prepared:** 2026-10-13, on branch `deploy/community-cloud-prep`.

**Labels:**
- **Verified:** checked locally or in CI.
- **Docs:** stated in Streamlit's current documentation, not tested on the platform.
- **Observed:** seen in responses from a public Community Cloud app (not this app).
- **Not verified:** can only be checked on a deployment.

## Platform facts

| Topic | Fact | Source |
|---|---|---|
| Operating system | Debian 11 ("bullseye") | Docs |
| Python | Chosen at deploy time under *Advanced settings*. The default is **3.12**; this app needs **3.13** (`requires-python = ">=3.13"`) | Docs |
| Dependency file | The first one found, in this order: `uv.lock`, `Pipfile`, `environment.yml`, `requirements.txt`, `pyproject.toml`. For this repository that is **`uv.lock`**. Which uv dependency groups get installed is not documented | Docs |
| System packages | `packages.txt` at the repository root, installed with apt | Docs |
| Working directory | Apps start from the repository root | Docs |
| Enforced configuration | Overrides `.streamlit/config.toml`: `client.showErrorDetails = false`, `runner.fastReruns = true`, `server.runOnSave = true`, `server.enableXsrfProtection = true`, `browser.gatherUsageStats = true` | Docs |
| Resources (documented as of Feb 2024; "may change without notice") | CPU 0.078–2 cores, memory 690 MB–2.7 GB, storage up to 50 GB. Apps sleep after 12 hours without traffic | Docs |
| Sharing | An app from a **public** repository is **public by default**. A developer can make it private ("Only specific people can view this app") **after** it is deployed. One private app per account | Docs |
| Secrets | Pasted in TOML under *Advanced settings*; top-level keys are also exposed as environment variables. This app needs none | Docs |
| HTTPS | `*.streamlit.app` is served over HTTPS; plain HTTP redirects. The `.app` top-level domain is on browsers' HSTS preload list | Observed |
| Response headers | `X-Content-Type-Options: nosniff` present. No `Content-Security-Policy`, `X-Frame-Options`, or `Strict-Transport-Security` header | Observed (one public app, 2026-10-13) |
| Cookies | Platform cookies are HttpOnly, Secure, SameSite=Lax: session, CSRF, and a ~31-day `proxy-tracking-id` | Observed |

## How this repository fits

| Requirement | Status | Evidence |
|---|---|---|
| Entry point | `main.py` at the root; adds `src/` to the import path if the package is not installed | Verified (CI, Docker, local) |
| Python 3.13 | Must be selected manually (default 3.12 would fail `requires-python`) | Docs; failure mode inferred |
| Install from `uv.lock` on Debian 11 | `uv sync --locked` succeeds in a Debian 11 container (CI job `cloud-parity`). It installs the `dev` and `research` groups too, which is heavier but harmless | Verified in a container; the platform's exact installer is not verified |
| Tesseract from `packages.txt` | Debian 11 provides **Tesseract 4.1.1** with `por` and `eng` data, older than the 5.x used in the study and in the other CI jobs. All real-OCR tests pass with it in CI: clean-card name recall, absent-name check, service pipeline with rule M1, research smoke run | Verified in a container |
| Executable and language data discovery | apt installs `tesseract` on `PATH` and its data in the default location; no `TESSDATA_PREFIX` or code change is needed | Verified in a container |
| apt mirror for Debian 11 | Debian 11 is end-of-life. The main archive still serves the Tesseract packages, but security-update files return 404 on `deb.debian.org` (CI uses `archive.debian.org`). Whether the platform's mirror is affected is **not verified** | Verified (CI log), platform not verified |
| Error details | Community Cloud's `showErrorDetails = false` means "stacktrace" in Streamlit 1.65. The app now catches every unexpected error itself and shows a fixed message, so no trace or path reaches visitors | Verified (test with the enforced value) |
| Enforced configuration | The app starts, and every page works, with all five enforced values (CI start-up check; local browser walk) | Verified locally and in a container |
| Research assets | Committed JSON and figures, resolved from the repository root; the page runs no OCR | Verified (tests, Docker) |
| Memory | About 155 MB working set and 285 MB private memory after a full browser walk (Windows), plus short-lived Tesseract processes. Below the documented 690 MB minimum | Measured locally; platform not verified |
| CPU | Clean-card OCR takes about 0.46 s on a CI runner. At the documented minimum of 0.078 cores it could be several times slower; the 15 s timeout and 2-job limit still bound it | Platform not verified |
| SQLite | Created at `.data/kyf_demo.db` under the repository root, shared by all sessions of the app process. Lost on restart, redeploy, or sleep; the app reseeds 25 profiles. If the directory were not writable, the Fans and OCR pages would show "dataset unavailable" (tested). Fix: set `KYF_DB_PATH = "/tmp/kyf_demo.db"` as a top-level secret | Behaviour verified locally; writability not verified |
| Credentials | None required; no secrets file exists or is needed | Verified |

## Security and privacy on the platform

- **Usage statistics cannot be turned off.** The platform enforces them, and the Streamlit page in
  the browser then contacts Streamlit's telemetry (`data.streamlit.io`, `webhooks.fivetran.com` in
  a local test with the same setting). PRIVACY.md says so.
- **Clickjacking:** no `X-Frame-Options` or CSP `frame-ancestors` header was observed, and the app
  cannot set response headers. Risk is low: the app has no accounts, and the only state change is
  adding a fictional profile. Accepted, with no workaround.
- **MIME sniffing:** `nosniff` was observed.
- **CSRF:** the platform enforces Streamlit's XSRF protection.
- **HTTPS:** observed.
- **Isolation between apps:** this is the platform's responsibility and cannot be tested by this
  project.

## Private test deployment: limitation

A private test is not possible without either a public window or a new repository:

- This repository is public, so a new app starts **public**.
- The documentation describes making an app private only after it is deployed.

| Option | What it involves | Trade-off |
|---|---|---|
| A. Private mirror repository | The owner creates a separate **private** GitHub repository with the same code and deploys from it, so the app starts private (developers only). | No public window. Requires a second repository, and granting Streamlit the broad GitHub `repo` OAuth scope, which the docs note is more than Streamlit needs. |
| B. Deploy, then restrict immediately | Deploy from this repository and switch sharing to "Only specific people" as soon as the app exists. | The app is public for the minutes it takes to build, under an unannounced URL. It is still a public deployment, so it needs explicit approval. |
| C. No hosted test | Rely on the Debian 11 parity job and the local test with the enforced configuration, then go live directly when approved. | Platform-only items (mirror, CPU, headers on this app, writability) are checked live. |

## Steps, once approved

1. Merge the deployment PR, if approved.
2. At share.streamlit.io, choose **Create app**, then **Yup, I have an app**. Enter:
   - repository `CaioVenxncio/know-your-fan-app` (or the private mirror for option A);
   - branch `main`;
   - file `main.py`.

   Optionally choose a custom subdomain.
3. Under **Advanced settings**, set Python version **3.13** and leave **Secrets empty**. Only if
   the SQLite check in step 5 fails, add `KYF_DB_PATH = "/tmp/kyf_demo.db"`.
4. Deploy. For option B, switch Sharing to "Only specific people can view this app" as soon as
   the app page exists.
5. Check the build log (download it from **Manage app**):
   - the dependency file used;
   - the Python version;
   - that `tesseract-ocr`, `tesseract-ocr-por`, and `tesseract-ocr-eng` were installed;
   - no apt 404 errors.
6. Validate (see below), then make the app public only with approval.

## Post-deployment validation checklist

Run against the app URL, with the owner's authorisation and bounded tests only:

- every page loads;
- profiles browse and generate;
- the OCR demo returns a match on a clean card;
- the 6th OCR run within a minute shows the rate-limit message;
- the Research tabs, charts, and tables render, and the Home card shows 19,200 runs;
- no stack trace appears anywhere;
- the axe-core scan and console check from Phase 6, at 1440 px and 390 px;
- response headers and cookies (`curl -sI`);
- request origins (expect the app, the platform, and Streamlit telemetry only);
- reboot the app and confirm it reseeds.

For a private app, the browser checks need a signed-in viewer session, so the owner runs them or
shares a session. Credentials must not be shared in chat.

## Rollback

- **Bad release:** revert the offending commit on `main` with a new commit (no history rewrite);
  the platform redeploys from the branch.
- **Abuse or unexpected behaviour:** make the app private, or stop or delete it, in the dashboard.
  All data is synthetic and recreated on start.
