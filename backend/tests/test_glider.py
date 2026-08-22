"""Glider API + collection-alias tests (no source configured = explicit response)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_glider_status_reports_unconfigured(client: TestClient) -> None:
    response = client.get("/api/v1/glider/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["provider"] == "null"


def test_glider_missions_not_configured(client: TestClient) -> None:
    response = client.get("/api/v1/glider/missions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_configured"
    assert "GLIDER_DATA_URL" in payload["detail"]


def test_gliders_collection_alias(client: TestClient) -> None:
    """Spec-named GET /gliders stays functional before any provider exists."""
    response = client.get("/api/v1/gliders")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


def test_single_glider_alias(client: TestClient) -> None:
    response = client.get("/api/v1/gliders/sg123")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
