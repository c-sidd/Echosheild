"""Argo observation API."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query, Request

from app.ingestion.argo_client import ArgoClient, ArgoClientError
from app.models.schemas import ArgoFloatDetail, ArgoFloatSummary, ArgoProfile
from app.services.comparison import ModelObservationComparison, compare_profile

router = APIRouter(prefix="/argo", tags=["argo"])
_ACTIVE_WINDOW_DAYS = 90


def _default_start() -> str:
    return (date.today() - timedelta(days=_ACTIVE_WINDOW_DAYS)).isoformat()


class UpstreamUnavailable(RuntimeError):
    """Mapped to HTTP 503 by the global exception handlers."""


def _client(request: Request) -> ArgoClient:
    client: ArgoClient = request.app.state.argo_client
    return client


@router.get("/floats", response_model=list[ArgoFloatSummary], summary="Search Argo floats", responses={503: {"description": "Argo upstream unavailable"}})
def search_floats(
    request: Request,
    lon_min: float = Query(default=50.0, ge=-180, le=180),
    lon_max: float = Query(default=100.0, ge=-180, le=180),
    lat_min: float = Query(default=-10.0, ge=-90, le=90),
    lat_max: float = Query(default=30.0, ge=-90, le=90),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    max_floats: int = Query(default=50, ge=1, le=500),
) -> list[ArgoFloatSummary]:
    if lon_min >= lon_max or lat_min >= lat_max:
        raise ValueError("invalid geographic bounds")
    if start is None and end is None:
        start = _default_start()
    try:
        return _client(request).search_floats(lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max, start=start, end=end, max_floats=max_floats)
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc


@router.get("/{float_id}", response_model=ArgoFloatDetail, summary="Float detail with recent profiles", responses={404: {"description": "Unknown float"}, 503: {"description": "Argo upstream unavailable"}})
def float_detail(request: Request, float_id: int, max_profiles: int = Query(default=5, ge=1, le=20)) -> ArgoFloatDetail:
    if not 1000 <= float_id <= 9_999_999:
        raise ValueError(f"implausible WMO id {float_id}")
    try:
        return _client(request).float_detail(float_id, max_profiles=max_profiles)
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc


@router.get("/{float_id}/profile", response_model=ArgoProfile, summary="One profile (latest or by cycle)", responses={404: {"description": "Unknown float/cycle"}, 503: {"description": "Argo upstream unavailable"}})
def float_profile(request: Request, float_id: int, cycle: int | None = Query(default=None, ge=0)) -> ArgoProfile:
    try:
        return _client(request).float_profile(float_id, cycle=cycle)
    except ArgoClientError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise KeyError(message) from exc
        raise UpstreamUnavailable(message) from exc


@router.get(
    "/{float_id}/compare",
    response_model=ModelObservationComparison,
    summary="Compare an Argo profile against the selected model",
    description=(
        "Matches the Argo profile to the nearest model timestep, samples the"
        " model at the float location and depth levels, and returns paired"
        " temperature/salinity errors plus bias, MAE and RMSE."
    ),
)
def compare_float(
    request: Request,
    float_id: int,
    dataset_id: str = Query(default="incois_argo_mnt_VAM"),
    cycle: int | None = Query(default=None, ge=0),
) -> ModelObservationComparison:
    try:
        profile = _client(request).float_profile(float_id, cycle=cycle)
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
    return compare_profile(request.app.state.model_service, dataset_id, profile)


@router.get("/search", response_model=list[ArgoFloatSummary], summary="Keyword-free region/time search alias", responses={503: {"description": "Argo upstream unavailable"}})
def search_alias(request: Request, lon_min: float = Query(default=50.0, ge=-180, le=180), lon_max: float = Query(default=100.0, ge=-180, le=180), lat_min: float = Query(default=-10.0, ge=-90, le=90), lat_max: float = Query(default=30.0, ge=-90, le=90)) -> list[ArgoFloatSummary]:
    try:
        return _client(request).search_floats(lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max, start=_default_start())
    except ArgoClientError as exc:
        raise UpstreamUnavailable(str(exc)) from exc
