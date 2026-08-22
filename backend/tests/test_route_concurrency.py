"""Guard: blocking route handlers must be threadpool-dispatched, never on the loop.

xarray / argopy / remote-HTTP calls inside the model and argo handlers are
synchronous. Declaring those handlers ``async def`` would run them directly
on the event loop and stall *every* concurrent request while one upstream is
slow (observed live against INCOIS ERDDAP). These endpoints must stay plain
``def`` so FastAPI dispatches them to its worker threadpool.
"""

from __future__ import annotations

import inspect

from fastapi.routing import APIRoute

from app.main import create_app


def test_blocking_endpoints_are_threadpool_dispatched(settings) -> None:  # noqa: ANN001
    app = create_app(settings)
    offenders = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and (route.path.startswith("/api/v1/model") or route.path.startswith("/api/v1/argo"))
        and inspect.iscoroutinefunction(route.endpoint)
    ]
    assert offenders == []
