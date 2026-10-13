"""Privacy-safe operational logging.

Logging policy (see docs/operations.md):

* Log technical events only: limits reached, timeouts, engine and storage
  failures, configuration errors.
* Never log OCR text, entered names, profile contents, images, or the
  messages of exceptions raised by third-party code. Use exception type names
  and fixed error codes instead.
* Throttle events that an abuser can trigger repeatedly.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

LOGGER_NAME = "know_your_fan"
_HANDLER_MARKER = "_know_your_fan_handler"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Attach one stderr handler to the package logger. Safe to call repeatedly.

    Propagation is left enabled so standard tooling (for example pytest's log
    capture) still sees these records.
    """
    logger = logging.getLogger(LOGGER_NAME)
    if not any(getattr(h, _HANDLER_MARKER, False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


class ThrottledEvent:
    """Log a repeatable event at most once per ``interval`` seconds.

    The first occurrence is logged immediately. Later occurrences within the
    interval are counted and reported in the next emitted message, so
    repeated abuse produces a bounded number of log lines.
    """

    def __init__(
        self,
        logger: logging.Logger,
        message: str,
        *,
        level: int = logging.WARNING,
        interval_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._logger = logger
        self._message = message
        self._level = level
        self._interval = interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._last_emit: float | None = None
        self._suppressed = 0

    def record(self) -> None:
        now = self._clock()
        with self._lock:
            if self._last_emit is not None and now - self._last_emit < self._interval:
                self._suppressed += 1
                return
            suppressed, self._suppressed = self._suppressed, 0
            self._last_emit = now
        self._logger.log(
            self._level, "%s (%d similar events suppressed)", self._message, suppressed
        )
