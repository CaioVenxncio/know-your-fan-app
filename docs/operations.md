# Operations: resource safeguards, configuration, and logging

This document covers Phase 3: how the public synthetic-data demo protects shared resources, how to
configure the limits, what is logged, and what remains unprotected. It describes the code as it
exists on the modernization branch. Measurements name the run that produced them.

## 1. Initial resource and abuse assessment (before Phase 3)

Code references are to commit `a3d60ee`, the end of Phase 2.

| Surface | Finding | Status before Phase 3 |
|---|---|---|
| OCR execution | Every click on *Extract text and compare* started a Tesseract subprocess (`services.py:72`), with no per-visitor or process-wide limit. | **Exploitable:** unbounded request rate. |
| Concurrent sessions | Each Streamlit session runs in its own thread, so concurrent sessions started concurrent Tesseract processes with no bound. | **Exploitable:** unbounded parallel CPU use. |
| OCR timeout | A 15 s timeout (`ocr.py:21`). pytesseract terminates the subprocess on timeout and removes its temporary files in a `finally` block (`pytesseract.py:141-156`, `208-219`). | Mitigated. Every `RuntimeError` was reported as a timeout (`ocr.py:142`), which was imprecise. |
| Streamlit reruns | OCR runs only in the rerun triggered by the button (`app.py`, `if not st.button(...)`). Moving a slider re-renders a 900×520 card, which is cheap. | Mitigated. |
| Image processing | 4 MP pixel cap and bounded blur and rotation (`ocr.py:94-126`). No uploads. | Partly mitigated. A NaN rotation bypassed the bound (`abs(nan) > 10` is false), non-image objects and unsupported modes raised unhandled errors, and there was no per-side limit. |
| SQLite writes | The capacity check ran outside any transaction (`storage.py:89-112`). Python's `sqlite3` only begins a transaction at the `INSERT`. | **Exploitable race.** Measured locally: 8 threads writing against a cap of 30 exceeded the cap in **20 of 20** trials (up to 36 rows). |
| Seeding | `seed_if_empty` counted, then inserted in separate transactions. | Low impact (duplicate IDs are ignored) but not atomic. |
| Profile writes | One visitor could fill the shared 500-profile dataset by clicking repeatedly. | Bounded by the cap only. |
| Failure recovery | Storage errors during page rendering and on *Add to dataset* (other than the cap) were not caught; SQLite lock errors were indistinguishable from other failures. | Partly mitigated (stack traces hidden by configuration). |
| Logging | None. | No operational visibility. |

## 2. Controls implemented

### OCR admission control (`limits.py`, `services.run_text_matching`)

Requests pass these checks in order. Each step runs only if the previous one passed, and
**Tesseract starts only after all of them**:

1. **Input checks:** the name is validated, and the image's metadata is checked (`check_image`).
   Invalid input spends no rate-limit budget.
2. **Per-session rate limit:** a sliding window, by default 5 requests per 60 s.
3. **Process-wide (global) rate limit:** a sliding window, by default 30 requests per 60 s across
   all sessions.
4. **Concurrency limit:** a bounded semaphore, by default 2 simultaneous OCR jobs per process. A
   request waits at most 2 s for a free slot, then gets "The OCR engine is busy". There is no
   queue, and the slot is released in `finally`, including after errors and timeouts.

A request that passes the rate checks but finds no free slot still counts against the rate limits.
This stops a client from probing capacity at no cost.

**Rate limiter properties:**

- Time comes from `time.monotonic()`, which tests replace with a fake clock.
- Memory is bounded: at most 10,000 tracked keys (least recently used evicted first), and at most
  `limit` timestamps per key.
- It is thread-safe, and rejected requests do not extend the window.

**Session identity:** a random UUID stored in `st.session_state`. **This is not a security
boundary.** Opening a new browser session gives a new identifier. Per-session limits are a fairness
measure, and the global limit and the concurrency limit are the real bounds on OCR work. LRU
eviction can also forget a session after 10,000 newer ones, which again only matters for fairness.

### Tesseract threading (`ocr.limit_engine_threads`)

Tesseract's OpenMP build starts one thread per CPU core. At start-up, `build_runtime()` sets
`OMP_THREAD_LIMIT=1` unless the operator has set it (the Docker image also sets it). pytesseract
passes `os.environ` to the subprocess, so every OCR call inherits it. Evidence from CI run
38387536577 (Ubuntu 24.04, Tesseract 5.3.4, engine warmed up first, 2 concurrent jobs):

| Configuration | Sequential median (5 runs) | Each of 2 concurrent jobs |
|---|---|---|
| Default threading | 0.365 s | 6.225 s / 6.363 s |
| `OMP_THREAD_LIMIT=1` | 0.352 s | 0.356 s / 0.365 s |

This is a single run on one runner type, not a statistical benchmark. It does show that the
concurrency limit alone did not prevent CPU oversubscription.

Across later CI runs, the default-threading arm varied widely, while the `OMP_THREAD_LIMIT=1` arm
stayed at about 0.4 s whenever it ran:

| CI run | Two concurrent jobs, default threading |
|---|---|
| 38387254881 | 8.67 s (no warm-up) |
| 38387536577 | 6.23 s / 6.36 s |
| 38388256877 | 2.87 s / 2.95 s |
| 38399044083 | Both jobs exceeded the **15 s OCR timeout** |

In the last run the timeout was handled correctly: the slots were released and the next request
succeeded. The validation script originally counted those timeouts as safety-invariant failures
and failed the step before the `OMP_THREAD_LIMIT=1` arm ran. It now records timeouts as a measured
outcome (`timeouts`) in Phase 4. The invariants themselves are unchanged: concurrency never above
capacity, all slots released, no unexpected errors.

### OCR failures and image safety (`ocr.py`)

- Timeouts raise `OCRTimeoutError`; other engine errors raise `OCRFailedError`; a missing engine
  or missing language data raises `OCRUnavailableError`. Visitors see fixed messages only.
- The application does not retry failed OCR.
- `check_image` rejects:
  - non-image objects;
  - empty images;
  - images over the pixel cap (4 MP by default);
  - images with any side over 8,000 px.
- Unsupported modes (for example `La` and `LAB` in Pillow 12) become `InvalidImageError`.
- `degrade` rejects non-finite blur and rotation values.

### SQLite concurrency (`storage.py`)

- Connections run in autocommit mode with explicit `BEGIN IMMEDIATE` write transactions. The write
  lock is taken **before** the duplicate and capacity checks, so check-then-insert is atomic across
  threads, processes, and containers that share the file. After the change: **0 of 20** contention
  trials exceeded the cap.
- `seed_if_empty` runs as one transaction, so concurrent seeders insert exactly once.
- SQLite retries a locked database for the busy timeout (default 5 s). After that, the error is
  reported as `StorageBusyError` ("The demo database is busy. Please try again.").
- Every connection is closed after each operation; a test asserts this.
- Storage errors while rendering a page show a message instead of failing the session.
- Per-session write limit: at most 10 dataset additions per 10 minutes. The 500-profile cap remains
  the hard bound.

## 3. Configuration

All limits are environment variables with safe defaults. Unset or blank means "use the default".
Malformed, non-finite, or out-of-range values stop the app with a generic message
(`ConfigurationError`). The log names the variable but not its value. Settings are read once per
process (`st.cache_resource`), not on every rerun.

| Variable | Default | Allowed range | Purpose |
|---|---|---|---|
| `KYF_DB_PATH` | `.data/kyf_demo.db` | path | SQLite file |
| `KYF_OCR_TIMEOUT_SECONDS` | 15 | 1–60 | Tesseract timeout |
| `KYF_OCR_SESSION_LIMIT` | 5 | 1–100 | OCR requests per session per window |
| `KYF_OCR_GLOBAL_LIMIT` | 30 | 1–10,000, and at least the session limit | OCR requests per process per window |
| `KYF_OCR_WINDOW_SECONDS` | 60 | 1–3,600 | Rate-limit window |
| `KYF_OCR_MAX_CONCURRENCY` | 2 | 1–8 | Simultaneous OCR jobs per process |
| `KYF_MAX_IMAGE_PIXELS` | 4,000,000 | 1,000,000–16,000,000 | Image pixel cap |
| `KYF_MAX_PROFILES` | 500 | 25–10,000 | Dataset cap (must hold the 25 seeded profiles) |
| `KYF_SQLITE_BUSY_TIMEOUT_SECONDS` | 5 | 0.1–30 | Wait for a locked database |
| `OMP_THREAD_LIMIT` | 1 (set if absent) | Tesseract/OpenMP | Threads per Tesseract process |

The per-session write limit (10 per 10 minutes) and the 2 s capacity wait are code constants
(`services.py`, `limits.py`). They were not made configurable because there is no operational need
yet.

## 4. Logging policy

- **Library:** standard `logging`, logger `know_your_fan.*`, one stderr handler added at start-up.
- **Logged:**
  - OCR timeouts (WARNING), engine failures with exit status (WARNING), missing engine or language
    data (ERROR);
  - rate-limit rejections (INFO) and capacity rejections (WARNING), both **throttled** to at most
    one line per minute with a count of suppressed events;
  - storage busy (WARNING) and failures (ERROR) with the SQLite error code only (e.g. `SQLITE_BUSY`);
  - allowlist rejections (count only), dataset at capacity, invalid configuration (no values), and
    the effective OCR thread limit.
- **Never logged:** OCR text, entered or generated names, profile contents, images, file paths,
  configuration values, or messages from third-party exceptions (exception type names are used
  instead). Tests assert this for OCR, storage, and complete UI flows.
- **No external telemetry.** Streamlit usage statistics stay disabled.

## 5. Bounded operational validation

`scripts/validate_limits.py` runs small, fixed workloads and exits with status 1 if an invariant is
violated. CI runs it twice with real Tesseract (default threading and `OMP_THREAD_LIMIT=1`) and
publishes results as run annotations. Locally (Windows, no Tesseract) it runs with a simulated
0.5 s OCR workload.

| Scenario | Result | Source |
|---|---|---|
| Rate limits (fake clock, defaults) | 1 session × 20 requests → 5 accepted. 10 sessions × 5 → 25 accepted (the global budget of 30 minus 5 already used). Accepted again after the window. Engine calls = 31 = accepted requests. | Deterministic (CI and local) |
| 8 simultaneous OCR requests, capacity 2, 0.25 s wait | 2 accepted, 6 rejected (busy), 0 errors, at most 2 running at once, 0 active afterwards | CI 38387536577, real Tesseract |
| Real Tesseract timeouts (timeout 0.01 s), 4 attempts | 4 timeouts, 0 slots held afterwards, next request succeeded, **0** `tess_*` temporary files left | CI 38387536577 |
| Generating and validating 10,000 profiles | 0.133 s generation, 0.038 s allowlist validation, 0 violations | CI 38387254881 |
| SQLite contention: 8 threads × 25 writes, cap 100 | 100 added, 100 refused at the cap, 0 busy, 100 rows; 0.333 s | CI 38387254881 |
| Sequential real OCR, clean card | median 0.262 s (min 0.245, max 0.264) | CI 38387254881 |

These figures come from shared CI runners and vary between runs. They are not capacity planning
numbers.

## 6. Limitations and remaining denial-of-service risks

- **Per process only.** All limits live in the Python process. Several processes, containers, or
  replicas each enforce their own limits, so totals scale with the number of replicas. A shared
  limiter (for example Redis) was deliberately not added; see ADR 0006. The profile cap is the
  exception, because it is enforced by SQLite transactions on the shared file.
- **Session limits can be bypassed** by opening new sessions. The global and concurrency limits
  still apply.
- **No per-IP limiting.** Streamlit does not expose a trustworthy client address to the app, and
  the deployment target is not decided yet.
- **One abuser can use up the global budget.** Legitimate visitors are then refused for up to one
  window (60 s by default). This trades fairness for a hard CPU bound.
- **Stuck subprocesses:** on timeout, pytesseract sends SIGTERM and waits 1 s without escalating to
  SIGKILL. A Tesseract process that ignored SIGTERM could outlive its slot. This has not been
  observed (the CI timeout scenario recovered fully).
- **Not covered by these limits:**
  - the Streamlit server itself (websocket connections, reruns, memory per session);
  - network-level floods;
  - card rendering on slider changes (cheap, but not rate-limited).
- **Weekly audit activation:** the scheduled dependency audit only runs once the workflow exists
  on the default branch, that is, after the final merge into `main`. Until then, audits run on
  every push.
- **Future option (not enabled):** Dependabot or Renovate could open dependency-update PRs. This
  was not configured, because automatic PRs are outside the agreed workflow.
