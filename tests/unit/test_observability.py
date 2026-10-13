from __future__ import annotations

import logging

import pytest

from know_your_fan.observability import LOGGER_NAME, ThrottledEvent, configure_logging


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging()
    handlers = len(logger.handlers)
    configure_logging()
    configure_logging()
    assert len(logger.handlers) == handlers
    assert logger.name == LOGGER_NAME
    assert logger.propagate is True  # keep records visible to root handlers and caplog


def test_throttled_event_emits_once_per_interval(caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    logger = logging.getLogger(f"{LOGGER_NAME}.test")
    event = ThrottledEvent(logger, "limit hit", interval_seconds=60, clock=clock)
    with caplog.at_level(logging.WARNING, logger=logger.name):
        for _ in range(1000):
            event.record()
        clock.now = 61
        event.record()
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "limit hit (0 similar events suppressed)",
        "limit hit (999 similar events suppressed)",
    ]
