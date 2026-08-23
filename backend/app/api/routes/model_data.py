"""Ocean model data API (local NetCDF + remote THREDDS / ERDDAP griddap)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.models.schemas import (
    CurrentsUnavailable,
    CurrentVectorField,
    DatasetExtent,
    DatasetInfo,
    DatasetMetadata,
    ModelSlice,
    OceanProfile,
    PointSample,
    ServiceEndpoints,
    SliceBatchRequest,
    TimeRange,
    TimestampEntry,
    VariableMetadata,
)
from app.services.dataset_registry import RegisteredDataset
from app.services.model_service import (
    DatasetNotAccessibleError,
    ModelDataService,
    UpstreamUnavailableError,
)

router = APIRouter(prefix="/model", tags=["model-data"])


def _service(request: Request) -> ModelDataService:
    service: ModelDataService = request.app.state.model_service
    return service


def _parse_bbox(
    west: float | None = None,
    east: float | None = None,
    south: float | None = None,
    north: float | None = None,
) -> tuple[float, float, float, float] | None:
    values = [west, east, south, north]
    if all(v is None for v in values):
        return None
    if any(v is None for v in values):
        raise ValueError("bbox requires all of west, east, south and north")
    assert west is not None and east is not None and south is not None and north is not None
    if not (-180 <= west < east <= 360):
        raise ValueError(f"invalid longitude bounds: west={west}, east={east}")
    if not (-90 <= south < north <= 90):
        raise ValueError(f"invalid latitude bounds: south={south}, north={north}")
    return (west, east, south, north)


@router.get(
    "/datasets",
    response_model=list[DatasetInfo],
    summary="List registered datasets",
    description=(
        "All datasets registered with EchoShield: local sample NetCDF files,"
        " INCOIS ERDDAP products discovered from ISO 19115 metadata, and"
        " THREDDS catalog entries when a THREDDS server is configured."
    ),
)
def list_datasets(request: Request) -> list[DatasetInfo]:
    return _service(request).list_datasets()


@router.get(
    "/{dataset_id}/metadata",
    response_model=DatasetMetadata,
    summary="Dataset metadata",
    description="Dimensions, variables, coordinates, attributes, time/depth ranges.",
    responses={
        404: {"description": "Unknown dataset"},
        503: {"description": "Remote dataset unavailable"},
    },
)
def get_metadata(dataset_id: str, request: Request) -> DatasetMetadata:
    return _service(request).get_metadata(dataset_id)


@router.get(
    "/{dataset_id}/variables",
    response_model=list[VariableMetadata],
    summary="List dataset variables",
    responses={404: {"description": "Unknown dataset"}},
)
def list_variables(dataset_id: str, request: Request) -> list[VariableMetadata]:
    return _service(request).list_variables(dataset_id)


@router.get(
    "/{dataset_id}/times",
    response_model=TimeRange,
    summary="Time axis",
    description="First/last timestep (ISO-8601) and the number of timesteps.",
    responses={404: {"description": "Unknown dataset"}},
)
def get_times(dataset_id: str, request: Request) -> TimeRange:
    times = _service(request).get_times(dataset_id)
    if not times:
        raise ValueError(f"dataset {dataset_id!r} has no time coordinate")
    return TimeRange(start=times[0], end=times[-1], count=len(times))


_MAX_TIMES_LIST = 2000


@router.get(
    "/{dataset_id}/times/list",
    response_model=list[str],
    summary="Full ISO-8601 time axis as a flat array",
    description=(
        "Every decoded timestep in order (index i ↔ response[i])."
        f" Capped at {_MAX_TIMES_LIST} entries; use ``/timestamps`` for the"
        " index-paired form."
    ),
    responses={404: {"description": "Unknown dataset"}},
)
def list_times(dataset_id: str, request: Request) -> list[str]:
    times = _service(request).get_times(dataset_id)
    if not times:
        raise ValueError(f"dataset {dataset_id!r} has no time coordinate")
    return times[:_MAX_TIMES_LIST]


@router.get(
    "/{dataset_id}/timestamps",
    response_model=list[TimestampEntry],
    summary="Time axis as explicit (index, ISO-8601) pairs",
    description=(
        "Explicit index↔timestamp mapping for scrubbers and deep-links;"
        f" capped at {_MAX_TIMES_LIST} entries."
    ),
    responses={404: {"description": "Unknown dataset"}},
)
def list_timestamps(dataset_id: str, request: Request) -> list[TimestampEntry]:
    times = _service(request).get_times(dataset_id)
    if not times:
        raise ValueError(f"dataset {dataset_id!r} has no time coordinate")
    return [
        TimestampEntry(index=index, iso=value)
        for index, value in enumerate(times[:_MAX_TIMES_LIST])
    ]


@router.get(
    "/{dataset_id}/extent",
    response_model=DatasetExtent,
    summary="Single-call startup extent",
    description=(
        "Complete renderable envelope — full time range, every vertical"
        " level, the lat/lon footprint and available variables — so the UI"
        " initialises without opening the dataset."
    ),
    responses={
        404: {"description": "Unknown dataset"},
        503: {"description": "Remote dataset unavailable"},
    },
)
def get_extent(dataset_id: str, request: Request) -> DatasetExtent:
    return _service(request).get_extent(dataset_id)


@router.get(
    "/{dataset_id}/depths",
    response_model=list[float],
    summary="Vertical axis values (native units)",
    description=(
        "Values in native vertical units. Interpret them via"
        " metadata.vertical_kind: 'depth' (meters), 'pressure' (e.g. dbar)"
        " or 'other'. No unit conversion is applied."
    ),
    responses={404: {"description": "Unknown dataset"}},
)
def get_depths(dataset_id: str, request: Request) -> list[float]:
    depths = _service(request).get_depths_meters(dataset_id)
    if not depths:
        raise ValueError(f"dataset {dataset_id!r} has no depth coordinate")
    return depths


@router.get(
    "/{dataset_id}/slice",
    response_model=ModelSlice,
    summary="Horizontal 2-D slice",
    description=(
        "One timestep (optionally depth-resolved) as a lat/lon grid."
        " Grids larger than MAX_GRID_POINTS are automatically downsampled;"
        " missing cells are null."
    ),
    responses={
        404: {"description": "Unknown dataset or variable"},
        422: {"description": "Invalid parameters"},
    },
)
def read_slice(
    dataset_id: str,
    request: Request,
    variable: str = Query(..., examples=["temperature"]),
    time_index: int | None = Query(
        default=None, ge=0, description="Timestep index (defaults to 0)"
    ),
    depth: float | None = Query(default=None, description="Nearest depth level in meters"),
    west: float | None = Query(default=None, ge=-180, le=360),
    east: float | None = Query(default=None, ge=-180, le=360),
    south: float | None = Query(default=None, ge=-90, le=90),
    north: float | None = Query(default=None, ge=-90, le=90),
) -> ModelSlice:
    bbox = _parse_bbox(west, east, south, north)
    return _service(request).read_slice(
        dataset_id,
        variable,
        time_index=time_index,
        depth_meters=depth,
        bbox=bbox,
    )


@router.get(
    "/{dataset_id}/profile",
    response_model=OceanProfile,
    summary="Vertical profile at nearest grid point",
    responses={404: {"description": "Unknown dataset or variable"}},
)
def read_profile(
    dataset_id: str,
    request: Request,
    variable: str = Query(..., examples=["temperature"]),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=360),
    time_index: int | None = Query(default=None, ge=0),
) -> OceanProfile:
    return _service(request).read_profile(
        dataset_id,
        variable,
        latitude=latitude,
        longitude=longitude,
        time_index=time_index,
    )


@router.get(
    "/{dataset_id}/point",
    response_model=PointSample,
    summary="Point sample for one or more variables",
    responses={404: {"description": "Unknown dataset or variable"}},
)
def read_point(
    dataset_id: str,
    request: Request,
    variables: str = Query(
        ..., examples=["temperature,salinity"], description="Comma-separated variable names"
    ),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=360),
    time_index: int | None = Query(default=None, ge=0),
    depth: float | None = Query(default=None),
) -> PointSample:
    names = [name.strip() for name in variables.split(",") if name.strip()]
    if not names or len(names) > 8:
        raise ValueError("provide between 1 and 8 variable names")
    return _service(request).read_point(
        dataset_id,
        names,
        latitude=latitude,
        longitude=longitude,
        time_index=time_index,
        depth_meters=depth,
    )


@router.post(
    "/{dataset_id}/slice/batch",
    response_model=list[ModelSlice],
    summary="Fetch several horizontal slices in one round-trip",
    description=(
        "Body: {\"slices\": [{variable, time_index?, depth_meters?,"
        " west/east/south/north?}, ...]} — at most 10 per batch. Slices are"
        " read concurrently off the event loop and returned in request order."
    ),
    responses={
        404: {"description": "Unknown dataset or variable"},
        422: {"description": "Invalid parameters"},
    },
)
async def read_slice_batch(
    dataset_id: str,
    request: Request,
    body: SliceBatchRequest,
) -> list[ModelSlice]:
    # Validate every bbox up-front so malformed requests fail before any I/O.
    for item in body.slices:
        item.bbox()
    return await _service(request).read_slice_batch(dataset_id, list(body.slices))


@router.get(
    "/{dataset_id}/currents",
    response_model=CurrentVectorField | CurrentsUnavailable,
    summary="Horizontal current vector field (u, v)",
    description=(
        "Metadata-detected (u, v) pair. Datasets without currents return"
        ' 200 with {"available": false, "reason": ...} — never fabricated data.'
    ),
    responses={404: {"description": "Unknown dataset"}},
)
def read_currents(
    dataset_id: str,
    request: Request,
    time_index: int | None = Query(default=None, ge=0),
    depth: float | None = Query(default=None),
    west: float | None = Query(default=None, ge=-180, le=360),
    east: float | None = Query(default=None, ge=-180, le=360),
    south: float | None = Query(default=None, ge=-90, le=90),
    north: float | None = Query(default=None, ge=-90, le=90),
) -> CurrentVectorField | CurrentsUnavailable:
    bbox = _parse_bbox(west, east, south, north)
    return _service(request).read_currents(
        dataset_id,
        time_index=time_index,
        depth_meters=depth,
        bbox=bbox,
    )


@router.get(
    "/{dataset_id}/services",
    response_model=ServiceEndpoints,
    summary="Scientific service endpoints for a dataset",
    description=(
        "OPeNDAP / WMS / WCS / ERDDAP URLs when available. The frontend should"
        " use these URLs directly; FastAPI does not proxy full WMS/WCS payloads."
    ),
    responses={
        404: {"description": "Unknown dataset"},
        503: {"description": "Metadata-only dataset"},
    },
)
def get_services(dataset_id: str, request: Request) -> ServiceEndpoints:
    entry: RegisteredDataset = request.app.state.registry.get(dataset_id)
    services = entry.info.services
    if services is None:
        raise UpstreamUnavailableError(f"dataset {dataset_id!r} exposes no scientific services")
    advertised = [
        field
        for field in ServiceEndpoints.model_fields
        if field != "dataset_id" and getattr(services, field)
    ]
    if not advertised:
        raise UpstreamUnavailableError(f"dataset {dataset_id!r} exposes no scientific services")
    return services


__all__ = ["router", "DatasetNotAccessibleError"]
