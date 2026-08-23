"""Model-data service: opens registered datasets and serves slices/profiles."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from functools import partial
from typing import Any, cast

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


class DatasetNotAccessibleError(RuntimeError):
    """Raised when a dataset is listed but has no openable access path."""


class UpstreamUnavailableError(RuntimeError):
    """Raised when a remote scientific service cannot be reached."""


class ModelDataService:
    """Serves model datasets through lazy xarray access with bounded caches."""

    def __init__(self, registry: DatasetRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings
        self._lock = threading.Lock()
        self._open_datasets: OrderedDict[str, xr.Dataset] = OrderedDict()
        self._slice_cache: OrderedDict[tuple[Any, ...], tuple[float, ModelSlice]] = OrderedDict()
        self._max_open = 4
        self._max_slice_cache = 128
        self._slice_cache_ttl = 30 * 60

    def list_datasets(self) -> list[DatasetInfo]:
        return self._registry.list()

    def get_services(self, dataset_id: str) -> ServiceEndpoints:
        return self._registry.get(dataset_id).info.services or ServiceEndpoints(dataset_id=dataset_id)

    def _open(self, entry: RegisteredDataset) -> xr.Dataset:
        with self._lock:
            cached = self._open_datasets.get(entry.info.id)
            if cached is not None:
                self._open_datasets.move_to_end(entry.info.id)
                return cached

        if entry.local_path is not None:
            ds = ncp.open_dataset(entry.local_path)
        elif entry.remote_url is not None:
            try:
                ds = ncp.open_dataset(entry.remote_url, engine=entry.engine or "pydap")
            except ncp.NetCDFParseError as exc:
                raise UpstreamUnavailableError(f"remote dataset {entry.info.id!r} unavailable: {exc}") from exc
        else:
            raise DatasetNotAccessibleError(
                f"dataset {entry.info.id!r} has no accessible data path (metadata-only registration)"
            )

        with self._lock:
            self._open_datasets[entry.info.id] = ds
            while len(self._open_datasets) > self._max_open:
                _, evicted = self._open_datasets.popitem(last=False)
                ncp.close_dataset(evicted)
        return ds

    def close_all(self) -> None:
        with self._lock:
            self._slice_cache.clear()
            while self._open_datasets:
                _, ds = self._open_datasets.popitem()
                ncp.close_dataset(ds)

    def _slice_key(self, dataset_id: str, variable: str, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> tuple[Any, ...]:
        return (
            dataset_id,
            variable,
            time_index,
            round(depth_meters, 6) if depth_meters is not None else None,
            tuple(round(v, 6) for v in bbox) if bbox else None,
        )

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
        ds = self._open(entry)
        metadata = ncp.build_metadata(ds, dataset_id=dataset_id, title=entry.info.title, summary=entry.info.summary, source_type=entry.info.source_type)
        metadata.services = entry.info.services
        metadata.provider = entry.info.provider
        metadata.license = entry.info.license
        return metadata

    def list_variables(self, dataset_id: str) -> list[VariableMetadata]:
        return ncp.list_variables(self._open(self._registry.get(dataset_id)))

    def get_times(self, dataset_id: str) -> list[str]:
        return ncp.get_time_values(self._open(self._registry.get(dataset_id)))

    def get_depths_meters(self, dataset_id: str) -> list[float]:
        return ncp.get_depth_values_meters(self._open(self._registry.get(dataset_id)))

    def get_depth_range(self, dataset_id: str) -> Any:
        return ncp.get_depth_range(self._open(self._registry.get(dataset_id)))

    def get_time_range(self, dataset_id: str) -> Any:
        return ncp.get_time_range(self._open(self._registry.get(dataset_id)))

    def get_extent(self, dataset_id: str) -> DatasetExtent:
        entry = self._registry.get(dataset_id)
        ds = self._open(entry)
        times = ncp.get_time_values(ds)
        if not times:
            raise ValueError(f"dataset {dataset_id!r} has no readable time coordinate")
        cmap = ncp.CoordinateMap(ds)
        return DatasetExtent(
            dataset_id=dataset_id,
            title=entry.info.title,
            source_type=entry.info.source_type,
            time_range=TimeRange(start=times[0], end=times[-1], count=len(times)),
            depth_levels=ncp.get_vertical_values(ds),
            vertical_kind=cmap.vertical_kind,
            vertical_units=cmap.vertical_units,
            spatial_bounds=ncp.get_spatial_bounds(ds),
            variables=[str(name) for name in ds.data_vars],
        )

    def _resolve_variable(self, ds: xr.Dataset, variable: str) -> str:
        if variable in ds.data_vars:
            return variable
        canonical = classify_dataset_variables(ds)
        resolved = canonical.get(cast(CanonicalVariable, variable))
        if resolved is not None:
            return resolved
        raise KeyError(f"unknown variable {variable!r}; available: {sorted(map(str, ds.data_vars))[:20]}")

    def read_slice(self, dataset_id: str, variable: str, *, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> ModelSlice:
        key = self._slice_key(dataset_id, variable, time_index, depth_meters, bbox)
        cached = self._cached_slice(key)
        if cached is not None:
            _LOG.debug("slice_cache_hit dataset=%s variable=%s", dataset_id, variable)
            return cached

        ds = self._open(self._registry.get(dataset_id))
        slice_ = ncp.read_slice(
            ds,
            self._resolve_variable(ds, variable),
            time_index=time_index,
            depth_meters=depth_meters,
            bbox=bbox,
            max_grid_points=self._settings.MAX_GRID_POINTS,
        )
        slice_.dataset_id = dataset_id
        _LOG.info("slice dataset=%s variable=%s points=%d cache=miss", dataset_id, variable, len(slice_.latitude) * len(slice_.longitude))
        return self._store_slice(key, slice_)

    def read_profile(self, dataset_id: str, variable: str, *, latitude: float, longitude: float, time_index: int | None) -> OceanProfile:
        ds = self._open(self._registry.get(dataset_id))
        profile = ncp.read_profile(ds, self._resolve_variable(ds, variable), latitude=latitude, longitude=longitude, time_index=time_index, max_points=self._settings.MAX_PROFILE_POINTS)
        profile.dataset_id = dataset_id
        return profile

    def read_point(self, dataset_id: str, variables: list[str], *, latitude: float, longitude: float, time_index: int | None, depth_meters: float | None) -> PointSample:
        ds = self._open(self._registry.get(dataset_id))
        sample = ncp.read_point(ds, [self._resolve_variable(ds, v) for v in variables], latitude=latitude, longitude=longitude, time_index=time_index, depth_meters=depth_meters)
        sample.dataset_id = dataset_id
        return sample

    def read_currents(self, dataset_id: str, *, time_index: int | None, depth_meters: float | None, bbox: tuple[float, float, float, float] | None) -> CurrentVectorField | CurrentsUnavailable:
        detected = self.detect_current_variables(dataset_id)
        if detected is None:
            return CurrentsUnavailable(dataset_id=dataset_id, reason="Current vector variables are not available in this dataset.")
        u_name, v_name = detected
        ds = self._open(self._registry.get(dataset_id))
        u_slice = ncp.read_slice(ds, u_name, time_index=time_index, depth_meters=depth_meters, bbox=bbox, max_grid_points=self._settings.MAX_GRID_POINTS // 2)
        v_slice = ncp.read_slice(ds, v_name, time_index=time_index, depth_meters=depth_meters, bbox=bbox, max_grid_points=self._settings.MAX_GRID_POINTS // 2)
        max_speed: float | None = None
        for row_u, row_v in zip(u_slice.values, v_slice.values, strict=False):
            for value_u, value_v in zip(row_u, row_v, strict=False):
                if value_u is None or value_v is None:
                    continue
                speed_sq = value_u * value_u + value_v * value_v
                if max_speed is None or speed_sq > max_speed:
                    max_speed = speed_sq
        return CurrentVectorField(
            dataset_id=dataset_id,
            u_variable=u_name,
            v_variable=v_name,
            units=u_slice.units or v_slice.units,
            time=u_slice.time,
            depth_meters=u_slice.depth_meters,
            latitude=u_slice.latitude,
            longitude=u_slice.longitude,
            u=u_slice.values,
            v=v_slice.values,
            max_speed_ms=round(max_speed**0.5, 6) if max_speed is not None else None,
        )

    def detect_current_variables(self, dataset_id: str) -> tuple[str, str] | None:
        ds = self._open(self._registry.get(dataset_id))
        canonical = classify_dataset_variables(ds)
        u_name = canonical.get("u_current")
        v_name = canonical.get("v_current")
        return (u_name, v_name) if u_name is not None and v_name is not None else None

    async def read_slice_batch(self, dataset_id: str, requests: list[SliceRequest]) -> list[ModelSlice]:
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None,
                partial(self.read_slice, dataset_id, request.variable, time_index=request.time_index, depth_meters=request.depth_meters, bbox=request.bbox()),
            )
            for request in requests
        ]
        return list(await asyncio.gather(*tasks))
