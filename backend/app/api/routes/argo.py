"""Argo observation API."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query, Request

from app.ingestion.argo_client import ArgoClient, ArgoClientError
from app.models.schemas import ArgoFloatDetail, ArgoFloatSummary, ArgoProfile

router = APIRouter(prefix="/argo", tags=["argo"])

# Floats surface every ~10 days; anything silent for months is not "active".
# Bounding the default window keeps upstream bulk queries small enough to
# finish well inside request timeouts (an unbounded Indian-Ocean region
# download exceeds any sane HTTP budget).
_ACTIVE_WINDOW_DAYS = 90


def _default_start() -> str:
    return (date.today() - timedelta(days=_ACTIVE_WINDOW_DAYS)).isoformat()


class UpstreamUnavailable(RuntimeError):
    """Mapped to HTTP 503 by the global exception handlers."""


def _client(request: Request) -> ArgoClient:
    client: ArgoClient = request.app.state.argo_client
    return client


@router.get(
    "/floats",
    response_model=list[ArgoFloatSummary],
    summary="Search Argo floats",
    description=(
        "Search active floats in a geographic box (defaults to the Indian"
        " Ocean). Without explicit start/end only floats reporting within"
        " the last 90 days are returned, keeping upstream queries fast;"
        " failures return HTTP 503 with a clear error."
    ),
    responses={503: {"description": "Argo upstream unavailable"}},
)
def search_floats(
    request: Request,
    lon_min: float = Query(default=50.0, ge=-180, le=180),
    lon_max: float = Query(default=100.0, ge=-180, le=180),
    lat_min: float = Query(default=-10.0, ge=-90, le=90),
    lat_max: float = Query(default=30.0, ge=-90, le=90),
    start: str | None = Query(default=None, examples=["2024-01-01"]),
    end: str | None = Query(default=None),
    max_floats: int = Query(default=50, ge=1, le=500),
) -> list[ArgoFloatSummary]:
    if lon_min >= lon_max:
        raise ValueError("lon_min must be less than lon_max")
    if lat_min >= lat_max:
        raise ValueError("lat_min must be less than lat_max")
    if start is None and end is None:
        start = _default_start()
    try:
        return _client(request).search_floats(
            lon_min=lon_min,
            lon_max=lon_max,
            lat_min=lat_min,
            lat_max=lat_max,
            start=start,
            end=end,
            max_floats=max_floats,
        )
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc


@router.get(
    "/{float_id}",
    response_model=ArgoFloatDetail,
    summary="Float detail with recent profiles",
    responses={
        404: {"description": "Unknown float"},
        503: {"description": "Argo upstream unavailable"},
    },
)
def float_detail(
    float_id: int,
    request: Request,
    max_profiles: int = Query(default=5, ge=1, le=20),
) -> ArgoFloatDetail:
    if not 1000 <= float_id <= 9_999_999:
        raise ValueError(f"implausible WMO id {float_id}")
    try:
        return _client(request).float_detail(float_id, max_profiles=max_profiles)
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc


@router.get(
    "/{float_id}/profile",
    response_model=ArgoProfile,
    summary="One profile (latest or by cycle)",
    responses={
        404: {"description": "Unknown float/cycle"},
        503: {"description": "Argo upstream unavailable"},
    },
)
def float_profile(
    float_id: int,
    request: Request,
    cycle: int | None = Query(default=None, ge=0),
) -> ArgoProfile:
    try:
        return _client(request).float_profile(float_id, cycle=cycle)
    except ArgoClientError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise KeyError(message) from exc
        raise UpstreamUnavailable(message) from exc


@router.get(
    "/search",
    response_model=list[ArgoFloatSummary],
    summary="Keyword-free region/time search alias",
    description="Alias of ``/floats`` kept for frontend convenience.",
    responses={503: {"description": "Argo upstream unavailable"}},
)
def search_alias(
    request: Request,
    lon_min: float = Query(default=50.0, ge=-180, le=180),
    lon_max: float = Query(default=100.0, ge=-180, le=180),
    lat_min: float = Query(default=-10.0, ge=-90, le=90),
    lat_max: float = Query(default=30.0, ge=-90, le=90),
) -> list[ArgoFloatSummary]:
    try:
        return _client(request).search_floats(
            lon_min=lon_min,
            lon_max=lon_max,
            lat_min=lat_min,
            lat_max=lat_max,
            start=_default_start(),
        )
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
