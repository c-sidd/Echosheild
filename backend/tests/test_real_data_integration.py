"""Integration tests against the REAL local INCOIS NetCDF product.

These tests exercise the full service stack (registry -> parser -> service)
against ``data/sample_netcdf/incois_argo_mnt_VAM_*.nc`` — the actual INCOIS
ARGO Monthly VAM gridded product downloaded from INCOIS ERDDAP — plus its
ISO 19115 sidecar record in ``data/``.

They are skipped automatically when the real file is absent so the rest of
the suite stays deterministic. No Internet access is required or attempted:
all comparisons are made against direct lazy xarray reads of the same file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from app.core.config import Settings
from app.services.dataset_registry import DatasetRegistry
from app.services.model_service import ModelDataService

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_ROOT = REPO_ROOT / "data"
REAL_NETCDF_FILES = sorted((REAL_DATA_ROOT / "sample_netcdf").glob("incois_argo_mnt_VAM_*.nc"))

pytestmark = pytest.mark.skipif(
    not REAL_NETCDF_FILES,
    reason="real INCOIS NetCDF product not present under data/sample_netcdf",
)

EXPECTED_DEPTHS = [
    5.0,
    10.0,
    20.0,
    30.0,
    50.0,
    75.0,
    100.0,
    125.0,
    150.0,
    200.0,
    250.0,
    300.0,
    400.0,
    500.0,
    600.0,
    700.0,
    800.0,
    900.0,
    1000.0,
    1200.0,
    1400.0,
    1600.0,
    1800.0,
    2000.0,
]


@pytest.fixture(scope="module")
def real_settings() -> Settings:
    """Settings pointing at the repository's real data tree (read-only)."""
    return Settings(
        DATA_ROOT=REAL_DATA_ROOT,
        NETCDF_DATA_ROOT=REAL_DATA_ROOT / "sample_netcdf",
        ARGO_CACHE_DIR=REAL_DATA_ROOT / "argo_cache",
        GLIDER_CACHE_DIR=REAL_DATA_ROOT / "glider_cache",
        THREDDS_BASE_URL=None,
        THREDDS_CATALOG_URL=None,
        OPENDAP_BASE_URL=None,
        WMS_BASE_URL=None,
        WCS_BASE_URL=None,
        INCOIS_ERDDAP_URL=None,
    )


@pytest.fixture(scope="module")
def registry(real_settings: Settings) -> DatasetRegistry:
    reg = DatasetRegistry(real_settings)
    reg.discover()
    return reg


@pytest.fixture(scope="module")
def service(registry: DatasetRegistry, real_settings: Settings) -> ModelDataService:
    svc = ModelDataService(registry, real_settings)
    yield svc
    svc.close_all()


@pytest.fixture(scope="module")
def dataset_id(registry: DatasetRegistry) -> str:
    """Deterministic ISO-derived ID of the real gridded product."""
    return "incois_argo_mnt_VAM"


# --- discovery & metadata ---------------------------------------------------


class TestRealDiscovery:
    def test_real_dataset_registered(self, registry: DatasetRegistry, dataset_id: str) -> None:
        entry = registry.get(dataset_id)  # raises if missing
        assert entry.local_path is not None
        assert entry.local_path.exists()
        assert entry.info.source_type == "local"

    def test_iso_sidecar_enrichment(self, registry: DatasetRegistry, dataset_id: str) -> None:
        info = registry.get(dataset_id).info
        assert info.title == "INCOIS ARGO Monthly data Variational Analysis Methodology"
        assert info.provider == "INCOIS"
        assert info.metadata_path is not None
        assert "iso19115" in Path(info.metadata_path).name
        bounds = info.spatial_bounds
        assert bounds is not None
        assert (bounds.west, bounds.east) == (30.5, 119.5)
        assert (bounds.south, bounds.north) == (-29.5, 29.5)

    def test_upstream_services_from_iso_record(
        self, registry: DatasetRegistry, dataset_id: str
    ) -> None:
        services = registry.get(dataset_id).info.services
        assert services is not None
        assert services.erddap_griddap == (
            "https://erddap.incois.gov.in/erddap/griddap/incois_argo_mnt_VAM"
        )
        # WCS must never be advertised without an explicit WCS-capable service.
        assert services.wcs is None


class TestRealMetadata:
    def test_dimensions(self, service: ModelDataService, dataset_id: str) -> None:
        md = service.get_metadata(dataset_id)
        assert md.dimensions == {"time": 271, "ZAX": 24, "latitude": 60, "longitude": 90}

    def test_vertical_axis_is_native_depth_in_meters(
        self, service: ModelDataService, dataset_id: str
    ) -> None:
        md = service.get_metadata(dataset_id)
        assert md.depth_range is not None
        # The source axis carries units METERS with positive-down semantics;
        # values are preserved natively (never converted from pressure).
        assert md.depth_range.min_meters == 5.0
        assert md.depth_range.max_meters == 2000.0

    def test_canonical_variable_mapping(self, service: ModelDataService, dataset_id: str) -> None:
        variables = {v.canonical_name: v.name for v in service.list_variables(dataset_id)}
        assert variables["temperature"] == "TEMP"
        assert variables["salinity"] == "SAL"
        # No currents / chlorophyll exist in this product — never fabricated.
        assert "u_current" not in variables.values()
        assert "v_current" not in variables.values()
        assert "chlorophyll" not in variables

    def test_time_axis_decoded(self, service: ModelDataService, dataset_id: str) -> None:
        tr = service.get_time_range(dataset_id)
        assert tr.start.startswith("2004-01-15")
        assert tr.end.startswith("2026-07-15")
        assert tr.count == 271

    def test_native_depth_values(self, service: ModelDataService, dataset_id: str) -> None:
        assert service.get_depths_meters(dataset_id) == EXPECTED_DEPTHS


# --- value-level verification -----------------------------------------------


class TestRealValues:
    def test_temperature_slice_matches_truth(
        self, registry: DatasetRegistry, service: ModelDataService, dataset_id: str
    ) -> None:
        entry = registry.get(dataset_id)
        slice_ = service.read_slice(
            dataset_id,
            "temperature",
            time_index=100,
            depth_meters=5.0,
            bbox=(60.0, 80.0, 10.0, 20.0),
        )
        assert slice_.canonical_name == "temperature"
        assert slice_.variable == "TEMP"
        assert slice_.units == "degs"
        assert slice_.vertical_kind == "depth"
        assert slice_.time is not None and slice_.time.startswith("2012-05-15")

        truth = (
            xr.open_dataset(entry.local_path)["TEMP"]
            .isel(time=100)
            .sel(ZAX=5)
            .sel(latitude=slice(10, 20), longitude=slice(60, 80))
        )
        tv = np.asarray(truth.values, dtype=float)
        arr = np.asarray(slice_.values, dtype=float)
        # Orientation contract: values[row][column] == latitude × longitude.
        assert arr.shape == tv.shape == (len(slice_.latitude), len(slice_.longitude))
        assert int(np.isfinite(arr).sum()) == int(np.isfinite(tv).sum())
        np.testing.assert_allclose(arr[np.isfinite(arr)], tv[np.isfinite(tv)], rtol=1e-6)

    def test_salinity_slice_matches_truth(
        self, registry: DatasetRegistry, service: ModelDataService, dataset_id: str
    ) -> None:
        entry = registry.get(dataset_id)
        slice_ = service.read_slice(
            dataset_id,
            "salinity",
            time_index=200,
            depth_meters=100.0,
            bbox=(80.0, 95.0, -15.0, 0.0),
        )
        assert slice_.canonical_name == "salinity"
        assert slice_.units == "PSU"
        truth = (
            xr.open_dataset(entry.local_path)["SAL"]
            .isel(time=200)
            .sel(ZAX=100)
            .sel(latitude=slice(-15, 0), longitude=slice(80, 95))
        )
        tv = np.asarray(truth.values, dtype=float)
        arr = np.asarray(slice_.values, dtype=float)
        np.testing.assert_allclose(arr[np.isfinite(arr)], tv[np.isfinite(tv)], rtol=1e-6)

    def test_profile_matches_truth_column(self, service: ModelDataService, dataset_id: str) -> None:
        lat, lon = 15.5, 70.5
        profile = service.read_profile(
            dataset_id, "TEMP", latitude=lat, longitude=lon, time_index=150
        )
        assert profile.vertical_kind == "depth"
        assert profile.depths_meters == EXPECTED_DEPTHS
        # Direct comparison against the same native column.
        ds = xr.open_dataset(_real_file())
        try:
            truth_col = (
                ds["TEMP"]
                .isel(time=150)
                .sel(latitude=lat, longitude=lon, method="nearest")
                .values.astype(float)
            )
        finally:
            ds.close()
        api_vals = np.asarray([np.nan if v is None else v for v in profile.values])
        np.testing.assert_allclose(api_vals, truth_col, rtol=1e-5)

    def test_point_matches_truth(self, service: ModelDataService, dataset_id: str) -> None:
        sample = service.read_point(
            dataset_id,
            ["temperature", "salinity"],
            latitude=15.5,
            longitude=70.5,
            time_index=50,
            depth_meters=75.0,
        )
        assert sample.nearest_grid == {"latitude": 15.5, "longitude": 70.5}
        assert sample.time is not None and sample.time.startswith("2008-03-15")
        # Point values are keyed by canonical category (stable frontend names).
        temp = sample.values["temperature"]
        sal = sample.values["salinity"]
        assert temp is not None and abs(temp - 24.865333557128906) < 1e-4
        assert sal is not None and abs(sal - 36.10966491699219) < 1e-4

    def test_currents_honestly_unavailable(
        self, service: ModelDataService, dataset_id: str
    ) -> None:
        field = service.read_currents(dataset_id, time_index=0, depth_meters=5.0, bbox=None)
        assert getattr(field, "available", None) is False
        assert "not available" in field.reason.lower()  # type: ignore[union-attr]


# --- error contracts on real data -------------------------------------------


class TestRealErrorContracts:
    def test_unknown_canonical_and_raw_variables(
        self, service: ModelDataService, dataset_id: str
    ) -> None:
        for bad in ("chlorophyll", "u_current", "NOPE"):
            with pytest.raises(KeyError):
                service.read_slice(dataset_id, bad, time_index=0, depth_meters=None, bbox=None)

    def test_time_index_bounds(self, service: ModelDataService, dataset_id: str) -> None:
        with pytest.raises(IndexError):
            service.read_slice(
                dataset_id,
                "temperature",
                time_index=271,
                depth_meters=5.0,
                bbox=None,
            )

    def test_api_layer_404_on_unknown_entities(self, real_settings: Settings) -> None:
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.main import create_app  # noqa: PLC0415

        with TestClient(create_app(real_settings)) as client:
            r = client.get("/api/v1/model/nope/metadata")
            assert r.status_code == 404
            r = client.get(
                "/api/v1/model/incois_argo_mnt_VAM/slice",
                params={"variable": "chlorophyll", "time_index": 0},
            )
            assert r.status_code == 404
            r = client.get(
                "/api/v1/model/incois_argo_mnt_VAM/slice",
                params={"variable": "temperature", "time_index": 99999},
            )
            assert r.status_code == 404
            # Path traversal can never resolve to a filesystem path.
            r = client.get("/api/v1/model/..%2F..%2Fsecret/metadata")
            assert r.status_code == 404


def _real_file() -> Path:
    return REAL_NETCDF_FILES[0]
