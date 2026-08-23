from __future__ import annotations

import pandas as pd
import pytest

from app.services.glider import ErddapGliderClient


@pytest.mark.asyncio
async def test_glider_adapter_normalizes_common_columns(monkeypatch):
    client = ErddapGliderClient("https://example.test/erddap/tabledap/gliders")
    frame = pd.DataFrame([{
        "trajectory": "GLIDER-1",
        "latitude": 12.5,
        "longitude": 67.2,
        "time": "2026-08-01T00:00:00Z",
        "depth": 100.0,
        "temperature": 24.1,
        "salinity": 35.2,
        "chlorophyll": 0.8,
    }])

    async def fake_read(mission_id=None):
        return frame

    monkeypatch.setattr(client, "_read", fake_read)
    missions = await client.search_missions()
    assert missions[0].mission_id == "GLIDER-1"
    assert missions[0].latitude == 12.5
    assert missions[0].longitude == 67.2

    profile = await client.get_profiles("GLIDER-1")
    assert profile.points[0].depth_meters == 100.0
    assert profile.points[0].temperature_c == 24.1
    assert profile.points[0].salinity_psu == 35.2
    assert profile.points[0].chlorophyll == 0.8
