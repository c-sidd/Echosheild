"""Pydantic response models shared across the API.

Every model is JSON-serializable; numeric conversions guarantee that NaN /
infinite values never reach a response (they are mapped to ``None``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DatasetSourceType = Literal["local", "thredds", "erddap_remote", "erddap_tabledap"]
VerticalKind = Literal["depth", "pressure", "other"]

class CurrentsUnavailable(BaseModel):
    dataset_id: str
    available: Literal[False] = False
    reason: str

class CoordinateMetadata(BaseModel):
    name: str
    axis: str | None = None
    units: str | None = None
    size: int
    min_value: float | None = None
    max_value: float | None = None

class VariableMetadata(BaseModel):
    name: str
    canonical_name: str | None = None
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
    vertical_kind: VerticalKind = "depth"
    vertical_units: str | None = None

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
    provider: str | None = None
    license: str | None = None
    enabled: bool = True
    metadata_path: str | None = None
    time_range: TimeRange | None = None
    spatial_bounds: SpatialBounds | None = None
    services: ServiceEndpoints | None = None

class DatasetMetadata(BaseModel):
    id: str
    title: str
    summary: str | None = None
    source_type: DatasetSourceType = "local"
    provider: str | None = None
    license: str | None = None
    dimensions: dict[str, int]
    variables: list[VariableMetadata]
    coordinates: list[CoordinateMetadata]
    coordinate_mapping: dict[str, str] = Field(default_factory=dict)
    global_attributes: dict[str, Any] = Field(default_factory=dict)
    time_range: TimeRange | None = None
    depth_range: DepthRange | None = None
    spatial_bounds: SpatialBounds | None = None
    services: ServiceEndpoints | None = None

class ModelSlice(BaseModel):
    dataset_id: str
    variable: str
    canonical_name: str | None = None
    units: str | None = None
    time_index: int | None = None
    time: str | None = None
    depth_meters: float | None = None
    vertical_kind: VerticalKind | None = None
    vertical_units: str | None = None
    latitude: list[float]
    longitude: list[float]
    values: list[list[float | None]]
    downsampling: dict[str, int] = Field(default_factory=dict)

class TimestampEntry(BaseModel):
    index: int
    iso: str

class SliceRequest(BaseModel):
    variable: str
    time_index: int | None = Field(default=None, ge=0)
    depth_meters: float | None = None
    west: float | None = Field(default=None, ge=-180, le=360)
    east: float | None = Field(default=None, ge=-180, le=360)
    south: float | None = Field(default=None, ge=-90, le=90)
    north: float | None = Field(default=None, ge=-90, le=90)

    def bbox(self) -> tuple[float, float, float, float] | None:
        values = [self.west, self.east, self.south, self.north]
        if all(v is None for v in values):
            return None
        if any(v is None for v in values):
            raise ValueError("bbox requires all of west, east, south and north")
        assert self.west is not None and self.east is not None
        assert self.south is not None and self.north is not None
        if not (-180 <= self.west < self.east <= 360):
            raise ValueError(f"invalid longitude bounds: west={self.west}, east={self.east}")
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError(f"invalid latitude bounds: south={self.south}, north={self.north}")
        return (self.west, self.east, self.south, self.north)

class SliceBatchRequest(BaseModel):
    slices: list[SliceRequest] = Field(..., min_length=1, max_length=10)

class DatasetExtent(BaseModel):
    dataset_id: str
    title: str | None = None
    source_type: DatasetSourceType = "local"
    time_range: TimeRange
    depth_levels: list[float]
    vertical_kind: VerticalKind = "depth"
    vertical_units: str | None = None
    spatial_bounds: SpatialBounds | None = None
    variables: list[str]

class OceanProfile(BaseModel):
    dataset_id: str
    variable: str
    canonical_name: str | None = None
    units: str | None = None
    latitude: float
    longitude: float
    time: str | None = None
    depths_meters: list[float]
    vertical_kind: VerticalKind = "depth"
    vertical_units: str | None = None
    values: list[float | None]

class PointSample(BaseModel):
    dataset_id: str
    latitude: float
    longitude: float
    time: str | None = None
    depth_meters: float | None = None
    vertical_kind: VerticalKind = "depth"
    vertical_units: str | None = None
    nearest_grid: dict[str, float] = Field(default_factory=dict)
    values: dict[str, float | None]
    units: dict[str, str | None]

class CurrentVectorField(BaseModel):
    dataset_id: str
    available: Literal[True] = True
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

class GliderNotConfigured(BaseModel):
    detail: str
    status: str = "not_configured"

class GliderMissionSummary(BaseModel):
    mission_id: str
    latitude: float | None = None
    longitude: float | None = None
    last_time: str | None = None
    profiles: int = 0
    source: str | None = None

class GliderProfilePoint(BaseModel):
    time: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    depth_meters: float | None = None
    temperature_c: float | None = None
    salinity_psu: float | None = None
    chlorophyll: float | None = None

class GliderMission(BaseModel):
    mission_id: str
    source: str
    points: list[GliderProfilePoint]
