"""Health / readiness endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "echoshield-backend"
    assert payload["version"]
    assert payload["environment"] in {"development", "staging", "production"}
    # Optional scientific dependencies are reported individually.
    deps = payload["optional_dependencies"]
    assert {"xarray", "netCDF4", "argopy"} <= set(deps)
    assert all(state == "available" for state in deps.values())
    # THREDDS is not configured in test settings.
    assert payload["thredds_configured"] is False


def test_readiness_reports_dependencies(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    names = {c["name"]: c for c in payload["checks"]}
    assert names["data_directory"]["status"] == "ok"
    # No THREDDS / ERDDAP configured in the test settings.
    assert names["thredds"]["status"] == "not_configured"
    assert names["incois_erddap"]["status"] == "not_configured"


def test_root_redirects_to_docs_info(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_openapi_schema_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = [
        "/api/v1/health",
        "/api/v1/health/ready",
        "/api/v1/model/datasets",
        "/api/v1/model/{dataset_id}/metadata",
        "/api/v1/model/{dataset_id}/variables",
        "/api/v1/model/{dataset_id}/times",
        "/api/v1/model/{dataset_id}/depths",
        "/api/v1/model/{dataset_id}/slice",
        "/api/v1/model/{dataset_id}/profile",
        "/api/v1/model/{dataset_id}/point",
        "/api/v1/model/{dataset_id}/currents",
        "/api/v1/model/{dataset_id}/services",
        "/api/v1/argo/floats",
        "/api/v1/glider/status",
    ]
    for path in expected:
        assert path in paths, f"missing OpenAPI path {path}"
