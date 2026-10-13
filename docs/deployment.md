# Deployment preparation: Streamlit Community Cloud

**Nothing has been deployed.** No hosting account is connected, and there is no public URL.
Deploying needs the owner's explicit approval. This page lists what the repository already
provides, what has not been verified, and the steps to follow once deployment is approved.

## What the repository provides

| Requirement | Provided by | Verified locally or in CI |
|---|---|---|
| Entry point | `main.py` at the repository root. It falls back to adding `src/` to the import path when the package is not installed | Yes (CI, Docker, local) |
| Python version | `requires-python = ">=3.13"`. Community Cloud lets you choose the version when deploying: choose **3.13** | 3.13 only (CI and local) |
| Python dependencies | `uv.lock` (exact versions and hashes) and `requirements.txt` (generated from it; CI checks they agree) | Yes |
| System packages | `packages.txt`: `tesseract-ocr`, `tesseract-ocr-por`, `tesseract-ocr-eng` | Equivalent apt packages tested on Ubuntu 24.04 (CI) and Debian 13 (Docker image) |
| Streamlit configuration | `.streamlit/config.toml`: error details hidden, usage statistics off, upload limit 1 MB, theme | Yes |
| Research page data | `experiments/results/research_explorer.json`, `research_summary.json`, `docs/research/figures/`, all committed. Paths resolve from the repository root | Yes (tests; Docker image check) |
| Credentials | None required. Do **not** add secrets | Yes |
| Start-up | Seeds 25 fictional profiles into `.data/kyf_demo.db` on first start. Invalid settings stop the app with a generic message | Yes |

## Not verified (cannot be checked without deploying)

| Item | Why it matters | What to check after a private test deployment |
|---|---|---|
| Dependency file used | Community Cloud uses the first file it finds, and `uv.lock` comes before `requirements.txt`. Which uv dependency groups it installs is not documented, so `dev` and `research` tools may be installed too | Read the build log. If dev tools are installed, the app still runs, but the image is larger |
| Tesseract version and languages | Community Cloud's documentation refers to a Debian package list. The packaged Tesseract may be older than the 5.x versions tested here, which can change OCR results | Run the OCR demo on several cards. Optionally add a temporary diagnostic, then remove it |
| Resource limits | Community Cloud apps have limited CPU and memory and are put to sleep when idle. The OCR limits (2 concurrent jobs, 30 per minute per process) were sized for a small host but not measured there | Watch resource warnings; lower `KYF_OCR_MAX_CONCURRENCY` if needed |
| Security headers | Streamlit sends no `Content-Security-Policy`, `X-Frame-Options`, or `X-Content-Type-Options` headers. Whether the platform adds them is unknown | `curl -sI <app URL>` |
| Persistence | The SQLite file is lost on restart. Expected: the app reseeds itself, so only profiles added through the generator are lost | Restart the app and confirm it reseeds |
| Logs | Platform logs may include Streamlit's own messages and tracebacks (operator-only) | Review logs after the smoke test |

## Configuration (optional)

All limits have safe defaults. Community Cloud exposes top-level secrets as environment variables,
so a `KYF_*` value could be set there. That is not needed, and none of these settings is secret.
The allowed ranges are in [operations.md](operations.md).

## Steps, once deployment is approved

1. Confirm the final integration into `main` has been approved and completed.
2. On share.streamlit.io, connect the GitHub account. Select the repository, branch `main`, and
   entry point `main.py`. Under advanced settings choose Python 3.13, and add no secrets.
3. Wait for the build. Check in the log which dependency file was used and that the Tesseract
   packages were installed.
4. Smoke test: each page loads; the OCR demo returns a result; the rate-limit message appears
   after 5 quick runs; the Research tabs render.
5. Run the Phase 6 browser checks against the URL: axe-core, console errors, and request origins.
   Check the response headers.
6. Only then share the URL.

## Rollback

- **Bad release:** revert the offending commit on `main` (a new commit, no history rewrite);
  Community Cloud redeploys from the branch.
- **Abuse or unexpected cost:** stop the app from the Community Cloud dashboard. All data is
  synthetic and recreated on start, so nothing needs to be backed up.
- **Removal:** delete the app in the dashboard. This does not affect the repository.
