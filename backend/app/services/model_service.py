"""Model-data service: opens registered datasets and serves slices/profiles."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any, cast

import numpy as np
import xarray as xr

from app.core.config import Settings
from app.ingestion import netcdf_parser as ncp
from app.ingestion.variable_mapping import CanonicalVariable, classify_dataset_variables
from app.models.schemas import (
    CurrentsUnavailable,
    CurrentVectorField,
    DatasetExtent,
    DatasetInfo,
    DatasetMetadata,
    DepthRange,
    ModelSlice,
    OceanProfile,
    PointSample,
    ServiceEndpoints,
    SliceRequest,
    TimeRange,
    VariableMetadata,
)
from app.services.dataset_registry import DatasetRegistry, RegisteredDataset

_LOG = logging.getLogger("echoshield.model")

_OPEN_WAIT_TIMEOUT: float | None = None


class DatasetNotAccessibleError(RuntimeError):
    """Raised when a dataset is listed but has no openable access path."""


class UpstreamUnavailableError(RuntimeError):
    """Raised when a remote scientific service cannot be reached."""


class _Handle:
    """A leased xarray dataset shared by concurrent readers.

    ``refs`` counts active leases. Eviction detaches the handle from the
    cache immediately but the underlying dataset is only closed once the
    last lease is released, so no reader can ever observe a closed file.
    """

    __slots__ = ("closed", "dataset_id", "ds", "evicted", "lock", "refs")

    def __init__(self, dataset_id: str, ds: xr.Dataset) -> None:
        self.dataset_id = dataset_id
        self.ds = ds
        self.lock = threading.Lock()
        self.refs = 1
        self.evicted = False
        self.closed = False


class _OpenFlight:
    """Single-flight coordinator: exactly one thread opens, others wait."""

    __slots__ = ("error", "event")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.error: BaseException | None = None


class ModelDataService:
    """Serves model datasets through lazy xarray access with bounded caches."""

    def __init__(self, registry: DatasetRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings
        self._lock = threading.Lock()
        self._handles: OrderedDict[str, _Handle] = OrderedDict()
        self._flights: dict[str, _OpenFlight] = {}
        self._shutting_down = False
        self._slice_cache: OrderedDict[tuple[Any, ...], tuple[float, ModelSlice]] = OrderedDict()
        self._max_open = 4
        self._max_slice_cache = 128
        self._slice_cache_ttl = 30 * 60

    def list_datasets(self) -> list[DatasetInfo]:
        return self._registry.list()

    def get_services(self, dataset_id: str) -> ServiceEndpoints:
        return self._registry.get(dataset_id).info.services or ServiceEndpoints(dataset_id=dataset_id)

    def _open_source(self, entry: RegisteredDataset) -> xr.Dataset:
        if entry.local_path is not None:
            return ncp.open_dataset(entry.local_path)
        if entry.remote_url is not None:
            try:
                return ncp.open_dataset(entry.remote_url, engine=entry.engine or "pydap")
            except ncp.NetCDFParseError as exc:
                raise UpstreamUnavailableError(f"remote dataset {entry.info.id!r} unavailable: {exc}") from exc
        raise DatasetNotAccessibleError(f"dataset {entry.info.id!r} has no accessible data path (metadata-only registration)")

    def _acquire(self, entry: RegisteredDataset) -> _Handle:
        dataset_id = entry.info.id
        while True:
            with self._lock:
                handle = self._handles.get(dataset_id)
                if handle is not None and not handle.evicted:
                    handle.refs += 1
                    self._handles.move_to_end(dataset_id)
                    return handle
                flight = self._flights.get(dataset_id)
                if flight is None:
                    flight = _OpenFlight()
                    self._flights[dataset_id] = flight
                    owner = True
                else:
                    owner = False
            if owner:
                return self._open_handle(entry, flight)
            if not flight.event.wait(_OPEN_WAIT_TIMEOUT):
                raise UpstreamUnavailableError(f"timed out waiting for dataset {dataset_id!r} to open")
            if flight.error is not None:
                raise flight.error

    def _open_handle(self, entry: RegisteredDataset, flight: _OpenFlight) -> _Handle:
        dataset_id = entry.info.id
        try:
            ds = self._open_source(entry)
        except BaseException as exc:
            with self._lock:
                flight.error = exc
                self._flights.pop(dataset_id, None)
            flight.event.set()
            raise
        victims: list[_Handle] = []
        with self._lock:
            handle = _Handle(dataset_id, ds)
            if self._shutting_down:
                handle.evicted = True
            else:
                self._handles[dataset_id] = handle
                while len(self._handles) > self._max_open:
                    _, victim = self._handles.popitem(last=False)
                    victim.evicted = True
                    if victim.refs <= 0 and not victim.closed:
                        victim.closed = True
                        victims.append(victim)
            self._flights.pop(dataset_id, None)
        flight.event.set()
        for victim in victims:
            self._close_dataset(victim.dataset_id, victim.ds)
        return handle

    def _release(self, handle: _Handle) -> None:
        close_now = False
        with self._lock:
            handle.refs -= 1
            if handle.refs <= 0 and handle.evicted and not handle.closed:
                handle.closed = True
                close_now = True
        if close_now:
            self._close_dataset(handle.dataset_id, handle.ds)

    def _close_dataset(self, dataset_id: str, ds: xr.Dataset) -> None:
        try:
            ncp.close_dataset(ds)
        except Exception:
            _LOG.warning("failed to close dataset %s", dataset_id, exc_info=True)

    @contextmanager
    def _reading(self, dataset_id: str) -> Iterator[xr.Dataset]:
        """Lease a dataset handle for one read.

        Yields the raw dataset under the per-handle read lock: the engines
        behind xarray (netCDF4/HDF5, pydap sessions) are not thread-safe, so
        every touch of a shared handle is serialised while independent
        datasets remain fully concurrent.
        """
        handle = self._acquire(self._registry.get(dataset_id))
        try:
            with handle.lock:
                yield handle.ds
        finally:
            self._release(handle)

    def close_all(self) -> None:
        doomed: list[_Handle] = []
        with self._lock:
            self._shutting_down = True
            self._slice_cache.clear()
            while self._handles:
                _, handle = self._handles.popitem()
                handle.evicted = True
                if handle.refs <= 0 and not handle.closed:
                    handle.closed = True
                    doomed.append(handle)
        for handle in doomed:
            self._close_dataset(handle.dataset_id, handle.ds)

    def _slice_key(self, dataset_id: str, variable: str, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> tuple[Any, ...]:
        return (dataset_id, variable, time_index, round(depth_meters, 6) if depth_meters is not None else None, tuple(round(v, 6) for v in bbox) if bbox else None)

    def _cached_slice(self, key: tuple[Any, ...]) -> ModelSlice | None:
        now = time.monotonic()
        with self._lock:
            item = self._slice_cache.get(key)
            if item is None:
                return None
            created, value = item
            if now - created > self._slice_cache_ttl:
                self._slice_cache.pop(key, None)
                return None
            self._slice_cache.move_to_end(key)
            return value.model_copy(deep=True)

    def _store_slice(self, key: tuple[Any, ...], value: ModelSlice) -> ModelSlice:
        with self._lock:
            self._slice_cache[key] = (time.monotonic(), value.model_copy(deep=True))
            self._slice_cache.move_to_end(key)
            while len(self._slice_cache) > self._max_slice_cache:
                self._slice_cache.popitem(last=False)
        return value

    def get_metadata(self, dataset_id: str) -> DatasetMetadata:
        entry = self._registry.get(dataset_id)
        with self._reading(dataset_id) as ds:
            metadata = ncp.build_metadata(ds, dataset_id=dataset_id, title=entry.info.title, summary=entry.info.summary, source_type=entry.info.source_type)
            metadata.services = entry.info.services
            metadata.provider = entry.info.provider
            metadata.license = entry.info.license
            return metadata

    def list_variables(self, dataset_id: str) -> list[VariableMetadata]:
        with self._reading(dataset_id) as ds:
            return ncp.list_variables(ds)

    def get_times(self, dataset_id: str) -> list[str]:
        with self._reading(dataset_id) as ds:
            return ncp.get_time_values(ds)

    def get_depths_meters(self, dataset_id: str) -> list[float]:
        with self._reading(dataset_id) as ds:
            return ncp.get_depth_values_meters(ds)

    def get_depth_range(self, dataset_id: str) -> Any:
        with self._reading(dataset_id) as ds:
            return ncp.get_depth_range(ds)

    def get_vertical_kind(self, dataset_id: str) -> str:
        """Vertical axis kind ('depth' | 'pressure' | 'other') for the dataset."""
        depth_range = cast("DepthRange | None", self.get_depth_range(dataset_id))
        return str(depth_range.vertical_kind) if depth_range is not None else "other"

    def get_time_range(self, dataset_id: str) -> Any:
        with self._reading(dataset_id) as ds:
            return ncp.get_time_range(ds)

    def get_extent(self, dataset_id: str) -> DatasetExtent:
        entry = self._registry.get(dataset_id)
        with self._reading(dataset_id) as ds:
            times = ncp.get_time_values(ds)
            if not times:
                raise ValueError(f"dataset {dataset_id!r} has no readable time coordinate")
            cmap = ncp.CoordinateMap(ds)
            return DatasetExtent(dataset_id=dataset_id, title=entry.info.title, source_type=entry.info.source_type, time_range=TimeRange(start=times[0], end=times[-1], count=len(times)), depth_levels=ncp.get_vertical_values(ds), vertical_kind=cmap.vertical_kind, vertical_units=cmap.vertical_units, spatial_bounds=ncp.get_spatial_bounds(ds), variables=[str(name) for name in ds.data_vars])

    def _resolve_variable(self, ds: xr.Dataset, variable: str) -> str:
        if variable in ds.data_vars:
            return variable
        resolved = classify_dataset_variables(ds).get(cast(CanonicalVariable, variable))
        if resolved is not None:
            return resolved
        raise KeyError(f"unknown variable {variable!r}; available: {sorted(map(str, ds.data_vars))[:20]}")

    @staticmethod
    def _sorted_vertical_view(ds: xr.Dataset) -> xr.Dataset:
        """Return a lazy dataset whose vertical coordinate is monotonic positive-down.

        ``netcdf_parser.read_slice`` historically sorted depth values but then
        indexed the original coordinate array. A descending source axis could
        therefore return the wrong physical depth. Sorting the xarray view first
        keeps the parser's index and coordinate ordering identical without
        loading the data into memory. Height-above-surface axes (negative-up
        storage) are additionally sign-normalised to positive-down so every
        consumer (slice, profile, point) matches against identical values;
        coordinate attributes are preserved and ``positive`` is inverted to
        stay truthful about the stored convention.
        """
        cmap = ncp.CoordinateMap(ds)
        if cmap.vertical is None or cmap.vertical not in ds.dims:
            return ds
        coord = ds[cmap.vertical]
        raw = np.asarray(coord.values).ravel().astype(float)
        if raw.size < 2:
            return ds
        sign_flip = cmap.vertical_kind == "depth" and bool(np.nanmin(raw) < 0)
        normalized = -raw if sign_flip else raw
        order = np.argsort(normalized, kind="stable")
        needs_permutation = not np.array_equal(order, np.arange(raw.size))
        if not needs_permutation and not sign_flip:
            return ds
        view = ds.isel({cmap.vertical: order}) if needs_permutation else ds
        if sign_flip:
            flipped = -view[cmap.vertical]
            attrs = dict(flipped.attrs)
            if attrs.get("positive") == "up":
                attrs["positive"] = "down"
            elif attrs.get("positive") == "down":
                attrs["positive"] = "up"
            flipped.attrs = attrs
            view = view.assign_coords({cmap.vertical: flipped})
        return view

    def read_slice(self, dataset_id: str, variable: str, *, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> ModelSlice:
        key = self._slice_key(dataset_id, variable, time_index, depth_meters, bbox)
        cached = self._cached_slice(key)
        if cached is not None:
            return cached
        with self._reading(dataset_id) as ds:
            ds_for_slice = self._sorted_vertical_view(ds)
            slice_ = ncp.read_slice(ds_for_slice, self._resolve_variable(ds_for_slice, variable), time_index=time_index, depth_meters=depth_meters, bbox=bbox, max_grid_points=self._settings.MAX_GRID_POINTS)
            # Parser returns the native coordinate value. For a normalized depth
            # view, expose the positive-down value consistently to the browser.
            if slice_.depth_meters is not None and ncp.CoordinateMap(ds_for_slice).vertical_kind == "depth" and slice_.depth_meters < 0:
                slice_.depth_meters = -slice_.depth_meters
            slice_.dataset_id = dataset_id
        _LOG.info("slice dataset=%s variable=%s points=%d cache=miss", dataset_id, variable, len(slice_.latitude) * len(slice_.longitude))
        return self._store_slice(key, slice_)

    def read_profile(self, dataset_id: str, variable: str, *, latitude: float, longitude: float, time_index: int | None) -> OceanProfile:
        with self._reading(dataset_id) as ds:
            ds_sorted = self._sorted_vertical_view(ds)
            profile = ncp.read_profile(ds_sorted, self._resolve_variable(ds_sorted, variable), latitude=latitude, longitude=longitude, time_index=time_index, max_points=self._settings.MAX_PROFILE_POINTS)
            profile.dataset_id = dataset_id
            return profile

    def read_point(self, dataset_id: str, variables: list[str], *, latitude: float, longitude: float, time_index: int | None, depth_meters: float | None) -> PointSample:
        with self._reading(dataset_id) as ds:
            ds_sorted = self._sorted_vertical_view(ds)
            sample = ncp.read_point(ds_sorted, [self._resolve_variable(ds_sorted, v) for v in variables], latitude=latitude, longitude=longitude, time_index=time_index, depth_meters=depth_meters)
            sample.dataset_id = dataset_id
            return sample

    def read_currents(self, dataset_id: str, *, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> CurrentVectorField | CurrentsUnavailable:
        detected = self.detect_current_variables(dataset_id)
        if detected is None:
            return CurrentsUnavailable(dataset_id=dataset_id, reason="Current vector variables are not available in this dataset.")
        u_name, v_name = detected
        with self._reading(dataset_id) as ds:
            ds_for_slice = self._sorted_vertical_view(ds)
            u_slice = ncp.read_slice(ds_for_slice, u_name, time_index=time_index, depth_meters=depth_meters, bbox=bbox, max_grid_points=self._settings.MAX_GRID_POINTS // 2)
            v_slice = ncp.read_slice(ds_for_slice, v_name, time_index=time_index, depth_meters=depth_meters, bbox=bbox, max_grid_points=self._settings.MAX_GRID_POINTS // 2)
        max_speed: float | None = None
        for row_u, row_v in zip(u_slice.values, v_slice.values, strict=False):
            for value_u, value_v in zip(row_u, row_v, strict=False):
                if value_u is None or value_v is None:
                    continue
                speed_sq = value_u * value_u + value_v * value_v
                if max_speed is None or speed_sq > max_speed:
                    max_speed = speed_sq
        units = u_slice.units or v_slice.units
        speed_ms = round(max_speed**0.5, 6) if max_speed is not None else None
        if units and "cm" in units.lower():
            speed_ms = round((max_speed**0.5) / 100, 6) if max_speed is not None else None
        return CurrentVectorField(dataset_id=dataset_id, u_variable=u_name, v_variable=v_name, units=units, time=u_slice.time, depth_meters=u_slice.depth_meters, latitude=u_slice.latitude, longitude=u_slice.longitude, u=u_slice.values, v=v_slice.values, max_speed_ms=speed_ms)

    def detect_current_variables(self, dataset_id: str) -> tuple[str, str] | None:
        with self._reading(dataset_id) as ds:
            canonical = classify_dataset_variables(ds)
        u_name = canonical.get("u_current")
        v_name = canonical.get("v_current")
        return (u_name, v_name) if u_name is not None and v_name is not None else None

    async def read_slice_batch(self, dataset_id: str, requests: list[SliceRequest]) -> list[ModelSlice]:
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(None, partial(self.read_slice, dataset_id, request.variable, time_index=request.time_index, depth_meters=request.depth_meters, bbox=request.bbox())) for request in requests]
        return list(await asyncio.gather(*tasks))
