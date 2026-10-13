"""Bounded operational validation of the Phase 3 resource safeguards.

Runs small, fixed workloads against the real components (no network, synthetic
data only) and reports what happened. It exits with status 1 if a safety
invariant is violated:

* no more OCR requests accepted than the rate limits allow;
* never more simultaneous OCR jobs than the configured capacity;
* the profile cap is never exceeded under concurrent writers;
* OCR capacity is fully released after failures and timeouts;
* no Tesseract temporary files are left behind (real-OCR mode).

Usage:
    python scripts/validate_limits.py              # simulated OCR work
    python scripts/validate_limits.py --real-ocr   # requires Tesseract
    python scripts/validate_limits.py --github     # also emit ::notice annotations

Timings are wall-clock measurements on the machine that runs the script. With
simulated OCR, the "work" is a fixed sleep, so concurrency results describe the
limiter, not Tesseract performance.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from know_your_fan import ocr, services
from know_your_fan.config import Settings
from know_your_fan.limits import CapacityExceededError, OCRGuard, RateLimitedError
from know_your_fan.storage import StorageBusyError, StorageLimitError, SyntheticProfileRepository
from know_your_fan.synthetic import generate_profiles, synthetic_violations
from know_your_fan.text_matching import match_name

SIMULATED_WORK_SECONDS = 0.5
CONCURRENT_REQUESTS = 8
CAPACITY_WAIT_SECONDS = 0.25

Result = dict[str, Any]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _card() -> tuple[Image.Image, str]:
    profile = generate_profiles(1, seed=2025)[0]
    return ocr.render_specimen(profile), profile.name


def _tesseract_temp_files() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("tess_*")}


def scenario_rate_limits() -> Result:
    """Deterministic: default limits, fake clock, no OCR engine involved."""
    settings = Settings()
    clock = FakeClock()
    guard = OCRGuard.from_settings(settings, clock=clock)
    image, name = _card()
    calls = 0

    def extractor(_: Image.Image) -> str:
        nonlocal calls
        calls += 1
        return name

    def attempt(session: str) -> bool:
        try:
            services.run_text_matching(image, name, extractor, guard=guard, session_key=session)
        except RateLimitedError:
            return False
        return True

    single = [attempt("burst") for _ in range(20)]
    many = [attempt(f"session-{i}") for i in range(10) for _ in range(5)]
    clock.now += settings.ocr_window_seconds + 0.001
    after_window = attempt("burst")
    accepted = sum(single) + sum(many)
    return {
        "kind": "deterministic (fake clock)",
        "session_limit": settings.ocr_session_limit,
        "global_limit": settings.ocr_global_limit,
        "single_session_requests": len(single),
        "single_session_accepted": sum(single),
        "multi_session_requests": len(many),
        "multi_session_accepted": sum(many),
        "accepted_after_window": after_window,
        "engine_calls": calls,
        "ok": sum(single) == settings.ocr_session_limit
        and accepted <= settings.ocr_global_limit
        and calls == accepted + int(after_window)
        and after_window,
    }


def scenario_concurrency(work: Callable[[Image.Image], str], label: str) -> Result:
    """Real threads released together; OCR work is real or a fixed sleep."""
    settings = Settings(ocr_session_limit=100, ocr_global_limit=10_000)
    guard = OCRGuard.from_settings(settings)
    guard.concurrency.wait_seconds = CAPACITY_WAIT_SECONDS
    image, name = _card()
    outcomes: list[str] = []
    durations: list[float] = []
    lock = threading.Lock()
    start = threading.Barrier(CONCURRENT_REQUESTS)

    def client(index: int) -> None:
        start.wait()
        began = time.perf_counter()
        try:
            services.run_text_matching(image, name, work, guard=guard, session_key=f"c{index}")
            outcome = "accepted"
        except CapacityExceededError:
            outcome = "rejected_busy"
        except Exception as exc:  # any other failure is reported as an error count
            outcome = f"error:{type(exc).__name__}"
        with lock:
            outcomes.append(outcome)
            durations.append(time.perf_counter() - began)

    threads = [threading.Thread(target=client, args=(i,)) for i in range(CONCURRENT_REQUESTS)]
    wall = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall
    errors = [o for o in outcomes if o.startswith("error")]
    return {
        "kind": label,
        "capacity": guard.concurrency.capacity,
        "capacity_wait_seconds": CAPACITY_WAIT_SECONDS,
        "simultaneous_requests": CONCURRENT_REQUESTS,
        "accepted": outcomes.count("accepted"),
        "rejected_busy": outcomes.count("rejected_busy"),
        "errors": len(errors),
        "max_concurrent_observed": guard.concurrency.max_observed,
        "active_after": guard.concurrency.active,
        "wall_seconds": round(wall, 3),
        "max_request_seconds": round(max(durations), 3),
        "ok": guard.concurrency.max_observed <= guard.concurrency.capacity
        and guard.concurrency.active == 0
        and not errors,
    }


def scenario_failure_recovery(real_ocr: bool) -> Result:
    """Failures and timeouts must release capacity; the next request must succeed."""
    guard = OCRGuard.from_settings(Settings(ocr_session_limit=100, ocr_global_limit=10_000))
    guard.concurrency.wait_seconds = 0
    image, name = _card()
    temp_before = _tesseract_temp_files()
    work = _too_short_real_ocr if real_ocr else _simulated_timeout
    failures = 0
    for _ in range(guard.concurrency.capacity + 2):
        try:
            services.run_text_matching(image, name, work, guard=guard, session_key="r")
        except ocr.OCRFailedError:
            failures += 1
    active_after_failures = guard.concurrency.active
    if real_ocr:
        outcome = services.run_text_matching(image, name, guard=guard, session_key="r")
    else:
        outcome = services.run_text_matching(
            image, name, lambda _: name, guard=guard, session_key="r"
        )
    leaked = sorted(_tesseract_temp_files() - temp_before) if real_ocr else []
    return {
        "kind": "real Tesseract timeouts" if real_ocr else "simulated timeouts",
        "timeouts_triggered": failures,
        "active_slots_after_failures": active_after_failures,
        "next_request_succeeded": outcome.match.all_found,
        "tesseract_temp_files_leaked": len(leaked),
        "ok": failures == guard.concurrency.capacity + 2
        and active_after_failures == 0
        and outcome.match.all_found
        and not leaked,
    }


def scenario_profile_generation() -> Result:
    count = 10_000
    began = time.perf_counter()
    profiles = generate_profiles(count, seed=7)
    generated = time.perf_counter() - began
    began = time.perf_counter()
    violations = sum(bool(synthetic_violations(p)) for p in profiles)
    validated = time.perf_counter() - began
    return {
        "kind": "measured",
        "profiles": count,
        "generation_seconds": round(generated, 3),
        "allowlist_validation_seconds": round(validated, 3),
        "allowlist_violations": violations,
        "ok": violations == 0,
    }


def scenario_storage_contention() -> Result:
    cap, writers, per_writer = 100, 8, 25
    profiles = generate_profiles(writers * per_writer, seed=99)
    counts = {"added": 0, "limit": 0, "busy": 0, "duplicate": 0}
    lock = threading.Lock()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "contention.db"
        SyntheticProfileRepository(path).initialize()
        start = threading.Barrier(writers)

        def writer(index: int) -> None:
            repo = SyntheticProfileRepository(path, max_profiles=cap, busy_timeout_seconds=10)
            start.wait()
            for profile in profiles[index * per_writer : (index + 1) * per_writer]:
                try:
                    key = "added" if repo.add(profile) else "duplicate"
                except StorageLimitError:
                    key = "limit"
                except StorageBusyError:
                    key = "busy"
                with lock:
                    counts[key] += 1

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(writers)]
        began = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - began
        rows = SyntheticProfileRepository(path).count()
    return {
        "kind": "measured (real SQLite, threads)",
        "cap": cap,
        "write_attempts": writers * per_writer,
        **counts,
        "rows_after": rows,
        "wall_seconds": round(elapsed, 3),
        "ok": rows == cap == counts["added"],
    }


def scenario_ocr_latency(runs: int = 5) -> Result:
    image, name = _card()
    times = []
    for _ in range(runs):
        began = time.perf_counter()
        text = ocr.extract_text(image)
        times.append(time.perf_counter() - began)
    return {
        "kind": "measured (real Tesseract, sequential, clean card)",
        "runs": runs,
        "min_seconds": round(min(times), 3),
        "median_seconds": round(statistics.median(times), 3),
        "max_seconds": round(max(times), 3),
        "last_run_name_found": match_name(name, text).all_found,
        "ok": True,
    }


def _too_short_real_ocr(image: Image.Image) -> str:
    """A real Tesseract run with a timeout far too short to finish."""
    return ocr.extract_text(image, timeout_seconds=0.01)


def _simulated_timeout(image: Image.Image) -> str:
    raise ocr.OCRTimeoutError("OCR timed out.")


def _simulated_work(image: Image.Image) -> str:
    time.sleep(SIMULATED_WORK_SECONDS)
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--real-ocr", action="store_true", help="use the real Tesseract engine")
    parser.add_argument("--github", action="store_true", help="emit GitHub ::notice annotations")
    parser.add_argument("--json", type=Path, help="also write results to this JSON file")
    args = parser.parse_args(argv)

    results: dict[str, Result] = {
        "rate_limits": scenario_rate_limits(),
        "concurrency": scenario_concurrency(
            ocr.extract_text if args.real_ocr else _simulated_work,
            "measured (real Tesseract)" if args.real_ocr else "measured (simulated 0.5 s work)",
        ),
        "failure_recovery": scenario_failure_recovery(args.real_ocr),
        "profile_generation": scenario_profile_generation(),
        "storage_contention": scenario_storage_contention(),
    }
    if args.real_ocr:
        results["ocr_latency"] = scenario_ocr_latency()

    for name, result in results.items():
        status = "OK " if result["ok"] else "FAIL"
        details = ", ".join(f"{k}={v}" for k, v in result.items() if k != "ok")
        print(f"[{status}] {name}: {details}")
        if args.github:
            level = "notice" if result["ok"] else "error"
            print(f"::{level} title=validate_limits {name}::{details}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if all(r["ok"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
