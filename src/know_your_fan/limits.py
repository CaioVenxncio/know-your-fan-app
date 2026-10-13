"""In-process resource limits: sliding-window rate limiting and bounded concurrency.

Scope and limitations (also in docs/operations.md):

* State lives in this Python process. Limits are shared by all Streamlit
  sessions served by the process, but **not** across processes, containers,
  or replicas. Each replica enforces its own limits.
* Per-session limits key on an identifier stored in Streamlit session state.
  A visitor can obtain a new identifier by opening a new session, so
  per-session limits are a fairness measure, **not** a security boundary. The
  process-wide (global) limit and the concurrency limit are the actual bounds
  on OCR work.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from know_your_fan.config import Settings
from know_your_fan.observability import LOGGER_NAME, ThrottledEvent

Clock = Callable[[], float]

GLOBAL_KEY = "__global__"
DEFAULT_MAX_KEYS = 10_000
DEFAULT_CAPACITY_WAIT_SECONDS = 2.0

_logger = logging.getLogger(f"{LOGGER_NAME}.limits")


class ResourceLimitError(RuntimeError):
    """A request was refused to protect shared resources. Messages are safe to display."""


class RateLimitedError(ResourceLimitError):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        wait = max(1, math.ceil(self.retry_after_seconds))
        super().__init__(f"Too many requests. Please wait about {wait} seconds and try again.")


class CapacityExceededError(ResourceLimitError):
    def __init__(self) -> None:
        super().__init__("The OCR engine is busy with other requests. Please try again shortly.")


class SlidingWindowRateLimiter:
    """Allow at most ``limit`` events per key within any ``window_seconds`` interval.

    Memory is bounded: at most ``max_keys`` keys are tracked (least recently
    used keys are evicted first) and each key stores at most ``limit``
    timestamps. Elapsed time comes from a monotonic clock, which tests replace.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Clock = time.monotonic,
    ) -> None:
        if limit < 1 or window_seconds <= 0 or max_keys < 1:
            raise ValueError("limit, window_seconds and max_keys must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._events: OrderedDict[str, deque[float]] = OrderedDict()

    def acquire(self, key: str) -> None:
        """Record one event for ``key`` or raise :class:`RateLimitedError`."""
        now = self._clock()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                events = deque()
                self._events[key] = events
                while len(self._events) > self.max_keys:
                    self._events.popitem(last=False)
            else:
                self._events.move_to_end(key)
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise RateLimitedError(events[0] + self.window_seconds - now)
            events.append(now)

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._events)


class ConcurrencyLimiter:
    """Bound simultaneous work with a semaphore and a bounded wait.

    There is no queue: a caller waits at most ``wait_seconds`` for a free slot
    and is then rejected with :class:`CapacityExceededError`. The slot is always
    released, including when the work raises or times out.
    """

    def __init__(self, capacity: int, wait_seconds: float = DEFAULT_CAPACITY_WAIT_SECONDS):
        if capacity < 1 or wait_seconds < 0:
            raise ValueError("capacity must be positive and wait_seconds non-negative")
        self.capacity = capacity
        self.wait_seconds = wait_seconds
        self._semaphore = threading.BoundedSemaphore(capacity)
        self._lock = threading.Lock()
        self._active = 0
        self._max_observed = 0

    def acquire(self) -> None:
        """Take a slot, waiting at most ``wait_seconds``; raise if none frees up."""
        if not self._semaphore.acquire(timeout=self.wait_seconds):
            raise CapacityExceededError()
        with self._lock:
            self._active += 1
            self._max_observed = max(self._max_observed, self._active)

    def release(self) -> None:
        with self._lock:
            self._active -= 1
        self._semaphore.release()

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @property
    def max_observed(self) -> int:
        with self._lock:
            return self._max_observed


class OCRGuard:
    """Admission control for OCR: per-session rate, global rate, then concurrency.

    Rate checks happen before a concurrency slot is requested, so rejected
    requests never start Tesseract. An attempt that passes the rate checks but
    finds no free slot still counts against the rate limits; this keeps a
    client from probing capacity at no cost.
    """

    def __init__(
        self,
        session_limiter: SlidingWindowRateLimiter,
        global_limiter: SlidingWindowRateLimiter,
        concurrency: ConcurrencyLimiter,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self.session_limiter = session_limiter
        self.global_limiter = global_limiter
        self.concurrency = concurrency
        self._rate_rejections = ThrottledEvent(
            _logger, "OCR request rejected by rate limit", level=logging.INFO, clock=clock
        )
        self._capacity_rejections = ThrottledEvent(
            _logger, "OCR request rejected: all OCR slots busy", clock=clock
        )

    @classmethod
    def from_settings(cls, settings: Settings, *, clock: Clock = time.monotonic) -> OCRGuard:
        window = settings.ocr_window_seconds
        return cls(
            SlidingWindowRateLimiter(settings.ocr_session_limit, window, clock=clock),
            SlidingWindowRateLimiter(settings.ocr_global_limit, window, clock=clock),
            ConcurrencyLimiter(settings.ocr_max_concurrency),
            clock=clock,
        )

    @contextmanager
    def admit(self, session_key: str) -> Iterator[None]:
        try:
            self.session_limiter.acquire(session_key)
            self.global_limiter.acquire(GLOBAL_KEY)
        except RateLimitedError:
            self._rate_rejections.record()
            raise
        try:
            self.concurrency.acquire()
        except CapacityExceededError:
            self._capacity_rejections.record()
            raise
        try:
            yield
        finally:
            self.concurrency.release()
