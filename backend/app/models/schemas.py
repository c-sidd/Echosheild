"""Pydantic response models shared across the API.

Every model is JSON-serializable; numeric conversions guarantee that NaN /
infinite values never reach a response (they are mapped to ``None``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DatasetSourceType = Literal[
    "local",
    "thredds",
    "erddap_remote",
    "erddap_tabledap",
]


class CoordinateMetadata(BaseModel):
    name: str
    axis: str | None = None
    units: str | None = None
    size: int
    min_value: float | None = None
    max_value: float | None = None


class VariableMetadata(BaseModel):
    name: str
    long_name: str | None = None
    standard_name: str | None = None
    units: str | None = None
    dimensions: list[str]
    shape: list[int]


class TimeRange(BaseModel):
    start: str
    end: str
    count: int


class DepthRange(BaseModel):
    min_meters: float
    max_meters: float
    count: int
    positive_down: bool = True


class SpatialBounds(BaseModel):
    west: float
    east: float
    south: float
    north: float


class ServiceEndpoints(BaseModel):
    dataset_id: str
    opendap: str | None = None
    erddap_griddap: str | None = None
    erddap_tabledap: str | None = None
    wms: str | None = None
    wcs: str | None = None
    thredds_catalog: str | None = None
    http_download: str | None = None


class DatasetInfo(BaseModel):
    id: str
    title: str
    summary: str | None = None
    source_type: DatasetSourceType = "local"
    time_range: TimeRange | None = None
    spatial_bounds: SpatialBounds | None = None
    services: ServiceEndpoints | None = None


class DatasetMetadata(BaseModel):
    id: str
    title: str
    summary: str | None = None
    source_type: DatasetSourceType = "local"
    dimensions: dict[str, int]
    variables: list[VariableMetadata]
    coordinates: list[CoordinateMetadata]
    global_attributes: dict[str, Any] = Field(default_factory=dict)
    time_range: TimeRange | None = None
    depth_range: DepthRange | None = None
    spatial_bounds: SpatialBounds | None = None
    services: ServiceEndpoints | None = None


class ModelSlice(BaseModel):
    dataset_id: str
    variable: str
    units: str | None = None
    time_index: int | None = None
    time: str | None = None
    depth_meters: float | None = None
    latitude: list[float]
    longitude: list[float]
    # values[i][j] -> latitude i, longitude j (NaN-safe: missing cells are null)
    values: list[list[float | None]]
    downsampling: dict[str, int] = Field(default_factory=dict)


class OceanProfile(BaseModel):
    dataset_id: str
    variable: str
    units: str | None = None
    latitude: float
    longitude: float
    time: str | None = None
    depths_meters: list[float]
    values: list[float | None]


class PointSample(BaseModel):
    dataset_id: str
    latitude: float
    longitude: float
    time: str | None = None
    depth_meters: float | None = None
    nearest_grid: dict[str, float] = Field(default_factory=dict)
    values: dict[str, float | None]
    units: dict[str, str | None]


class CurrentVectorField(BaseModel):
    dataset_id: str
    u_variable: str
    v_variable: str
    units: str | None = None
    time: str | None = None
    depth_meters: float | None = None
    latitude: list[float]
    longitude: list[float]
    u: list[list[float | None]]
    v: list[list[float | None]]
    max_speed_ms: float | None = None


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    # Importability of heavy/optional scientific packages (no side effects).
    optional_dependencies: dict[str, str] = Field(default_factory=dict)
    thredds_configured: bool = False


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "unavailable", "not_configured"]
    detail: str | None = None
    latency_ms: float | None = None


class ReadinessStatus(BaseModel):
    ready: bool
    service: str
    checks: list[DependencyStatus]


class ArgoFloatSummary(BaseModel):
    platform_wmo: int
    cycles: int
    last_location: tuple[float, float] | None = None
    last_time: str | None = None


class ArgoProfilePoint(BaseModel):
    pressure_dbar: float | None = None
    depth_meters: float | None = None
    temperature_c: float | None = None
    salinity_psu: float | None = None


class ArgoProfile(BaseModel):
    platform_wmo: int
    cycle_number: int | None = None
    time: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    points: list[ArgoProfilePoint]


class ArgoFloatDetail(BaseModel):
    platform_wmo: int
    profiles_available: int
    time_range: TimeRange | None = None
    spatial_bounds: SpatialBounds | None = None
    recent_profiles: list[ArgoProfile] = Field(default_factory=list)


class TextParseResult(BaseModel):
    file: str
    delimiter: str
    records_parsed: int
    columns: list[str]
    coordinate_columns: dict[str, str] = Field(default_factory=dict)
    sample_records: list[dict[str, str | None]] = Field(default_factory=list)


# --- Glider -----------------------------------------------------------------


class GliderNotConfigured(BaseModel):
    detail: str
    status: str = "not_configured"
