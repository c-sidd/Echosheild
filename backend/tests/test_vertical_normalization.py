"""Vertical-axis normalization regression tests.

Contract under test:
- depth-kind axes stored ascending, descending or as negative heights
  (height-above-surface) must all select the same *physical* level for a
  given requested depth across /depths, /slice, /point and /profile.
- Reported depth representation follows the positive-down convention
  already used by /depths and /slice.
- Pressure-kind models are never silently compared against meter-based
  Argo profiles by /argo/{wmo}/compare.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.main import create_app
from app.models.schemas import ArgoProfile, ArgoProfilePoint


def _value_at_physical_depth(physical_depth: float) -> float:
    """Distinctive value so the selected physical level is identifiable."""
    return round(20.0 - 0.1 * physical_depth, 4)


AXIS_CASES = {
    "ascending_positive_down": [5.0, 10.0, 25.0, 50.0, 100.0],
    "descending_positive_down": [100.0, 50.0, 25.0, 10.0, 5.0],
    "negative_height": [-5.0, -10.0, -25.0, -50.0, -100.0],
}
SORTED_PHYSICAL = [5.0, 10.0, 25.0, 50.0, 100.0]


def _axis_dataset(depths: list[float], *, with_nan: bool = False) -> xr.Dataset:
    axis = np.asarray(depths, dtype="float32")
    # Height-above-surface storage encodes depth as negative values.
    physical = np.abs(axis).astype("float32")
    column = (20.0 - 0.1 * physical)[:, None, None]
    data = np.broadcast_to(column, (2, axis.size, 2, 2)).astype("float32").copy()
    salinity = (
        np.broadcast_to((34.6 + 0.01 * physical)[:, None, None], (2, axis.size, 2, 2))
        .astype("float32")
        .copy()
    )
    if with_nan:
        k25 = int(np.argmin(np.abs(np.abs(axis) - 25.0)))
        data[0, k25, 0, 0] = np.nan
        salinity[0, k25, 0, 0] = np.nan
    ds = xr.Dataset(
        data_vars={
            "temperature": (("time", "depth", "latitude", "longitude"), data),
            "salinity": (("time", "depth", "latitude", "longitude"), salinity),
        },
        coords={
            "time": pd.date_range("2024-01-01", periods=2, freq="D"),
            "depth": (
                "depth",
                axis,
                {"units": "m", "positive": "up" if float(axis.min()) < 0 else "down"},
            ),
            "latitude": [5.0, 6.0],
            "longitude": [60.0, 61.0],
        },
    )
    ds["temperature"].attrs = {"standard_name": "sea_water_temperature", "units": "degC"}
    ds["salinity"].attrs = {"standard_name": "sea_water_salinity", "units": "1e-3"}
    return ds


def _pressure_dataset() -> xr.Dataset:
    axis = np.asarray([10.0, 50.0, 100.0, 500.0, 1000.0], dtype="float32")
    data = np.broadcast_to((15.0 + 0.002 * axis)[:, None, None], (2, axis.size, 2, 2))
    ds = xr.Dataset(
        data_vars={"TEMP": (("time", "pres", "latitude", "longitude"), data.astype("float32"))},
        coords={
            "time": pd.date_range("2024-01-01", periods=2, freq="D"),
            "pres": ("pres", axis, {"units": "dbar"}),
            "latitude": [5.0, 6.0],
            "longitude": [60.0, 61.0],
        },
    )
    ds["TEMP"].attrs = {"standard_name": "sea_water_temperature", "units": "degC"}
    return ds


def _register(settings, stem: str, ds: xr.Dataset) -> str:
    root = Path(settings.NETCDF_DATA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(root / f"{stem}.nc", engine="netcdf4")
    return f"local_{stem}"


@pytest.fixture()
def axis_clients(settings):  # noqa: ANN001
    """One lifespan-active TestClient per axis representation, keyed by case name."""
    from fastapi.testclient import TestClient as _TC

    clients: dict[str, _TC] = {}
    with contextlib.ExitStack() as stack:
        for name, depths in AXIS_CASES.items():
            _register(settings, name, _axis_dataset(depths))
            clients[name] = stack.enter_context(_TC(create_app(settings)))
        yield clients


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_depths_endpoint_reports_sorted_positive_down_levels(axis_clients, case: str) -> None:  # noqa: ANN001
    response = axis_clients[case].get("/api/v1/model/local_" + case + "/depths")
    assert response.status_code == 200
    assert response.json() == pytest.approx(SORTED_PHYSICAL)


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_point_selects_physical_level_across_axis_representations(
    axis_clients,
    case: str,  # noqa: ANN001
) -> None:
    response = axis_clients[case].get(
        "/api/v1/model/local_" + case + "/point",
        params={
            "variables": "temperature",
            "latitude": 6.0,
            "longitude": 61.0,
            "time_index": 0,
            "depth": 25.0,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    # Positive-down reporting contract regardless of native storage order.
    assert payload["depth_meters"] == pytest.approx(25.0)
    assert payload["values"]["temperature"] == pytest.approx(_value_at_physical_depth(25.0))


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_slice_selects_physical_level_across_axis_representations(
    axis_clients,
    case: str,  # noqa: ANN001
) -> None:
    response = axis_clients[case].get(
        "/api/v1/model/local_" + case + "/slice",
        params={"variable": "temperature", "time_index": 0, "depth": 25.0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["depth_meters"] == pytest.approx(25.0)
    assert payload["vertical_kind"] == "depth"
    assert payload["values"][1][1] == pytest.approx(_value_at_physical_depth(25.0))


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_profile_reports_sorted_positive_down_levels(
    axis_clients,
    case: str,  # noqa: ANN001
) -> None:
    response = axis_clients[case].get(
        "/api/v1/model/local_" + case + "/profile",
        params={"variable": "temperature", "latitude": 6.0, "longitude": 61.0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["depths_meters"] == pytest.approx(SORTED_PHYSICAL)
    expected = [_value_at_physical_depth(d) for d in SORTED_PHYSICAL]
    assert payload["values"] == pytest.approx(expected)


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_default_depth_is_shallowest_level_consistently_across_endpoints(
    axis_clients,
    case: str,  # noqa: ANN001
) -> None:
    client = axis_clients[case]
    point = client.get(
        "/api/v1/model/local_" + case + "/point",
        params={"variables": "temperature", "latitude": 6.0, "longitude": 61.0},
    ).json()
    slice_ = client.get(
        "/api/v1/model/local_" + case + "/slice",
        params={"variable": "temperature", "time_index": 0},
    ).json()
    assert point["depth_meters"] == pytest.approx(SORTED_PHYSICAL[0])
    assert point["values"]["temperature"] == pytest.approx(_value_at_physical_depth(5.0))
    # /point must agree with /slice when no depth is requested.
    assert slice_["depth_meters"] == pytest.approx(point["depth_meters"])
    assert slice_["values"][1][1] == pytest.approx(point["values"]["temperature"])


@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_out_of_range_depth_snaps_to_nearest_extreme(
    axis_clients,
    case: str,  # noqa: ANN001
) -> None:
    client = axis_clients[case]
    deep = client.get(
        "/api/v1/model/local_" + case + "/point",
        params={
            "variables": "temperature",
            "latitude": 6.0,
            "longitude": 61.0,
            "depth": 9999.0,
        },
    ).json()
    shallow = client.get(
        "/api/v1/model/local_" + case + "/point",
        params={
            "variables": "temperature",
            "latitude": 6.0,
            "longitude": 61.0,
            "depth": -3.0,
        },
    ).json()
    assert deep["depth_meters"] == pytest.approx(SORTED_PHYSICAL[-1])
    assert deep["values"]["temperature"] == pytest.approx(_value_at_physical_depth(100.0))
    assert shallow["depth_meters"] == pytest.approx(SORTED_PHYSICAL[0])
    assert shallow["values"]["temperature"] == pytest.approx(_value_at_physical_depth(5.0))


def test_nan_cell_returns_null_without_affecting_neighbours(settings) -> None:  # noqa: ANN001
    stem = "nan_axis"
    dataset_id = _register(
        settings, stem, _axis_dataset(AXIS_CASES["ascending_positive_down"], with_nan=True)
    )
    app = create_app(settings)
    from fastapi.testclient import TestClient as _TC

    with _TC(app) as client:
        nan_cell = client.get(
            f"/api/v1/model/{dataset_id}/point",
            params={
                "variables": "temperature",
                "latitude": 5.0,
                "longitude": 60.0,
                "time_index": 0,
                "depth": 25.0,
            },
        ).json()
        neighbour = client.get(
            f"/api/v1/model/{dataset_id}/point",
            params={
                "variables": "temperature",
                "latitude": 6.0,
                "longitude": 61.0,
                "time_index": 0,
                "depth": 25.0,
            },
        ).json()
        later_time = client.get(
            f"/api/v1/model/{dataset_id}/point",
            params={
                "variables": "temperature",
                "latitude": 5.0,
                "longitude": 60.0,
                "time_index": 1,
                "depth": 25.0,
            },
        ).json()
    assert nan_cell["values"]["temperature"] is None
    assert neighbour["values"]["temperature"] == pytest.approx(_value_at_physical_depth(25.0))
    assert later_time["values"]["temperature"] == pytest.approx(_value_at_physical_depth(25.0))
    app.state.model_service.close_all()


def test_surface_only_dataset_selects_single_level(settings) -> None:  # noqa: ANN001
    stem = "surface_only"
    dataset_id = _register(settings, stem, _axis_dataset([0.0]))
    app = create_app(settings)
    from fastapi.testclient import TestClient as _TC

    with _TC(app) as client:
        depths = client.get(f"/api/v1/model/{dataset_id}/depths")
        default_point = client.get(
            f"/api/v1/model/{dataset_id}/point",
            params={"variables": "temperature", "latitude": 6.0, "longitude": 61.0},
        )
        snapped_point = client.get(
            f"/api/v1/model/{dataset_id}/point",
            params={
                "variables": "temperature",
                "latitude": 6.0,
                "longitude": 61.0,
                "depth": 25.0,
            },
        )
    assert depths.status_code == 200
    assert depths.json() == pytest.approx([0.0])
    assert default_point.json()["depth_meters"] == pytest.approx(0.0)
    # Nearest-level semantics clamp to the only available level.
    assert snapped_point.json()["depth_meters"] == pytest.approx(0.0)
    app.state.model_service.close_all()


# --- comparison guard --------------------------------------------------------


class _StubArgoClient:
    source = "stub"

    def __init__(self, profile: ArgoProfile) -> None:
        self._profile = profile

    def float_profile(self, wmo: int, cycle: int | None = None) -> ArgoProfile:
        return self._profile


def _observed_profile() -> ArgoProfile:
    return ArgoProfile(
        platform_wmo=2902123,
        cycle_number=3,
        time="2024-01-01T12:00:00Z",
        latitude=6.0,
        longitude=61.0,
        points=[
            ArgoProfilePoint(depth_meters=10.0, temperature_c=20.0, salinity_psu=35.0),
            ArgoProfilePoint(depth_meters=25.0, temperature_c=19.0, salinity_psu=35.2),
        ],
    )


def test_compare_rejects_pressure_coordinate_model(settings, monkeypatch) -> None:  # noqa: ANN001
    dataset_id = _register(settings, "pressure_model", _pressure_dataset())
    app = create_app(settings)
    from fastapi.testclient import TestClient as _TC

    with _TC(app) as client:
        monkeypatch.setattr(app.state, "argo_client", _StubArgoClient(_observed_profile()))
        response = client.get(
            "/api/v1/argo/2902123/compare",
            params={"dataset_id": dataset_id},
        )
    detail = response.json()["detail"]
    assert response.status_code == 422
    assert "pressure" in detail
    # No misleading metrics may be present in the error path.
    assert "mae" not in detail.lower()
    app.state.model_service.close_all()


def test_compare_still_works_for_depth_coordinate_model(settings, monkeypatch) -> None:  # noqa: ANN001
    dataset_id = _register(
        settings, "depth_model", _axis_dataset(AXIS_CASES["descending_positive_down"])
    )
    app = create_app(settings)
    from fastapi.testclient import TestClient as _TC

    with _TC(app) as client:
        monkeypatch.setattr(app.state, "argo_client", _StubArgoClient(_observed_profile()))
        response = client.get(
            "/api/v1/argo/2902123/compare",
            params={"dataset_id": dataset_id},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == dataset_id
    metrics = payload["metrics"]
    assert metrics["temperature_count"] == 2
    assert metrics["temperature_mae_c"] is not None
    assert len(payload["points"]) == 2
    # Model levels were matched at the observed physical depths.
    assert [p["depth_meters"] for p in payload["points"]] == pytest.approx([10.0, 25.0])
    app.state.model_service.close_all()


def test_compare_unknown_dataset_still_404(settings, monkeypatch) -> None:  # noqa: ANN001
    app = create_app(settings)
    from fastapi.testclient import TestClient as _TC

    with _TC(app) as client:
        monkeypatch.setattr(app.state, "argo_client", _StubArgoClient(_observed_profile()))
        response = client.get(
            "/api/v1/argo/2902123/compare",
            params={"dataset_id": "does_not_exist"},
        )
    assert response.status_code == 404
    app.state.model_service.close_all()
