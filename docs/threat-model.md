# Threat model

A lightweight, STRIDE-based threat model of the public synthetic-data demo, as implemented on
the modernization branch. "Implemented" means the mitigation exists in code or configuration
today; "Residual" covers what is not mitigated.

## System boundaries

```mermaid
flowchart LR
    v([Anonymous visitor]) -- HTTPS / websocket<br/>(provided by host) --> s
    subgraph host [Host: local machine, container, or Streamlit Community Cloud]
        s[Streamlit process<br/>know_your_fan] --> db[(SQLite file)]
        s --> t[[Tesseract binary]]
    end
    dev([Maintainer]) -- git push --> gh[GitHub repository + Actions]
    gh -. dependencies .-> pypi[(PyPI)]
```

- **Trust boundary 1:** visitor to Streamlit process. Everything a visitor sends (widget values)
  is untrusted.
- **Trust boundary 2:** repository to CI, and package registries to the build. Third-party code
  and actions are untrusted until pinned and verified.
- **Out of scope:** the host platform's TLS, network, and access logs. There is no deployment
  at present.

## Protected assets

| Asset | Why it matters |
|---|---|
| Visitors' real personal data | Must never be requested or stored. This is the main privacy goal. |
| Accuracy of claims | The app must never be presented or relied on as identity verification. |
| Availability of the demo | CPU (OCR) and disk (SQLite) are finite. |
| Integrity of the demo dataset | It should contain only generator output. |
| Repository and CI integrity | Secrets, dependencies, and workflow definitions. |

## Trust assumptions

- The operator controls environment variables (`KYF_DB_PATH`) and `.streamlit/config.toml`.
  Visitors cannot change them.
- The Tesseract binary and its language data come from the OS or the Docker image's package
  manager.
- Streamlit escapes text in `st.text`, `st.code`, and `st.dataframe`.

## STRIDE analysis

| Category | Threat scenario | Implemented mitigation | Residual risk |
|---|---|---|---|
| **Spoofing** | Someone presents a passed text match as proof of identity. | UI, README, and docs state "not identity verification", and no wording claims validity. Tests scan every page for misleading claims. | Users can still misread the output. Wording reduces this but cannot prevent it. |
| **Spoofing** | Someone impersonates the admin. | There is no admin or authentication; the hardcoded password was removed in Phase 1. | The old password is in Git history. It is treated as compromised and must never be reused. |
| **Tampering** | A visitor inserts arbitrary data (real CPF, address, script) into the dataset. | There are no free-text write paths. `storage.add` enforces the allowlist `synthetic_violations`, and SQL is parameterized. | None known for the UI. A code change that bypassed `add()` would bypass the allowlist. |
| **Tampering** | A compromised dependency or GitHub Action enters the build. | `uv.lock` pins versions and hashes; Actions are pinned to commit SHAs; gitleaks and actionlint binaries are checksum-verified; pre-commit hooks are pinned to SHAs. | Trust in PyPI and upstream maintainers remains. The lock must be refreshed to receive fixes. |
| **Repudiation** | A visitor denies adding profiles. | Not applicable: there are no accounts and no meaningful actions. | No audit log exists, by design. |
| **Information disclosure** | Stack traces reveal paths or internals. | `client.showErrorDetails = "none"`; storage and OCR errors become friendly messages. | Host-level logs may still contain tracebacks (operator-only). |
| **Information disclosure** | Real data is committed to Git. | `.gitignore` covers databases, `.env`, and secrets; gitleaks runs in pre-commit and on full history in CI. | gitleaks is pattern-based. Personal data that doesn't look like a secret (e.g. names) is not detected. |
| **Information disclosure** | Telemetry about visitors. | `browser.gatherUsageStats = false`. | The hosting platform's own logs. |
| **Denial of service** | Repeated OCR requests exhaust CPU. | Images are capped at 4 MP; Tesseract timeout is 15 s; blur and rotation are bounded; uploads are not possible. | **No rate limiting**: concurrent sessions can each run Tesseract. Acceptable for a demo; see Phase 3. |
| **Denial of service** | Unbounded dataset growth fills the disk. | 500-profile cap, enforced in a transaction, and duplicate IDs are ignored. | — |
| **Denial of service** | Locked SQLite database under concurrent writes. | Short transactions and a 5 s busy timeout; failures become `StorageError`. | Heavy concurrency could still produce visible errors. |
| **Elevation of privilege** | The container process escapes or modifies the image. | The Docker image runs as an unprivileged user (UID 10001), and only `/app/.data` is writable by it. | Host and container runtime security are outside this project. |
| **Elevation of privilege** | CI token abuse. | The workflow token has `contents: read` only; checkout does not persist credentials; no secrets are used. | — |

## Unsafe rendering and injection

- **Markdown/HTML injection:** profile values and OCR output are rendered with `st.text`,
  `st.code`, or `st.dataframe`, never interpolated into Markdown or HTML (`app.py` module
  docstring). The fixed explanatory texts on the About page use `st.write` with static strings
  only.
- **SQL injection:** all statements use bound parameters (`storage.py`).
- **Path injection:** the database path comes only from the operator-controlled `KYF_DB_PATH`.
- **Regular expressions:** all patterns are constants; user input is never compiled as a regex.

## OCR failure modes

| Failure | Effect | Handling |
|---|---|---|
| Tesseract or language data missing | No OCR possible | `OCRUnavailableError` and a friendly message; CI fails if this happens there. |
| Engine timeout or crash | No text | `OCRFailedError` and a friendly message. |
| Recognition errors (blur, rotation, fonts) | False "missing" words | Shown as a partial or no match. No threshold tuning exists yet (research phase). |
| Recognized text coincidentally containing the name | False "found" | Whole-word matching reduces this. It cannot be ruled out. |

## Residual risks summary

1. There is no rate limiting on OCR, so CPU exhaustion is possible under abuse.
2. The meaning of a text match can still be misunderstood despite the disclaimers.
3. There is a window of dependency vulnerability between lock refreshes. CI audits on every
   push, but nothing schedules audits when there are no pushes.
4. The historical password remains in Git history; it is compromised and must not be reused.
5. The behaviour on Streamlit Community Cloud is unverified because nothing has been deployed.
