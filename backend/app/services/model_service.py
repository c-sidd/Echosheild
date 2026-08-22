"""Model-data service: opens registered datasets and serves slices/profiles."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any

import xarray as xr

from app.core.config import Settings
from app.ingestion import netcdf_parser as ncp
from app.ingestion.variable_mapping import classify_dataset_variables
from app.models.schemas import (
    CurrentsUnavailable,
    CurrentVectorField,
    DatasetInfo,
    DatasetMetadata,
    ModelSlice,
    OceanProfile,
    PointSample,
    ServiceEndpoints,
    VariableMetadata,
)
from app.services.dataset_registry import DatasetRegistry, RegisteredDataset

_LOG = logging.getLogger("echoshield.model")


class DatasetNotAccessibleError(RuntimeError):
    """Raised when a dataset is listed but has no openable access path."""


class UpstreamUnavailableError(RuntimeError):
    """Raised when a remote scientific service cannot be reached."""


class ModelDataService:
    """Serves model datasets through lazy xarray access with an LRU cache."""

    def __init__(self, registry: DatasetRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings
        self._lock = threading.Lock()
        self._open_datasets: OrderedDict[str, xr.Dataset] = OrderedDict()
        self._max_open = 4

    # -- dataset lifecycle ---------------------------------------------------

    def list_datasets(self) -> list[DatasetInfo]:
        return self._registry.list()

    def get_services(self, dataset_id: str) -> ServiceEndpoints:
        return self._registry.get(dataset_id).info.services or ServiceEndpoints(
            dataset_id=dataset_id
        )

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
                raise UpstreamUnavailableError(
                    f"remote dataset {entry.info.id!r} unavailable: {exc}"
                ) from exc
        else:
            raise DatasetNotAccessibleError(
                f"dataset {entry.info.id!r} has no accessible data path"
                " (metadata-only registration)"
            )

        with self._lock:
            self._open_datasets[entry.info.id] = ds
            while len(self._open_datasets) > self._max_open:
                _, evicted = self._open_datasets.popitem(last=False)
                ncp.close_dataset(evicted)
        return ds

    def close_all(self) -> None:
        with self._lock:
            while self._open_datasets:
                _, ds = self._open_datasets.popitem()
                ncp.close_dataset(ds)

    # -- metadata endpoints --------------------------------------------------

    def get_metadata(self, dataset_id: str) -> DatasetMetadata:
        entry = self._registry.get(dataset_id)
        ds = self._open(entry)
        metadata = ncp.build_metadata(
            ds,
            dataset_id=dataset_id,
            title=entry.info.title,
            summary=entry.info.summary,
            source_type=entry.info.source_type,
        )
        metadata.services = entry.info.services
        metadata.provider = entry.info.provider
        metadata.license = entry.info.license
        return metadata

    def list_variables(self, dataset_id: str) -> list[VariableMetadata]:
        ds = self._open(self._registry.get(dataset_id))
        return ncp.list_variables(ds)

    def get_times(self, dataset_id: str) -> list[str]:
        ds = self._open(self._registry.get(dataset_id))
        return ncp.get_time_values(ds)

    def get_depths_meters(self, dataset_id: str) -> list[float]:
        ds = self._open(self._registry.get(dataset_id))
        return ncp.get_depth_values_meters(ds)

    def get_depth_range(self, dataset_id: str) -> Any:
        ds = self._open(self._registry.get(dataset_id))
        return ncp.get_depth_range(ds)

    def get_time_range(self, dataset_id: str) -> Any:
        ds = self._open(self._registry.get(dataset_id))
        return ncp.get_time_range(ds)

    # -- data extraction -----------------------------------------------------

    def read_slice(
        self,
        dataset_id: str,
        variable: str,
        *,
        time_index: int | None,
        depth_meters: float | None,
        bbox: tuple[float, float, float, float] | None,
    ) -> ModelSlice:
        ds = self._open(self._registry.get(dataset_id))
        slice_ = ncp.read_slice(
            ds,
            variable,
            time_index=time_index,
            depth_meters=depth_meters,
            bbox=bbox,
            max_grid_points=self._settings.MAX_GRID_POINTS,
        )
        slice_.dataset_id = dataset_id
        _LOG.info(
            "slice dataset=%s variable=%s points=%d",
            dataset_id,
            variable,
            len(slice_.latitude) * len(slice_.longitude),
        )
        return slice_

    def read_profile(
        self,
        dataset_id: str,
        variable: str,
        *,
        latitude: float,
        longitude: float,
        time_index: int | None,
    ) -> OceanProfile:
        ds = self._open(self._registry.get(dataset_id))
        profile = ncp.read_profile(
            ds,
            variable,
            latitude=latitude,
            longitude=longitude,
            time_index=time_index,
            max_points=self._settings.MAX_PROFILE_POINTS,
        )
        profile.dataset_id = dataset_id
        return profile

    def read_point(
        self,
        dataset_id: str,
        variables: list[str],
        *,
        latitude: float,
        longitude: float,
        time_index: int | None,
        depth_meters: float | None,
    ) -> PointSample:
        ds = self._open(self._registry.get(dataset_id))
        sample = ncp.read_point(
            ds,
            variables,
            latitude=latitude,
            longitude=longitude,
            time_index=time_index,
            depth_meters=depth_meters,
        )
        sample.dataset_id = dataset_id
        return sample

    def read_currents(
        self,
        dataset_id: str,
        *,
        time_index: int | None,
        depth_meters: float | None,
        bbox: tuple[float, float, float, float] | None,
    ) -> CurrentVectorField | CurrentsUnavailable:
        detected = self.detect_current_variables(dataset_id)
        if detected is None:
            return CurrentsUnavailable(
                dataset_id=dataset_id,
                reason="Current vector variables are not available in this dataset.",
            )
        u_name, v_name = detected
        ds = self._open(self._registry.get(dataset_id))
        u_slice = ncp.read_slice(
            ds,
            u_name,
            time_index=time_index,
            depth_meters=depth_meters,
            bbox=bbox,
            max_grid_points=self._settings.MAX_GRID_POINTS // 2,
        )
        v_slice = ncp.read_slice(
            ds,
            v_name,
            time_index=time_index,
            depth_meters=depth_meters,
            bbox=bbox,
            max_grid_points=self._settings.MAX_GRID_POINTS // 2,
        )

        max_speed: float | None = None
        for row_u, row_v in zip(u_slice.values, v_slice.values, strict=False):
            for value_u, value_v in zip(row_u, row_v, strict=False):
                if value_u is None or value_v is None:
                    continue
                speed_sq = value_u * value_u + value_v * value_v
                if max_speed is None or speed_sq > max_speed:
                    max_speed = speed_sq
        units = u_slice.units or v_slice.units
        return CurrentVectorField(
            dataset_id=dataset_id,
            u_variable=u_name,
            v_variable=v_name,
            units=units,
            time=u_slice.time,
            depth_meters=u_slice.depth_meters,
            latitude=u_slice.latitude,
            longitude=u_slice.longitude,
            u=u_slice.values,
            v=v_slice.values,
            max_speed_ms=round(max_speed**0.5, 6) if max_speed is not None else None,
        )

    def detect_current_variables(self, dataset_id: str) -> tuple[str, str] | None:
        """Return the ``(u, v)`` source-variable pair, or ``None``.

        Detection is metadata-driven (CF standard names first, then known
        naming conventions). Datasets that genuinely lack currents yield
        ``None`` — no data is ever fabricated.
        """
        ds = self._open(self._registry.get(dataset_id))
        canonical = classify_dataset_variables(ds)
        u_name = canonical.get("u_current")
        v_name = canonical.get("v_current")
        if u_name is None or v_name is None:
            return None
        return u_name, v_name
