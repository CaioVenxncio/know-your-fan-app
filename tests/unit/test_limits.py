"""Rate limiting and concurrency limits, with a fake clock and explicit synchronization."""

from __future__ import annotations

import contextlib
import threading

import pytest

from know_your_fan.config import Settings
from know_your_fan.limits import (
    GLOBAL_KEY,
    CapacityExceededError,
    ConcurrencyLimiter,
    OCRGuard,
    RateLimitedError,
    SlidingWindowRateLimiter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


# ------------------------------------------------------------------ rate limiter


def test_requests_within_limit_are_allowed(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(3, 60, clock=clock)
    for _ in range(3):
        limiter.acquire("a")


def test_request_over_limit_is_rejected_with_retry_after(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(2, 60, clock=clock)
    limiter.acquire("a")
    clock.advance(10)
    limiter.acquire("a")
    clock.advance(5)
    with pytest.raises(RateLimitedError) as excinfo:
        limiter.acquire("a")
    # The oldest event (t=0) leaves the window at t=60; now is t=15.
    assert excinfo.value.retry_after_seconds == pytest.approx(45)
    assert "45 seconds" in str(excinfo.value)


def test_rejected_requests_do_not_extend_the_window(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(1, 60, clock=clock)
    limiter.acquire("a")
    for _ in range(10):
        clock.advance(5)
        with pytest.raises(RateLimitedError):
            limiter.acquire("a")
    clock.advance(10.001)  # t > 60 since the only accepted event
    limiter.acquire("a")


def test_window_expiry_is_sliding(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(2, 60, clock=clock)
    limiter.acquire("a")  # t=0
    clock.advance(30)
    limiter.acquire("a")  # t=30
    clock.advance(30)  # t=60: first event expires exactly at the boundary
    limiter.acquire("a")
    with pytest.raises(RateLimitedError):
        limiter.acquire("a")  # events at t=30 and t=60 are still inside the window


def test_keys_are_independent(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(1, 60, clock=clock)
    limiter.acquire("session-a")
    limiter.acquire("session-b")
    with pytest.raises(RateLimitedError):
        limiter.acquire("session-a")


def test_tracked_state_is_bounded_by_lru_eviction(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(1, 60, max_keys=3, clock=clock)
    for key in ("a", "b", "c"):
        limiter.acquire(key)
    with pytest.raises(RateLimitedError):
        limiter.acquire("a")  # refreshes "a" as most recently used
    limiter.acquire("d")  # evicts "b", the least recently used key
    assert limiter.tracked_keys() == 3
    limiter.acquire("b")  # "b" was forgotten, so it is allowed again (documented trade-off)
    with pytest.raises(RateLimitedError):
        limiter.acquire("a")


def test_events_per_key_never_exceed_the_limit(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(3, 60, clock=clock)
    for _ in range(50):
        with contextlib.suppress(RateLimitedError):
            limiter.acquire("a")
    assert len(limiter._events["a"]) == 3


@pytest.mark.parametrize(("limit", "window", "max_keys"), [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_rate_limiter_rejects_invalid_parameters(limit: int, window: float, max_keys: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        SlidingWindowRateLimiter(limit, window, max_keys=max_keys)


def test_rate_limiter_is_thread_safe(clock: FakeClock) -> None:
    limiter = SlidingWindowRateLimiter(100, 60, clock=clock)
    accepted: list[int] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def worker() -> None:
        start.wait()
        for _ in range(50):
            try:
                limiter.acquire("shared")
            except RateLimitedError:
                continue
            with lock:
                accepted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(accepted) == 100  # exactly the limit, never more


# ------------------------------------------------------------------ concurrency limiter


def test_slots_are_bounded_and_released() -> None:
    limiter = ConcurrencyLimiter(2, wait_seconds=0)
    limiter.acquire()
    limiter.acquire()
    assert limiter.active == 2
    with pytest.raises(CapacityExceededError):
        limiter.acquire()
    limiter.release()
    limiter.acquire()
    assert limiter.max_observed == 2


def test_slot_is_released_when_work_raises() -> None:
    limiter = ConcurrencyLimiter(1, wait_seconds=0)
    with pytest.raises(RuntimeError, match="boom"), limiter.slot():
        raise RuntimeError("boom")
    assert limiter.active == 0
    with limiter.slot():
        assert limiter.active == 1


def test_bounded_wait_succeeds_when_a_slot_frees_up() -> None:
    limiter = ConcurrencyLimiter(1, wait_seconds=5)
    holding = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with limiter.slot():
            holding.set()
            release.wait()

    thread = threading.Thread(target=holder)
    thread.start()
    holding.wait()
    release.set()  # the waiter below gets the slot as soon as the holder exits
    with limiter.slot():
        assert limiter.active == 1
    thread.join()


def test_concurrent_workers_never_exceed_capacity() -> None:
    limiter = ConcurrencyLimiter(2, wait_seconds=0)
    inside = threading.Barrier(3)  # two workers + the test thread
    release = threading.Event()
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            with limiter.slot():
                inside.wait()
                release.wait()
            outcome = "ran"
        except CapacityExceededError:
            outcome = "rejected"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    inside.wait()  # both workers now hold a slot
    with pytest.raises(CapacityExceededError):
        limiter.acquire()  # a third caller is rejected immediately
    release.set()
    for t in threads:
        t.join()
    assert results == ["ran", "ran"]
    assert limiter.max_observed == 2
    assert limiter.active == 0


@pytest.mark.parametrize(("capacity", "wait"), [(0, 1.0), (1, -1.0)])
def test_concurrency_limiter_rejects_invalid_parameters(capacity: int, wait: float) -> None:
    with pytest.raises(ValueError, match="capacity"):
        ConcurrencyLimiter(capacity, wait)


# ------------------------------------------------------------------ OCR guard


@pytest.fixture
def guard(clock: FakeClock) -> OCRGuard:
    settings = Settings(ocr_session_limit=2, ocr_global_limit=3, ocr_max_concurrency=1)
    built = OCRGuard.from_settings(settings, clock=clock)
    built.concurrency.wait_seconds = 0
    return built


def test_guard_enforces_session_then_global_limits(guard: OCRGuard) -> None:
    for _ in range(2):
        with guard.admit("a"):
            pass
    with pytest.raises(RateLimitedError), guard.admit("a"):
        pass
    with guard.admit("b"):  # third accepted request process-wide
        pass
    with pytest.raises(RateLimitedError), guard.admit("c"):  # global budget is spent
        pass
    assert guard.global_limiter._events[GLOBAL_KEY]


def test_guard_rejects_when_capacity_is_exhausted(guard: OCRGuard) -> None:
    with guard.admit("a"), pytest.raises(CapacityExceededError), guard.admit("b"):
        pass
    assert guard.concurrency.active == 0


def test_guard_releases_capacity_after_failures(guard: OCRGuard, clock: FakeClock) -> None:
    with pytest.raises(TimeoutError), guard.admit("a"):
        raise TimeoutError
    assert guard.concurrency.active == 0
    with guard.admit("b"):
        assert guard.concurrency.active == 1


def test_guard_window_expiry_restores_budget(guard: OCRGuard, clock: FakeClock) -> None:
    for key in ("a", "a", "b"):
        with guard.admit(key):
            pass
    with pytest.raises(RateLimitedError), guard.admit("c"):
        pass
    clock.advance(60.001)
    with guard.admit("c"):
        pass
