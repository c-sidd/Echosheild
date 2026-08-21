"""Dataset discovery and registration.

Datasets are *registered* by ID — API requests can never open arbitrary
server paths. Sources discovered here:

* local sample NetCDF files under ``NETCDF_DATA_ROOT``,
* ISO 19115 metadata records under ``DATA_ROOT`` (real INCOIS products),
* optionally THREDDS catalog entries when configured.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.ingestion.iso19115_parser import scan_metadata_directory
from app.ingestion.thredds_client import ThreddsClient, build_erddap_griddap_urls
from app.models.schemas import DatasetInfo, SpatialBounds, TimeRange

_LOG = logging.getLogger("echoshield.registry")


@dataclass(frozen=True)
class RegisteredDataset:
    """Internal registry entry linking an ID to its physical access path."""

    info: DatasetInfo
    local_path: Path | None = None
    remote_url: str | None = None  # OPeNDAP / ERDDAP-griddap URL for xarray
    engine: str | None = None

    @property
    def accessible(self) -> bool:
        return self.local_path is not None or self.remote_url is not None


class DatasetRegistry:
    """Loads and exposes registered datasets by ID."""

    def __init__(self, settings: Settings, thredds_client: ThreddsClient | None = None) -> None:
        self._settings = settings
        self._thredds = thredds_client
        self._datasets: dict[str, RegisteredDataset] = {}

    # -- discovery -----------------------------------------------------------

    def discover(self) -> int:
        """Discover local + ISO19115 datasets (sync part of startup)."""
        count = self._discover_local_netcdf()
        count += self._discover_iso19115()
        _LOG.info("registry_discovered total=%d", count)
        return count

    def _register(self, entry: RegisteredDataset) -> None:
        existing = self._datasets.get(entry.info.id)
        if existing is None or not existing.accessible:
            self._datasets[entry.info.id] = entry

    def _discover_local_netcdf(self) -> int:
        root = self._settings.netcdf_data_root
        if not root.is_dir():
            return 0
        count = 0
        for nc_file in sorted(root.glob("*.nc")):
            dataset_id = f"local_{nc_file.stem}"
            self._register(
                RegisteredDataset(
                    info=DatasetInfo(
                        id=dataset_id,
                        title=nc_file.stem.replace("_", " ").title(),
                        summary=f"Local sample NetCDF file ({nc_file.name}).",
                        source_type="local",
                    ),
                    local_path=nc_file,
                )
            )
            count += 1
        return count

    def _discover_iso19115(self) -> int:
        records = scan_metadata_directory(self._settings.metadata_root)
        count = 0
        for record in records:
            time_range = (
                TimeRange(
                    start=record.time_start,
                    end=record.time_end,
                    count=0,
                )
                if record.time_start and record.time_end
                else None
            )
            if record.services.erddap_griddap:
                entry = RegisteredDataset(
                    info=DatasetInfo(
                        id=record.dataset_id,
                        title=record.title,
                        summary=record.summary,
                        source_type="erddap_remote",
                        time_range=time_range,
                        spatial_bounds=record.spatial_bounds,
                        services=build_erddap_griddap_urls(
                            record.services.erddap_griddap.rsplit("/griddap/", 1)[0],
                            record.dataset_id,
                        ),
                    ),
                    remote_url=record.services.erddap_griddap,
                    engine="pydap",
                )
            elif record.services.opendap:
                entry = RegisteredDataset(
                    info=DatasetInfo(
                        id=record.dataset_id,
                        title=record.title,
                        summary=record.summary,
                        source_type="thredds",
                        time_range=time_range,
                        spatial_bounds=record.spatial_bounds,
                        services=record.services.model_copy(
                            update={"dataset_id": record.dataset_id}
                        ),
                    ),
                    remote_url=record.services.opendap,
                    engine="pydap",
                )
            else:
                # e.g. tabledap-only records: listed for completeness, but not
                # openable through the gridded-model API.
                entry = RegisteredDataset(
                    info=DatasetInfo(
                        id=record.dataset_id,
                        title=record.title,
                        summary=record.summary,
                        source_type="erddap_tabledap",
                        time_range=time_range,
                        spatial_bounds=record.spatial_bounds,
                        services=record.services.model_copy(
                            update={"dataset_id": record.dataset_id}
                        ),
                    )
                )
            self._register(entry)
            count += 1
        return count

    async def discover_thredds_async(self) -> int:
        """Best-effort THREDDS catalog discovery; never fails startup."""
        if self._thredds is None or not self._thredds.configured:
            return 0
        try:
            catalog_entries = await self._thredds.discover_datasets()
        except Exception as exc:  # noqa: BLE001 - optional source
            _LOG.warning("thredds_discovery_failed error=%r", exc)
            return 0
        added = 0
        from app.ingestion.thredds_client import build_thredds_service_urls

        for item in catalog_entries:
            if item.id in self._datasets:
                continue
            urls = build_thredds_service_urls(
                dataset_path=item.id,
                settings=self._settings,
            )
            self._register(
                RegisteredDataset(
                    info=DatasetInfo(
                        id=item.id.rsplit("/", 1)[-1],
                        title=item.title,
                        summary="Discovered via THREDDS catalog.",
                        source_type="thredds",
                        services=urls,
                    ),
                    remote_url=urls.opendap,
                    engine="pydap" if urls.opendap else None,
                )
            )
            added += 1
        return added

    def refresh_in_background(self) -> None:
        """Trigger THREDDS discovery without blocking startup."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.discover_thredds_async())

    # -- lookup --------------------------------------------------------------

    def list(self) -> list[DatasetInfo]:
        return [entry.info for entry in self._datasets.values()]

    def get(self, dataset_id: str) -> RegisteredDataset:
        entry = self._datasets.get(dataset_id)
        if entry is None:
            known = ", ".join(sorted(self._datasets)[:10]) or "(none)"
            raise KeyError(f"unknown dataset_id {dataset_id!r}; registered: {known}")
        return entry


def bounds_from_record(south: float, north: float, west: float, east: float) -> SpatialBounds:
    return SpatialBounds(south=south, north=north, west=west, east=east)
