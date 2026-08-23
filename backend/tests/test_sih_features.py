from __future__ import annotations

import numpy as np
import xarray as xr

from app.ingestion.variable_mapping import classify_dataset_variables
from app.models.schemas import ArgoProfile, ArgoProfilePoint, PointSample
from app.services.comparison import compare_profile


def test_incois_geostrophic_aliases_are_detected() -> None:
    ds = xr.Dataset(
        data_vars={
            "GEO_U": (("lat", "lon"), np.ones((2, 2), dtype=np.float32)),
            "GEO_V": (("lat", "lon"), np.ones((2, 2), dtype=np.float32)),
        },
        coords={"lat": [0.0, 1.0], "lon": [70.0, 71.0]},
    )
    mapping = classify_dataset_variables(ds)
    assert mapping["u_current"] == "GEO_U"
    assert mapping["v_current"] == "GEO_V"


def test_model_observation_comparison_calculates_metrics() -> None:
    class FakeModel:
        def get_times(self, dataset_id):
            return ["2026-01-01T00:00:00Z"]

        def read_point(self, dataset_id, variables, *, latitude, longitude, time_index, depth_meters):
            return PointSample(
                dataset_id=dataset_id,
                latitude=latitude,
                longitude=longitude,
                time="2026-01-01T00:00:00Z",
                depth_meters=depth_meters,
                values={"temperature": 21.0, "salinity": 35.5},
                units={"temperature": "degC", "salinity": "PSU"},
            )

    profile = ArgoProfile(
        platform_wmo=1234567,
        cycle_number=10,
        time="2026-01-01T00:05:00Z",
        latitude=15.0,
        longitude=72.0,
        points=[
            ArgoProfilePoint(depth_meters=10.0, temperature_c=20.0, salinity_psu=35.0),
            ArgoProfilePoint(depth_meters=50.0, temperature_c=20.5, salinity_psu=35.0),
        ],
    )
    result = compare_profile(FakeModel(), "model", profile)
    assert result.model_time_index == 0
    assert result.metrics.temperature_count == 2
    assert result.metrics.temperature_bias_c == 0.75
    assert result.metrics.temperature_rmse_c == 0.790569
    assert result.metrics.salinity_bias_psu == 0.5
