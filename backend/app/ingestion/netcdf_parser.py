"""xarray-based NetCDF ingestion utilities.

All functions operate lazily on ``xarray.Dataset`` objects; nothing loads an
entire dataset into memory unless a small, capped subset is materialised.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from app.ingestion.variable_mapping import (
    ResolvedCoordinates,
    VerticalKind,
    classify_variable,
    resolve_coordinates,
)
from app.models.schemas import (
    CoordinateMetadata,
    DatasetMetadata,
    DepthRange,
    ModelSlice,
    OceanProfile,
    PointSample,
    SpatialBounds,
    TimeRange,
    VariableMetadata,
)

_LOG = logging.getLogger("echoshield.netcdf")

ALLOWED_SUFFIXES = {".nc", ".nc4", ".cdf"}


class NetCDFParseError(ValueError):
    """Raised when a dataset cannot be interpreted as expected."""


def validate_local_source(source: str | Path) -> Path:
    """Validate a local NetCDF path without allowing arbitrary file access."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"dataset file not found: {path}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES and not path.is_dir():
        raise NetCDFParseError(
            f"unsupported dataset format {path.suffix!r}; expected one of {sorted(ALLOWED_SUFFIXES)}"
        )
    return path


def open_dataset(
    source: str | Path,
    *,
    engine: str | None = None,
    decode_times: bool = True,
) -> xr.Dataset:
    """Open a NetCDF/Zarr dataset lazily (local file or remote URL).

    The caller owns the returned dataset and must close/release it.
    """
    source_str = str(source)
    if not source_str.startswith(("http://", "https://")):
        source_str = str(validate_local_source(Path(source)))
    try:
        ds = xr.open_dataset(source_str, engine=engine, decode_times=decode_times)
    except Exception as exc:  # noqa: BLE001 - surfaced as domain error
        raise NetCDFParseError(f"failed to open dataset {source_str}: {exc}") from exc
    _LOG.info("dataset_opened source=%s engine=%s", source_str, engine or "auto")
    return ds


def close_dataset(ds: xr.Dataset | None) -> None:
    """Release dataset resources safely."""
    if ds is not None:
        try:
            ds.close()
        except Exception:  # noqa: BLE001 - best-effort release
            _LOG.debug("dataset_close_failed", exc_info=True)


def find_coordinate(ds: xr.Dataset, candidates: Iterable[str]) -> str | None:
    names_lower = {str(name).lower(): str(name) for name in ds.variables}
    for candidate in candidates:
        if candidate in names_lower:
            return names_lower[candidate]
    return None


class CoordinateMap:
    """Detected coordinate variables for a dataset (metadata-driven)."""

    def __init__(self, ds: xr.Dataset) -> None:
        self.resolved: ResolvedCoordinates = resolve_coordinates(ds)
        self.time = self.resolved.time
        self.lat = self.resolved.latitude
        self.lon = self.resolved.longitude
        self.vertical = self.resolved.vertical
        # Backwards-compatible alias; ``vertical_kind`` is authoritative.
        self.depth = self.vertical

    @property
    def vertical_kind(self) -> VerticalKind:
        return self.resolved.vertical_kind

    @property
    def vertical_units(self) -> str | None:
        return self.resolved.vertical_units


def get_dimensions(ds: xr.Dataset) -> dict[str, int]:
    return {str(name): int(size) for name, size in ds.sizes.items()}


def list_variables(ds: xr.Dataset) -> list[VariableMetadata]:
    coords = set(map(str, ds.coords))
    excluded_prefixes = ("lat_bnds", "lon_bnds")
    out: list[VariableMetadata] = []
    for name, da in ds.data_vars.items():
        name_str = str(name)
        if name_str in coords or name_str.startswith(excluded_prefixes):
            continue
        attrs = da.attrs
        canonical = classify_variable(
            name_str,
            {str(k).lower(): str(v) for k, v in attrs.items() if isinstance(v, (str, int, float))},
        )
        out.append(
            VariableMetadata(
                name=name_str,
                canonical_name=canonical,
                long_name=_safe_str(attrs.get("long_name")),
                standard_name=_safe_str(attrs.get("standard_name")),
                units=_safe_str(attrs.get("units")),
                dimensions=[str(d) for d in da.dims],
                shape=[int(s) for s in da.shape],
            )
        )
    return out


def get_coordinates(ds: xr.Dataset) -> list[CoordinateMetadata]:
    cmap = CoordinateMap(ds)
    out: list[CoordinateMetadata] = []
    for name in (cmap.time, cmap.depth, cmap.lat, cmap.lon):
        if name is None:
            continue
        da = ds[name]
        values = np.asarray(da.values).ravel()
        numeric = pd.to_numeric(values, errors="coerce") if values.dtype.kind not in "M" else None
        min_v = (
            float(np.nanmin(numeric))
            if numeric is not None and numeric.size and not np.isnan(numeric).all()
            else None
        )
        max_v = (
            float(np.nanmax(numeric))
            if numeric is not None and numeric.size and not np.isnan(numeric).all()
            else None
        )
        out.append(
            CoordinateMetadata(
                name=name,
                axis=_axis_for(name, cmap),
                units=_safe_str(da.attrs.get("units"))
                or (
                    "degrees_north"
                    if name == cmap.lat
                    else "degrees_east"
                    if name == cmap.lon
                    else None
                ),
                size=int(da.size),
                min_value=min_v,
                max_value=max_v,
            )
        )
    return out


def _axis_for(name: str, cmap: CoordinateMap) -> str | None:
    if name == cmap.time:
        return "T"
    if name == cmap.depth:
        return "Z"
    if name == cmap.lat:
        return "Y"
    if name == cmap.lon:
        return "X"
    return None


def get_time_values(ds: xr.Dataset) -> list[str]:
    cmap = CoordinateMap(ds)
    if cmap.time is None:
        return []
    return [_to_iso(v) for v in np.asarray(ds[cmap.time].values).ravel()]


def get_time_range(ds: xr.Dataset) -> TimeRange | None:
    values = get_time_values(ds)
    if not values:
        return None
    return TimeRange(start=values[0], end=values[-1], count=len(values))


def get_vertical_values(ds: xr.Dataset) -> list[float]:
    """Vertical coordinate values in their NATIVE units (no conversion).

    For pressure coordinates the values are pressure (e.g. dbar); callers
    must label them using :func:`get_vertical_kind` / ``vertical_units``.
    Only sign normalisation is applied: height-above-surface storage
    (negative-up depth) is flipped to positive-down.
    """
    cmap = CoordinateMap(ds)
    if cmap.vertical is None:
        return []
    raw = np.asarray(ds[cmap.vertical].values).ravel().astype(float)
    if cmap.resolved.vertical_kind == "depth" and raw.size and float(raw.min()) < 0:
        # Height above surface (negative-down values): flip to positive-down.
        raw = -raw
    return sorted(float(v) for v in raw if math.isfinite(v))


def get_vertical_kind(ds: xr.Dataset) -> VerticalKind:
    cmap = CoordinateMap(ds)
    return cmap.vertical_kind


def get_depth_values_meters(ds: xr.Dataset) -> list[float]:
    """Backwards-compatible alias of :func:`get_vertical_values`.

    Historical name retained; values are native-unit vertical coordinates
    (see ``vertical_kind`` on responses — pressure is *not* converted).
    """
    return get_vertical_values(ds)


def get_depth_range(ds: xr.Dataset) -> DepthRange | None:
    values = get_vertical_values(ds)
    if not values:
        return None
    cmap = CoordinateMap(ds)
    positive_down = True
    if cmap.vertical is not None:
        raw_min = float(np.nanmin(np.asarray(ds[cmap.vertical].values).ravel().astype(float)))
        positive_down = raw_min >= 0
    return DepthRange(
        min_meters=values[0],
        max_meters=values[-1],
        count=len(values),
        positive_down=positive_down,
        vertical_kind=cmap.vertical_kind,
        vertical_units=cmap.vertical_units,
    )


def get_spatial_bounds(ds: xr.Dataset) -> SpatialBounds | None:
    cmap = CoordinateMap(ds)
    if cmap.lat is None or cmap.lon is None:
        return None
    lats = np.asarray(ds[cmap.lat].values).ravel().astype(float)
    lons = np.asarray(ds[cmap.lon].values).ravel().astype(float)
    lats_f = [v for v in lats if math.isfinite(v)]
    lons_f = [v for v in lons if math.isfinite(v)]
    if not lats_f or not lons_f:
        return None
    return SpatialBounds(
        west=min(lons_f),
        east=max(lons_f),
        south=min(lats_f),
        north=max(lats_f),
    )


def build_metadata(
    ds: xr.Dataset,
    *,
    dataset_id: str,
    title: str | None = None,
    summary: str | None = None,
    source_type: str = "local",
) -> DatasetMetadata:
    attrs = {str(k): _attr_to_json(v) for k, v in list(ds.attrs.items())[:40] if isinstance(k, str)}
    resolved_title = title or _safe_str(ds.attrs.get("title")) or dataset_id
    cmap = CoordinateMap(ds)
    return DatasetMetadata(
        id=dataset_id,
        title=resolved_title,
        summary=summary or _safe_str(ds.attrs.get("summary")),
        source_type=source_type,  # type: ignore[arg-type]
        dimensions=get_dimensions(ds),
        variables=list_variables(ds),
        coordinates=get_coordinates(ds),
        coordinate_mapping=cmap.resolved.mapping,
        global_attributes=attrs,
        time_range=get_time_range(ds),
        depth_range=get_depth_range(ds),
        spatial_bounds=get_spatial_bounds(ds),
    )


# --- Data extraction --------------------------------------------------------


def read_slice(
    ds: xr.Dataset,
    variable: str,
    *,
    time_index: int | None = None,
    depth_meters: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    max_grid_points: int = 100_000,
) -> ModelSlice:
    """Extract one horizontal 2-D slice, capped at ``max_grid_points`` cells."""
    if variable not in ds.data_vars:
        raise KeyError(
            f"unknown variable {variable!r}; available: {sorted(map(str, ds.data_vars))[:20]}"
        )
    cmap = CoordinateMap(ds)
    da = ds[variable]

    time_iso: str | None = None
    if cmap.time is not None and cmap.time in da.dims:
        n_times = int(ds.sizes[cmap.time])
        idx = time_index if time_index is not None else 0
        if not 0 <= idx < n_times:
            raise IndexError(f"time_index {idx} out of range [0, {n_times - 1}]")
        da = da.isel({cmap.time: idx})
        time_iso = _to_iso(np.asarray(ds[cmap.time].values).ravel()[idx])

    depth_used: float | None = None
    if cmap.vertical is not None and cmap.vertical in da.dims:
        verticals = get_vertical_values(ds)
        if depth_meters is None:
            vertical_idx = 0
        else:
            if not verticals:
                raise NetCDFParseError("dataset has a vertical coordinate but no readable values")
            vertical_idx = int(
                min(range(len(verticals)), key=lambda i: abs(verticals[i] - depth_meters))
            )
        actual = np.asarray(ds[cmap.vertical].values).ravel()[vertical_idx]
        depth_used = float(actual)
        da = da.isel({cmap.vertical: vertical_idx})

    lon_name, lat_name = cmap.lon, cmap.lat
    if (
        lon_name is not None
        and lon_name in da.dims
        and lat_name is not None
        and lat_name in da.dims
    ):
        lons_all = np.asarray(ds[lon_name].values).ravel().astype(float)
        lats_all = np.asarray(ds[lat_name].values).ravel().astype(float)
        lon_slice: slice = slice(0, None)
        lat_slice: slice = slice(0, None)
        if bbox is not None:
            west, east, south, north = (float(v) for v in bbox)
            lon_slice = slice(west, east) if lons_all[0] <= lons_all[-1] else slice(east, west)
            lat_slice = slice(south, north) if lats_all[0] <= lats_all[-1] else slice(north, south)
            da = da.sel({lon_name: lon_slice, lat_name: lat_slice})
        n_lat, n_lon = int(da.sizes[lat_name]), int(da.sizes[lon_name])
        total = n_lat * n_lon
        stride_y = stride_x = 1
        while total / (stride_y * stride_x) > max_grid_points:
            if stride_x <= stride_y:
                stride_x += 1
            else:
                stride_y += 1
            total = max(1, (n_lat // stride_y + 1) * (n_lon // stride_x + 1))
        if stride_x > 1 or stride_y > 1:
            da = da.isel(
                {lat_name: slice(None, None, stride_y), lon_name: slice(None, None, stride_x)}
            )

        lats = [float(v) for v in np.asarray(da[lat_name].values).ravel()]
        lons = [float(v) for v in np.asarray(da[lon_name].values).ravel()]
        values = _nan_safe_matrix(np.asarray(da.values, dtype=float))
    else:
        lats = []
        lons = []
        values = [[_finite_or_none(float(np.asarray(da.values).ravel()[0]))]]
        stride_y = stride_x = 1

    units = _safe_str(ds[variable].attrs.get("units"))
    downsampling: dict[str, int] = {}
    if stride_y > 1 or stride_x > 1:
        downsampling = {"latitude_stride": stride_y, "longitude_stride": stride_x}
    return ModelSlice(
        dataset_id="",
        variable=variable,
        canonical_name=_canonical_of(ds, variable),
        units=units,
        time_index=time_index,
        time=time_iso,
        depth_meters=depth_used,
        vertical_kind=cmap.vertical_kind if cmap.vertical is not None else None,
        vertical_units=cmap.vertical_units,
        latitude=lats,
        longitude=lons,
        values=values,
        downsampling=downsampling,
    )


def read_profile(
    ds: xr.Dataset,
    variable: str,
    *,
    latitude: float,
    longitude: float,
    time_index: int | None = None,
    max_points: int = 500,
) -> OceanProfile:
    """Extract a vertical profile at the grid point nearest (lat, lon)."""
    if variable not in ds.data_vars:
        raise KeyError(f"unknown variable {variable!r}")
    cmap = CoordinateMap(ds)
    if cmap.lat is None or cmap.lon is None:
        raise NetCDFParseError("dataset has no latitude/longitude coordinates")
    da = ds[variable]

    time_iso: str | None = None
    if cmap.time is not None and cmap.time in da.dims:
        n_times = int(ds.sizes[cmap.time])
        idx = time_index if time_index is not None else 0
        if not 0 <= idx < n_times:
            raise IndexError(f"time_index {idx} out of range [0, {n_times - 1}]")
        da = da.isel({cmap.time: idx})
        time_iso = _to_iso(np.asarray(ds[cmap.time].values).ravel()[idx])

    da = da.sel({cmap.lat: latitude, cmap.lon: longitude}, method="nearest")
    if cmap.vertical is not None and cmap.vertical in da.dims:
        verticals_all = np.asarray(ds[cmap.vertical].values).ravel()
        step = max(1, int(da.sizes[cmap.vertical]) // max_points)
        da = da.isel({cmap.vertical: slice(None, None, step)})
        verticals_raw = np.asarray(verticals_all)[::step]
        vals = [_finite_or_none(float(v)) for v in np.asarray(da.values, dtype=float).ravel()]
    else:
        verticals_raw = np.asarray([0.0])
        vals = [_finite_or_none(float(np.asarray(da.values, dtype=float).ravel()[0]))]

    return OceanProfile(
        dataset_id="",
        variable=variable,
        canonical_name=_canonical_of(ds, variable),
        units=_safe_str(ds[variable].attrs.get("units")),
        latitude=float(da[cmap.lat].values) if cmap.lat in da.coords else latitude,
        longitude=float(da[cmap.lon].values) if cmap.lon in da.coords else longitude,
        time=time_iso,
        depths_meters=[float(v) for v in verticals_raw],
        vertical_kind=cmap.vertical_kind,
        vertical_units=cmap.vertical_units,
        values=vals,
    )


def read_point(
    ds: xr.Dataset,
    variables: list[str],
    *,
    latitude: float,
    longitude: float,
    time_index: int | None = None,
    depth_meters: float | None = None,
) -> PointSample:
    """Extract nearest-grid scalar values for several variables."""
    cmap = CoordinateMap(ds)
    values: dict[str, float | None] = {}
    units: dict[str, str | None] = {}
    nearest: dict[str, float] = {}
    time_iso: str | None = None
    depth_used: float | None = None

    first_da: Any = None
    for variable in variables:
        if variable not in ds.data_vars:
            raise KeyError(f"unknown variable {variable!r}")
        da = ds[variable]
        if cmap.time is not None and cmap.time in da.dims:
            n_times = int(ds.sizes[cmap.time])
            idx = time_index if time_index is not None else 0
            if not 0 <= idx < n_times:
                raise IndexError(f"time_index {idx} out of range [0, {n_times - 1}]")
            da = da.isel({cmap.time: idx})
            if first_da is None:
                time_iso = _to_iso(np.asarray(ds[cmap.time].values).ravel()[idx])
        if (
            cmap.lat is not None
            and cmap.lat in da.dims
            and cmap.lon is not None
            and cmap.lon in da.dims
        ):
            da = da.sel({cmap.lat: latitude, cmap.lon: longitude}, method="nearest")
            if first_da is None:
                nearest["latitude"] = float(da[cmap.lat].values)
                nearest["longitude"] = float(da[cmap.lon].values)
        if cmap.vertical is not None and cmap.vertical in da.dims:
            verticals = np.asarray(ds[cmap.vertical].values).ravel().astype(float)
            target = depth_meters if depth_meters is not None else float(verticals[0])
            vertical_idx = int(min(range(len(verticals)), key=lambda i: abs(verticals[i] - target)))
            da = da.isel({cmap.vertical: vertical_idx})
            if first_da is None:
                depth_used = float(verticals[vertical_idx])
        raw = float(np.asarray(da.values).ravel()[0])
        values[variable] = _finite_or_none(raw)
        units[variable] = _safe_str(ds[variable].attrs.get("units"))
        if first_da is None:
            first_da = da

    return PointSample(
        dataset_id="",
        latitude=latitude,
        longitude=longitude,
        time=time_iso,
        depth_meters=depth_used,
        vertical_kind=cmap.vertical_kind,
        vertical_units=cmap.vertical_units,
        nearest_grid=nearest,
        values=values,
        units=units,
    )


# --- helpers ----------------------------------------------------------------


def _canonical_of(ds: xr.Dataset, variable: str) -> str | None:
    da = ds.get(variable)
    if da is None:
        return None
    attrs = {
        str(k).lower(): str(v) for k, v in da.attrs.items() if isinstance(v, (str, int, float))
    }
    canonical = classify_variable(variable, attrs)
    return str(canonical) if canonical else None


def _finite_or_none(value: float) -> float | None:
    value_f = float(value)
    return value_f if math.isfinite(value_f) else None


def _nan_safe_matrix(arr: np.ndarray) -> list[list[float | None]]:
    matrix = arr.astype(float)
    if matrix.ndim == 1:
        matrix = matrix[np.newaxis, :]
    return [[_finite_or_none(value) for value in row] for row in matrix.tolist()]


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_iso(value: object) -> str:
    if isinstance(value, np.datetime64):
        return str(pd.Timestamp(value).isoformat())
    if isinstance(value, pd.Timestamp):
        return str(value.isoformat())
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return str(iso())
    return str(value)


def _attr_to_json(value: object) -> Any:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    array = getattr(value, "tolist", None)
    if callable(array):
        try:
            return array()
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)
