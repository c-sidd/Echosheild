"""Retry helpers for flaky upstream scientific services."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
import tenacity

_LOG = logging.getLogger("echoshield.retry")

T = TypeVar("T")

_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_retryable(exception: BaseException) -> bool:
    """Retry transient network failures and server-side HTTP errors only."""
    if isinstance(
        exception,
        (httpx.TimeoutException, httpx.TransportError),
    ):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in _RETRYABLE_HTTP_STATUSES
    return False


def _retry_predicate() -> Any:
    """tenacity-compatible predicate for transient failures."""
    return tenacity.retry_if_exception(_is_retryable)


def async_retry[**P, T](
    operation: str,
    *,
    attempts: int = 3,
    initial_wait: float = 0.5,
    max_wait: float = 8.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator adding exponential-backoff retries to an async callable.

    Permanent client errors (4xx except 408/429) are never retried.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        retrier = tenacity.AsyncRetrying(
            stop=tenacity.stop_after_attempt(attempts),
            wait=tenacity.wait_exponential(multiplier=initial_wait, max=max_wait),
            retry=_retry_predicate(),
            reraise=True,
        )

        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            async for state in retrier:
                with state:
                    return await func(*args, **kwargs)
            raise RuntimeError(f"retry loop exhausted for {operation}")  # pragma: no cover

        wrapper.__name__ = getattr(func, "__name__", "retry_wrapper")
        return wrapper

    return decorator


def sync_retry[**P, T](
    operation: str,
    *,
    attempts: int = 3,
    initial_wait: float = 0.5,
    max_wait: float = 8.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator adding exponential-backoff retries to a sync callable."""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        retrier = tenacity.Retrying(
            stop=tenacity.stop_after_attempt(attempts),
            wait=tenacity.wait_exponential(multiplier=initial_wait, max=max_wait),
            retry=_retry_predicate(),
            reraise=True,
        )

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return retrier(func, *args, **kwargs)

        wrapper.__name__ = getattr(func, "__name__", "retry_wrapper")
        return wrapper

    return decorator


def call_with_retry[**P, T](
    func: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Invoke *func* with the shared transient-failure retry policy."""
    retrier = tenacity.Retrying(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=0.5, max=8.0),
        retry=_retry_predicate(),
        reraise=True,
    )
    return retrier(func, *args, **kwargs)
