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
from app.ingestion.iso19115_parser import (
    IsoDatasetRecord,
    parse_iso19115_file,
    scan_metadata_directory,
)
from app.ingestion.thredds_client import (
    ThreddsClient,
    build_erddap_griddap_urls,
    build_thredds_service_urls,
)
from app.models.schemas import DatasetInfo, ServiceEndpoints, TimeRange

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

    def _local_roots(self) -> list[Path]:
        roots = [self._settings.netcdf_data_root]
        for candidate in (self._settings.argo_cache_dir, self._settings.glider_cache_dir):
            if candidate not in roots:
                roots.append(candidate)
        return [root for root in roots if root.is_dir()]

    def _sidecar_record(self, nc_file: Path) -> IsoDatasetRecord | None:
        """Associate ``<stem>_iso19115.xml`` metadata with a NetCDF file.

        Matching is metadata-driven and tolerant of real-world export names:

        1. exact stem match wins (``synthetic_ocean.nc`` ↔
           ``synthetic_ocean_iso19115.xml``),
        2. otherwise a word-boundary *prefix* match associates ERDDAP-style
           download names with their product record — e.g.
           ``incois_argo_mnt_VAM_f99c_fe7d_a5a3_U1787403117643.nc`` ↔
           ``incois_argo_mnt_VAM_iso19115.xml``,

        with the most specific (longest) record winning on ambiguity.
        """
        stem = nc_file.stem.lower()
        search_dirs = {nc_file.parent, self._settings.metadata_root}
        best: tuple[int, int, IsoDatasetRecord] | None = None  # (exact, length)
        seen_xml: set[Path] = set()
        for directory in search_dirs:
            if not directory.is_dir():
                continue
            for xml_path in sorted(directory.glob("*iso19115*.xml")):
                if xml_path.resolve() in seen_xml:
                    continue
                seen_xml.add(xml_path.resolve())
                lowered = xml_path.name.lower()
                xml_stem = (
                    lowered[: -len("_iso19115.xml")]
                    if lowered.endswith("_iso19115.xml")
                    else xml_path.stem.lower()
                )
                exact = xml_stem == stem or xml_path.stem.lower() == stem
                prefix = not exact and xml_stem and stem.startswith(xml_stem + "_")
                if not (exact or prefix):
                    continue
                specificity = (1 if exact else 0, len(xml_stem))
                if best is not None and specificity <= best[:2]:
                    continue
                record = parse_iso19115_file(xml_path)
                if record is not None:
                    best = (specificity[0], specificity[1], record)
        return best[2] if best else None

    def _services_for(
        self,
        sidecar: IsoDatasetRecord | None,
        nc_file: Path,
        dataset_id: str,
    ) -> ServiceEndpoints | None:
        """Combine upstream-product services (ISO) with THREDDS local-copy URLs.

        When THREDDS is configured the local copy is served deterministically
        through ``dodsC``/``wms``/``fileServer``; upstream ERDDAP endpoints from
        the ISO record are kept alongside. WCS is never invented here.
        """
        thredds_urls: ServiceEndpoints | None = None
        if self._settings.THREDDS_BASE_URL:
            try:
                thredds_urls = build_thredds_service_urls(
                    dataset_path=f"{nc_file.parent.name}/{nc_file.name}",
                    settings=self._settings,
                    supported={"opendap", "httpserver", "wms"},
                )
            except ValueError:  # malformed configured URL — never break discovery
                thredds_urls = None

        upstream: ServiceEndpoints | None = None
        if sidecar is not None:
            candidate = sidecar.services.model_copy(update={"dataset_id": dataset_id})
            remote_fields = (
                "opendap",
                "erddap_griddap",
                "erddap_tabledap",
                "wms",
                "wcs",
            )
            if any(getattr(candidate, field) for field in remote_fields):
                upstream = candidate

        if thredds_urls is None:
            return upstream
        if upstream is None:
            return thredds_urls
        return ServiceEndpoints(
            dataset_id=dataset_id,
            opendap=thredds_urls.opendap or upstream.opendap,
            wms=thredds_urls.wms or upstream.wms,
            erddap_griddap=upstream.erddap_griddap,
            erddap_tabledap=upstream.erddap_tabledap,
            wcs=upstream.wcs,
            thredds_catalog=thredds_urls.thredds_catalog,
            http_download=thredds_urls.http_download,
        )

    def _probe_readable(self, nc_file: Path) -> bool:
        """Cheap header check so corrupt files never break discovery."""
        try:
            import xarray as xr

            ds = xr.open_dataset(nc_file, decode_times=False)
            ds.close()
            return True
        except Exception as exc:  # noqa: BLE001 - corrupt/unreadable files are isolated
            _LOG.warning("dataset_skipped_unreadable file=%s error=%s", nc_file.name, exc)
            return False

    def _discover_local_netcdf(self) -> int:
        count = 0
        seen_ids: set[str] = set()
        for root in self._local_roots():
            for nc_file in sorted(root.glob("*.nc")):
                if not self._probe_readable(nc_file):
                    continue
                sidecar = self._sidecar_record(nc_file)
                # Deterministic ID: the ISO 19115 product identifier when a
                # sidecar record matches (stable across ERDDAP re-downloads,
                # whose filenames embed session hashes), otherwise the file
                # stem based local_* ID.
                dataset_id = sidecar.dataset_id if sidecar else f"local_{nc_file.stem}"
                if dataset_id in seen_ids:
                    # Deterministic de-confliction across cache directories.
                    dataset_id = f"local_{nc_file.stem}"
                if dataset_id in seen_ids:
                    dataset_id = f"local_{root.name}_{nc_file.stem}"
                if dataset_id in seen_ids:
                    continue
                seen_ids.add(dataset_id)

                time_range = (
                    TimeRange(start=sidecar.time_start, end=sidecar.time_end, count=0)
                    if sidecar and sidecar.time_start and sidecar.time_end
                    else None
                )
                info = DatasetInfo(
                    id=dataset_id,
                    title=(sidecar.title if sidecar else nc_file.stem.replace("_", " ").title()),
                    summary=(
                        sidecar.summary
                        if sidecar and sidecar.summary
                        else f"Local sample NetCDF file ({nc_file.name})."
                    ),
                    source_type="local",
                    provider=sidecar.provider if sidecar else None,
                    license=sidecar.use_limitation if sidecar else None,
                    metadata_path=sidecar.source_file if sidecar else None,
                    time_range=time_range,
                    spatial_bounds=sidecar.spatial_bounds if sidecar else None,
                    services=self._services_for(sidecar, nc_file, dataset_id),
                )
                self._register(RegisteredDataset(info=info, local_path=nc_file))
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
            common = {
                "provider": record.provider,
                "license": record.use_limitation,
                "metadata_path": record.source_file,
            }
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
                        **common,  # type: ignore[arg-type]
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
                        **common,  # type: ignore[arg-type]
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
                        **common,  # type: ignore[arg-type]
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

    def entries(self) -> list[RegisteredDataset]:
        """Full registration records (including access paths)."""
        return list(self._datasets.values())

    def list(self) -> list[DatasetInfo]:
        return [entry.info for entry in self._datasets.values()]

    def get(self, dataset_id: str) -> RegisteredDataset:
        entry = self._datasets.get(dataset_id)
        if entry is None:
            known = ", ".join(sorted(self._datasets)[:10]) or "(none)"
            raise KeyError(f"unknown dataset_id {dataset_id!r}; registered: {known}")
        return entry
