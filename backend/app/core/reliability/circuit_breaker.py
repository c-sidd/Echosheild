"""Minimal in-process circuit breaker for upstream scientific services."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from enum import StrEnum

_LOG = logging.getLogger("echoshield.circuit")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is open."""


class CircuitBreaker:
    """Thread-safe circuit breaker.

    After ``failure_threshold`` consecutive failures the circuit opens and
    rejects calls with :class:`CircuitOpenError` until ``reset_timeout``
    seconds elapse, after which a single trial call is allowed (half-open).
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
    ) -> None:
        self.name = name or f"circuit-{uuid.uuid4().hex[:8]}"
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        with self._lock:
            elapsed = time.monotonic() - self._opened_at if self._opened_at is not None else None
            if (
                self._state is CircuitState.OPEN
                and elapsed is not None
                and elapsed >= self.reset_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                _LOG.info("circuit=%s half_open", self.name)
            return self._state

    def allow_call(self) -> bool:
        """Return True when a call may proceed; transitions open->half-open."""
        return self.state is not CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            if self._state is not CircuitState.CLOSED:
                _LOG.info("circuit=%s closed_after_recovery", self.name)
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                _LOG.warning("circuit=%s opened failures=%d", self.name, self._failures)

    def __enter__(self) -> CircuitBreaker:
        if not self.allow_call():
            raise CircuitOpenError(f"circuit {self.name} is open")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
