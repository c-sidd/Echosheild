"""Argo client tests — upstream (argopy) is fully mocked."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.ingestion.argo_client import ArgoClient, ArgoClientError, _create_fetcher


class FakeFetcher:
    """Mimics the argopy fetcher surface used by ArgoClient."""

    def __init__(self, data: xr.Dataset | pd.DataFrame) -> None:
        self._data = data

    def region(self, box: list[float]) -> FakeFetcher:
        return self

    def float(self, wmo: int) -> FakeFetcher:
        return self

    def profile(self, wmo: int, cycle: int) -> FakeFetcher:
        return self

    def to_dataframe(self) -> pd.DataFrame:
        if isinstance(self._data, pd.DataFrame):
            return self._data
        return self._data.to_dataframe().reset_index()

    @property
    def data(self) -> xr.Dataset:
        if isinstance(self._data, pd.DataFrame):
            frame = self._data.copy()
            return xr.Dataset.from_dataframe(frame.set_index(["N_PROF", "N_LEVELS"]))
        assert isinstance(self._data, xr.Dataset)
        return self._data


def _fake_point_dataset(n_prof: int = 6, n_levels: int = 10) -> xr.Dataset:
    rng = np.random.default_rng(7)
    return xr.Dataset(
        {
            "TEMP": (("N_PROF", "N_LEVELS"), rng.uniform(2, 28, (n_prof, n_levels))),
            "PSAL": (("N_PROF", "N_LEVELS"), rng.uniform(34, 36, (n_prof, n_levels))),
            "PRES": (("N_PROF", "N_LEVELS"), np.tile(np.linspace(5, 500, n_levels), (n_prof, 1))),
            "PLATFORM_NUMBER": (("N_PROF",), np.full(n_prof, 2902123.0)),
            "CYCLE_NUMBER": (("N_PROF",), np.arange(1, n_prof + 1, dtype=float)),
            "LATITUDE": (("N_PROF",), np.linspace(8, 12, n_prof)),
            "LONGITUDE": (("N_PROF",), np.linspace(65, 70, n_prof)),
            "TIME": (("N_PROF",), pd.date_range("2024-02-01", periods=n_prof, freq="10D").values),
        }
    )


@pytest.fixture()
def mocked_argo(monkeypatch: pytest.MonkeyPatch, settings) -> ArgoClient:
    frame = _fake_point_dataset().to_dataframe().reset_index()
    monkeypatch.setattr(
        "app.ingestion.argo_client._create_fetcher",
        lambda source, dataset, mode="standard", **options: FakeFetcher(frame.copy()),
    )
    return ArgoClient(settings)


def test_search_floats_returns_summaries(mocked_argo: ArgoClient) -> None:
    floats = mocked_argo.search_floats(max_floats=10)
    assert floats and floats[0].platform_wmo == 2902123
    assert floats[0].cycles == 6
    assert floats[0].last_location is not None


def test_float_detail_profiles(mocked_argo: ArgoClient) -> None:
    detail = mocked_argo.float_detail(2902123, max_profiles=3)
    assert detail.platform_wmo == 2902123
    assert len(detail.recent_profiles) == 3
    profile = detail.recent_profiles[0]
    assert profile.points
    first = profile.points[0]
    assert first.temperature_c is not None and first.salinity_psu is not None
    assert detail.time_range is not None


def test_profile_by_cycle_and_missing_cycle(
    mocked_argo: ArgoClient,
) -> None:
    latest = mocked_argo.float_profile(2902123)
    assert latest.cycle_number in {1, 2, 3}
    by_cycle = mocked_argo.float_profile(2902123, cycle=1)
    assert by_cycle.cycle_number == 1
    with pytest.raises(ArgoClientError, match="not found"):
        mocked_argo.float_profile(2902123, cycle=999)


def test_upstream_failure_maps_to_domain_error(monkeypatch: pytest.MonkeyPatch, settings) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise TimeoutError("upstream down")

    monkeypatch.setattr("app.ingestion.argo_client._create_fetcher", boom)
    client = ArgoClient(settings)
    with pytest.raises(ArgoClientError, match="request failed"):
        client.search_floats()


def test_region_box_meets_argopy_minimum(
    monkeypatch: pytest.MonkeyPatch,
    settings,  # noqa: ANN001 - Settings fixture
) -> None:
    """argopy rejects region boxes with <6 elements; depths must always ride along."""
    captured: dict[str, list[float]] = {}
    frame = _fake_point_dataset(n_prof=2).to_dataframe().reset_index()

    def spy_fetch(self: ArgoClient, box: list[float]) -> pd.DataFrame:
        captured["box"] = list(box)
        return frame.copy()

    monkeypatch.setattr(ArgoClient, "_fetch_region", spy_fetch)
    client = ArgoClient(settings)

    client.search_floats(max_floats=5)
    assert len(captured["box"]) == 6  # lon0 lon1 lat0 lat1 depth0 depth1
    assert captured["box"][4] == 0 and captured["box"][5] == 2000

    client.search_floats(start="2024-01-01", end="2024-02-01", max_floats=5)
    assert len(captured["box"]) == 8


def test_argo_api_returns_503_when_upstream_down(
    client,  # noqa: ANN001 - TestClient fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API degrades gracefully: argopy failure must never crash the app."""

    def boom(*args: object, **kwargs: object) -> object:
        raise TimeoutError("erddap unreachable")

    monkeypatch.setattr("app.ingestion.argo_client._create_fetcher", boom)
    response = client.get("/api/v1/argo/floats")
    assert response.status_code == 503
    assert "upstream unavailable" in response.json()["detail"]


def test_empty_region_raises_clear_error(monkeypatch: pytest.MonkeyPatch, settings) -> None:
    empty_frame = pd.DataFrame()
    monkeypatch.setattr(
        "app.ingestion.argo_client._create_fetcher",
        lambda *a, **k: FakeFetcher(empty_frame),
    )
    client = ArgoClient(settings)
    with pytest.raises(ArgoClientError, match="no Argo floats"):
        client.search_floats()


def test_create_fetcher_seam_importable() -> None:
    # The real seam must stay importable for production use.
    assert callable(_create_fetcher)
