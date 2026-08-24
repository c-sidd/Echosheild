"""LocalArgoClient tests using real-schema Argo-style fixture files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.core.config import Settings
from app.ingestion.argo_client import ArgoClient, create_argo_client
from app.ingestion.argo_local import LocalArgoClient


def _write_argo_style_file(
    path: Path, *, wmo: int = 2902123, n_prof: int = 3, n_levels: int = 20
) -> None:
    rng = np.random.default_rng(11)
    ds = xr.Dataset(
        {
            "TEMP": (("N_PROF", "N_LEVELS"), rng.uniform(2.0, 28.0, (n_prof, n_levels))),
            "PSAL": (("N_PROF", "N_LEVELS"), rng.uniform(34.0, 36.0, (n_prof, n_levels))),
            "PRES": (
                ("N_PROF", "N_LEVELS"),
                np.tile(np.linspace(5.0, 500.0, n_levels), (n_prof, 1)),
            ),
            "PLATFORM_NUMBER": (("N_PROF",), np.full(n_prof, float(wmo))),
            "CYCLE_NUMBER": (("N_PROF",), np.arange(1, n_prof + 1, dtype=float)),
            "LATITUDE": (("N_PROF",), np.linspace(8.0, 12.0, n_prof)),
            "LONGITUDE": (("N_PROF",), np.linspace(65.0, 70.0, n_prof)),
            "JULD": (("N_PROF",), pd.date_range("2024-02-01", periods=n_prof, freq="10D").values),
        }
    )
    ds.to_netcdf(path)


@pytest.fixture()
def local_argo_settings(settings: Settings) -> Settings:
    cache: Path = settings.ARGO_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    _write_argo_style_file(cache / "2902123_profiles.nc")
    return settings


def test_factory_auto_prefers_local_files(local_argo_settings: Settings) -> None:
    client = create_argo_client(local_argo_settings)
    assert isinstance(client, LocalArgoClient)


def test_factory_auto_falls_back_to_null_when_no_local_files(settings: Settings) -> None:
    """Without local .nc files, auto mode returns NullArgoClient (not remote).

    NullArgoClient returns clean 503 responses instead of making network calls
    to Ifremer ERDDAP that will fail in CI/local dev without outbound TLS.
    Use ARGO_PROVIDER=remote to explicitly enable live fetching.
    """
    from app.ingestion.argo_client import NullArgoClient

    # Force auto mode explicitly — backend/.env may set ARGO_PROVIDER=local
    # which would override the test's intent via pydantic-settings.
    auto_settings = settings.model_copy(update={"ARGO_PROVIDER": "auto"})
    assert isinstance(create_argo_client(auto_settings), NullArgoClient)


def test_factory_respects_explicit_mode(settings: Settings) -> None:
    forced = settings.model_copy(update={"ARGO_PROVIDER": "remote"})
    assert isinstance(create_argo_client(forced), ArgoClient)


def test_search_floats_from_local_cache(local_argo_settings: Settings) -> None:
    client = LocalArgoClient(local_argo_settings)
    floats = client.search_floats(lon_min=50.0, lon_max=100.0, lat_min=-10.0, lat_max=30.0)
    assert len(floats) == 1
    summary = floats[0]
    assert summary.platform_wmo == 2902123
    assert summary.cycles == 3
    assert summary.last_location is not None
    lon, lat = summary.last_location
    assert 65 <= lon <= 70 and 8 <= lat <= 12
    assert summary.last_time is not None


def test_float_detail_pressure_not_depth(local_argo_settings: Settings) -> None:
    detail = LocalArgoClient(local_argo_settings).float_detail(2902123, max_profiles=2)
    assert detail.profiles_available == 3
    assert len(detail.recent_profiles) == 2
    profile = detail.recent_profiles[-1]
    first = profile.points[0]
    # Pressure stays pressure; depth is never silently derived.
    assert first.pressure_dbar is not None
    assert first.depth_meters is None
    assert first.temperature_c is not None and first.salinity_psu is not None


def test_profile_by_cycle_and_missing_cycle(local_argo_settings: Settings) -> None:
    client = LocalArgoClient(local_argo_settings)
    latest = client.float_profile(2902123)
    assert latest.cycle_number == 3
    by_cycle = client.float_profile(2902123, cycle=1)
    assert by_cycle.cycle_number == 1
    with pytest.raises(KeyError, match="not found"):
        client.float_profile(2902123, cycle=999)


def test_corrupt_local_file_is_skipped(local_argo_settings: Settings) -> None:
    (local_argo_settings.ARGO_CACHE_DIR / "broken.nc").write_bytes(b"garbage" * 64)
    client = LocalArgoClient(local_argo_settings)
    floats = client.search_floats()
    assert [s.platform_wmo for s in floats] == [2902123]
