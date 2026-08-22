"""Structured application logging setup."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.core.config import get_settings

_LOG = logging.getLogger("echoshield")

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    """Configure root logging once, honouring settings.LOG_LEVEL."""
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT, stream=sys.stdout)
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, level))


def log_event(message: str, /, **fields: object) -> None:
    """Emit a structured event line: ``message key=value ...``."""
    parts = [message] + [f"{key}={value}" for key, value in fields.items() if value is not None]
    _LOG.info(" ".join(parts))


def add_request_logging_middleware(app: FastAPI) -> None:
    """Register lightweight request/duration logging middleware."""

    @app.middleware("http")
    async def _log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            _LOG.exception(
                "request_failed path=%s method=%s duration_ms=%.1f",
                request.url.path,
                request.method,
                duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000.0
        _LOG.info(
            "request path=%s method=%s status=%d duration_ms=%.1f",
            request.url.path,
            request.method,
            response.status_code,
            duration_ms,
        )
        return response
