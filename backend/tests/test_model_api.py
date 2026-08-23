"""Model data API tests (local synthetic dataset, no external services)."""

from __future__ import annotations

from fastapi.testclient import TestClient

DATASET = "local_synthetic_ocean"


def test_list_datasets_includes_sample(client: TestClient) -> None:
    response = client.get("/api/v1/model/datasets")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert DATASET in ids


def test_metadata_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimensions"]["time"] == 8
    names = {v["name"] for v in payload["variables"]}
    assert {"temperature", "salinity", "u", "v"} <= names


def test_metadata_unknown_dataset_404(client: TestClient) -> None:
    response = client.get("/api/v1/model/does_not_exist/metadata")
    assert response.status_code == 404
    assert "unknown dataset_id" in response.json()["detail"]


def test_variables_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/variables")
    assert response.status_code == 200
    variables = response.json()
    temp = next(v for v in variables if v["name"] == "temperature")
    assert temp["units"] == "degC"
    assert temp["shape"] == [8, 5, 10, 12]


def test_times_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/times")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 8
    assert payload["start"].startswith("2024-01-01")


def test_depths_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/depths")
    assert response.status_code == 200
    depths = response.json()
    assert depths == pytest_approx([0.0, 10.0, 20.0, 50.0, 100.0])


def pytest_approx(values: list[float]) -> list[float]:
    import math

    return [round(v, 3) if math.isfinite(v) else v for v in values]


def test_slice_endpoint_basic(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/slice",
        params={"variable": "temperature", "time_index": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["latitude"]) == 10
    assert len(payload["longitude"]) == 12
    assert payload["values"][0][0] is None  # deliberate NaN cell
    assert payload["units"] == "degC"


def test_slice_endpoint_bbox_and_depth(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/slice",
        params={
            "variable": "salinity",
            "time_index": 0,
            "depth": 50.0,
            "west": 62.0,
            "east": 66.0,
            "south": 6.0,
            "north": 9.0,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["latitude"]) < 10
    assert payload["depth_meters"] == 50.0


def test_slice_invalid_variable_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/slice", params={"variable": "oxygen"})
    assert response.status_code == 404


def test_slice_invalid_timestep_404(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/slice",
        params={"variable": "temperature", "time_index": 999},
    )
    assert response.status_code == 404


def test_slice_partial_bbox_422(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/slice",
        params={"variable": "temperature", "west": 60.0},
    )
    assert response.status_code == 422


def test_profile_endpoint(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/profile",
        params={"variable": "temperature", "latitude": 6.2, "longitude": 61.5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["depths_meters"]) == len(payload["values"])
    assert payload["depths_meters"][0] == 0.0


def test_point_endpoint(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/point",
        params={
            "variables": "temperature,salinity",
            "latitude": 8.0,
            "longitude": 65.0,
            "time_index": 1,
            "depth": 20.0,
        },
    )
    assert response.status_code == 200
    values = response.json()["values"]
    assert set(values) == {"temperature", "salinity"}
    assert all(v is not None for v in values.values())


def test_currents_endpoint(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/model/{DATASET}/currents",
        params={"time_index": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["u_variable"] == "u"
    assert payload["v_variable"] == "v"
    assert payload["max_speed_ms"] is not None and payload["max_speed_ms"] >= 0


def test_currents_unavailable_contract(client: TestClient, settings) -> None:  # noqa: ANN001
    """Datasets without (u, v) return an explicit availability contract."""
    import numpy as np
    import xarray as xr
    from fastapi.testclient import TestClient

    from app.main import create_app

    temp_only_path = settings.NETCDF_DATA_ROOT / "temp_only.nc"
    ds = xr.Dataset(
        {
            "temperature": (
                ("time", "depth", "latitude", "longitude"),
                np.zeros((2, 2, 2, 2), dtype="float32"),
            ),
        },
        coords={
            "time": np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[ns]"),
            "depth": [0.0, 10.0],
            "latitude": [5.0, 6.0],
            "longitude": [60.0, 61.0],
        },
    )
    temp_only_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(temp_only_path)

    with TestClient(create_app(settings)) as temp_client:
        response = temp_client.get("/api/v1/model/local_temp_only/currents")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is False
        assert "not available" in payload["reason"]


def test_services_metadata_only_dataset_503(client: TestClient) -> None:
    # The synthetic local dataset has no THREDDS/WMS services configured.
    response = client.get(f"/api/v1/model/{DATASET}/services")
    assert response.status_code == 503


# --- registry extents surfaced through the listing (BUG 1 / BUG 3) ----------


def test_dataset_listing_has_real_extents(client: TestClient) -> None:
    response = client.get("/api/v1/model/datasets")
    assert response.status_code == 200
    entry = next(d for d in response.json() if d["id"] == DATASET)
    time_range = entry["time_range"]
    assert time_range is not None
    assert time_range["count"] == 8  # real count, never the placeholder 0
    assert time_range["start"].startswith("2024-01-01")
    assert time_range["end"].startswith("2024-01-08")
    # Spatial footprint probed from coordinates when no ISO sidecar exists.
    bounds = entry["spatial_bounds"]
    assert bounds is not None
    assert (bounds["west"], bounds["east"]) == (60.0, 71.0)
    assert (bounds["south"], bounds["north"]) == (5.0, 14.0)


# --- startup-convenience endpoints ------------------------------------------


def test_times_list_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/times/list")
    assert response.status_code == 200
    times = response.json()
    assert isinstance(times, list) and len(times) == 8
    assert all(isinstance(t, str) for t in times)
    assert times[0].startswith("2024-01-01")
    assert times[-1].startswith("2024-01-08")


def test_times_list_matches_times_count(client: TestClient) -> None:
    listed = len(client.get(f"/api/v1/model/{DATASET}/times/list").json())
    counted = client.get(f"/api/v1/model/{DATASET}/times").json()["count"]
    assert listed == counted


def test_timestamps_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/timestamps")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 8
    assert entries[0]["index"] == 0
    assert entries[-1]["index"] == 7
    assert entries[0]["iso"].startswith("2024-01-01")
    indexes = [e["index"] for e in entries]
    assert indexes == sorted(indexes)


def test_extent_endpoint(client: TestClient) -> None:
    response = client.get(f"/api/v1/model/{DATASET}/extent")
    assert response.status_code == 200
    extent = response.json()
    assert extent["dataset_id"] == DATASET
    assert extent["time_range"]["count"] == 8
    assert extent["time_range"]["start"].startswith("2024-01-01")
    assert extent["depth_levels"] == pytest_approx([0.0, 10.0, 20.0, 50.0, 100.0])
    assert extent["vertical_kind"] == "depth"
    bounds = extent["spatial_bounds"]
    assert (bounds["west"], bounds["east"], bounds["south"], bounds["north"]) == (
        60.0,
        71.0,
        5.0,
        14.0,
    )
    assert {"temperature", "salinity", "u", "v"} <= set(extent["variables"])
    # Extent agrees with the individual endpoints it summarises.
    depths = client.get(f"/api/v1/model/{DATASET}/depths").json()
    assert extent["depth_levels"] == pytest_approx(depths)


def test_extent_unknown_dataset_404(client: TestClient) -> None:
    response = client.get("/api/v1/model/does_not_exist/extent")
    assert response.status_code == 404


# --- batch slicing -----------------------------------------------------------


def test_slice_batch_endpoint(client: TestClient) -> None:
    body = {
        "slices": [
            {"variable": "temperature", "time_index": 0},
            {
                "variable": "salinity",
                "time_index": 1,
                "depth_meters": 10.0,
                "west": 62.0,
                "east": 66.0,
                "south": 6.0,
                "north": 9.0,
            },
        ]
    }
    response = client.post(f"/api/v1/model/{DATASET}/slice/batch", json=body)
    assert response.status_code == 200
    slices = response.json()
    assert len(slices) == 2
    # Order mirrors request order.
    assert slices[0]["variable"] == "temperature"
    assert slices[1]["variable"] == "salinity"
    assert len(slices[0]["latitude"]) == 10
    assert slices[1]["depth_meters"] == 10.0
    assert len(slices[1]["latitude"]) < 10  # bbox applied
    # Batch results match single-slice responses exactly.
    single = client.get(
        f"/api/v1/model/{DATASET}/slice",
        params={"variable": "temperature", "time_index": 0},
    ).json()
    assert slices[0]["values"] == single["values"]
    assert slices[0]["time"] == single["time"]


def test_slice_batch_rejects_more_than_ten(client: TestClient) -> None:
    body = {"slices": [{"variable": "temperature"}] * 11}
    response = client.post(f"/api/v1/model/{DATASET}/slice/batch", json=body)
    assert response.status_code == 422


def test_slice_batch_partial_bbox_422(client: TestClient) -> None:
    body = {"slices": [{"variable": "temperature", "west": 60.0}]}
    response = client.post(f"/api/v1/model/{DATASET}/slice/batch", json=body)
    assert response.status_code == 422


def test_slice_batch_invalid_bbox_order_422(client: TestClient) -> None:
    body = {
        "slices": [
            {
                "variable": "temperature",
                "west": 70.0,
                "east": 60.0,
                "south": 0.0,
                "north": 10.0,
            }
        ]
    }
    response = client.post(f"/api/v1/model/{DATASET}/slice/batch", json=body)
    assert response.status_code == 422


def test_slice_batch_unknown_variable_404(client: TestClient) -> None:
    body = {
        "slices": [
            {"variable": "temperature", "time_index": 0},
            {"variable": "oxygen", "time_index": 0},
        ]
    }
    response = client.post(f"/api/v1/model/{DATASET}/slice/batch", json=body)
    assert response.status_code == 404


# --- BUG 4: optional Argo source must never break the app --------------------


def test_argo_endpoints_503_when_client_uninitialized(
    monkeypatch: object, settings  # noqa: ANN001
) -> None:
    from fastapi.testclient import TestClient

    from app import main as app_main

    def _boom(_settings: object) -> object:
        raise RuntimeError("argopy exploded during init")

    monkeypatch.setattr(app_main, "create_argo_client", _boom)  # type: ignore[attr-defined]
    app = app_main.create_app(settings)
    with TestClient(app) as argo_client:
        response = argo_client.get("/api/v1/argo/floats")
        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()
        # The rest of the API keeps working.
        assert argo_client.get("/api/v1/model/datasets").status_code == 200
