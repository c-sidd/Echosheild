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


def test_services_metadata_only_dataset_503(client: TestClient) -> None:
    # The synthetic local dataset has no THREDDS/WMS services configured.
    response = client.get(f"/api/v1/model/{DATASET}/services")
    assert response.status_code == 503
