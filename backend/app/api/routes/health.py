"""Health and readiness endpoints."""

from __future__ import annotations

import importlib.util
import time

import httpx
from fastapi import APIRouter, Request

from app import __version__
from app.core.config import Settings, get_settings
from app.core.logging import log_event
from app.models.schemas import DependencyStatus, HealthStatus, ReadinessStatus

router = APIRouter(prefix="/health", tags=["health"])

# Scientific packages the deployment may rely on; checked via importlib spec
# lookup so liveness never triggers heavy imports or side effects.
_OPTIONAL_DEPENDENCIES = ("xarray", "netCDF4", "h5netcdf", "pydap", "argopy")


def _optional_dependency_status() -> dict[str, str]:
    """Report whether each optional scientific package is importable."""
    status: dict[str, str] = {}
    for module in _OPTIONAL_DEPENDENCIES:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            status[module] = "error"
        else:
            status[module] = "available" if found else "missing"
    return status


@router.get(
    "",
    response_model=HealthStatus,
    summary="Liveness probe",
    description=(
        "Basic liveness information for the EchoShield backend, including"
        " optional scientific-dependency availability and whether THREDDS is"
        " configured. Live THREDDS connectivity is probed by /health/ready."
    ),
)
async def health() -> HealthStatus:
    settings = get_settings()
    return HealthStatus(
        status="healthy",
        service=settings.APP_NAME,
        version=__version__,
        environment=settings.APP_ENV,
        optional_dependencies=_optional_dependency_status(),
        thredds_configured=bool(settings.THREDDS_BASE_URL or settings.THREDDS_CATALOG_URL),
    )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    summary="Readiness probe",
    description=(
        "Checks application-local dependencies (configuration, data directory)."
        " External services (THREDDS, INCOIS ERDDAP) are reported explicitly but"
        " do not block readiness when unavailable."
    ),
)
async def ready(request: Request) -> ReadinessStatus:
    settings: Settings = request.app.state.settings
    checks: list[DependencyStatus] = []

    data_dir_ok = settings.DATA_ROOT.is_dir()
    checks.append(
        DependencyStatus(
            name="data_directory",
            status="ok" if data_dir_ok else "unavailable",
            detail=str(settings.DATA_ROOT),
        )
    )

    registered = len(request.app.state.registry.list())
    checks.append(
        DependencyStatus(
            name="dataset_registry",
            status="ok" if registered > 0 else "not_configured",
            detail=f"{registered} datasets registered",
        )
    )

    if settings.THREDDS_BASE_URL or settings.THREDDS_CATALOG_URL:
        url = settings.THREDDS_BASE_URL or ""
        checks.append(await _probe(url or "http://invalid.invalid", "thredds"))
    else:
        checks.append(DependencyStatus(name="thredds", status="not_configured"))

    if settings.INCOIS_ERDDAP_URL:
        checks.append(await _probe(settings.INCOIS_ERDDAP_URL, "incois_erddap"))
    else:
        checks.append(DependencyStatus(name="incois_erddap", status="not_configured"))

    ready_flag = (
        all(check.status != "unavailable" for check in checks if check.name != "thredds")
        and data_dir_ok
    )
    log_event("readiness_checked", ready=ready_flag)
    return ReadinessStatus(ready=ready_flag, service=settings.APP_NAME, checks=checks)


async def _probe(url: str, name: str) -> DependencyStatus:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(url, follow_redirects=True)
        latency = (time.perf_counter() - started) * 1000.0
        ok = response.status_code < 500
        return DependencyStatus(
            name=name,
            status="ok" if ok else "unavailable",
            detail=f"HTTP {response.status_code}",
            latency_ms=round(latency, 1),
        )
    except Exception as exc:  # noqa: BLE001 - readiness must never crash
        latency = (time.perf_counter() - started) * 1000.0
        return DependencyStatus(
            name=name,
            status="unavailable",
            detail=type(exc).__name__,
            latency_ms=round(latency, 1),
        )
