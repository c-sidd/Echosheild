"""Canonical variable-mapping tests against INCOIS-style schemas."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.ingestion import netcdf_parser as ncp
from app.ingestion.variable_mapping import (
    classify_dataset_variables,
    classify_variable,
    resolve_coordinates,
)


def _incois_style_dataset(*, vertical_units: str = "dbar") -> xr.Dataset:
    """Mimic INCOIS griddap naming: TEMP/SAL over TAXIS/XAXIS/YAXIS/ZAX."""
    taxis = pd.date_range("2024-01-01", periods=4, freq="10D")
    zax = np.array([0.0, 10.0, 20.0, 50.0])
    yaxis = np.arange(5.0, 9.0)
    xaxis = np.arange(60.0, 64.0)
    rng = np.random.default_rng(42)
    shape = (len(taxis), len(zax), len(yaxis), len(xaxis))
    return xr.Dataset(
        {
            "TEMP": (
                ("TAXIS", "ZAX", "YAXIS", "XAXIS"),
                rng.uniform(20, 30, shape),
                {
                    "units": "degC",
                    "long_name": "Sea water temperature",
                    "standard_name": "sea_water_temperature",
                },
            ),
            "SAL": (
                ("TAXIS", "ZAX", "YAXIS", "XAXIS"),
                rng.uniform(34, 36, shape),
                {
                    "units": "1e-3",
                    "long_name": "Sea water practical salinity",
                    "standard_name": "sea_water_practical_salinity",
                },
            ),
        },
        coords={
            "TAXIS": ("TAXIS", taxis, {"axis": "T", "standard_name": "time"}),
            "ZAX": ("ZAX", zax, {"units": vertical_units, "positive": "down"}),
            "YAXIS": ("YAXIS", yaxis, {"units": "degrees_north", "axis": "Y"}),
            "XAXIS": ("XAXIS", xaxis, {"units": "degrees_east", "axis": "X"}),
        },
    )


def test_incois_coordinates_resolve() -> None:
    resolved = resolve_coordinates(_incois_style_dataset())
    assert resolved.time == "TAXIS"
    assert resolved.latitude == "YAXIS"
    assert resolved.longitude == "XAXIS"
    assert resolved.vertical == "ZAX"


def test_pressure_is_not_labelled_depth() -> None:
    """dbar units must classify the vertical axis as pressure — never depth."""
    resolved = resolve_coordinates(_incois_style_dataset(vertical_units="dbar"))
    assert resolved.vertical_kind == "pressure"

    depth_like = resolve_coordinates(_incois_style_dataset(vertical_units="meters"))
    assert depth_like.vertical_kind == "depth"


def test_canonical_variable_classification() -> None:
    ds = _incois_style_dataset()
    canonical = classify_dataset_variables(ds)
    assert canonical == {"temperature": "TEMP", "salinity": "SAL"}


@pytest.mark.parametrize(
    ("name", "attrs", "expected"),
    [
        ("thetao", {"standard_name": "sea_water_potential_temperature"}, "temperature"),
        ("sst", {"units": "degC"}, "temperature"),
        ("so", {"standard_name": "sea_water_practical_salinity"}, "salinity"),
        ("uo", {"standard_name": "eastward_sea_water_velocity"}, "u_current"),
        ("vo", {"standard_name": "northward_sea_water_velocity"}, "v_current"),
        ("CHL", {"units": "mg m-3", "long_name": "chlorophyll-a"}, "chlorophyll"),
        ("oxygen", {"units": "ml/l"}, None),
        ("random_field", {}, None),
    ],
)
def test_classify_variable_matrix(name: str, attrs: dict[str, str], expected: str | None) -> None:
    assert classify_variable(name, attrs) == expected


def test_metadata_exposes_mapping_and_canonical_names() -> None:
    ds = _incois_style_dataset()
    metadata = ncp.build_metadata(ds, dataset_id="x")
    assert metadata.coordinate_mapping == {
        "time": "TAXIS",
        "latitude": "YAXIS",
        "longitude": "XAXIS",
        "pressure": "ZAX",
    }
    by_name = {v.name: v for v in metadata.variables}
    assert by_name["TEMP"].canonical_name == "temperature"
    assert by_name["SAL"].canonical_name == "salinity"


def test_profile_reports_pressure_kind_not_meters() -> None:
    """Pressure profiles keep dbar values and say so explicitly."""
    ds = _incois_style_dataset(vertical_units="dbar")
    profile = ncp.read_profile(ds, "TEMP", latitude=6.5, longitude=61.5, time_index=0)
    assert profile.vertical_kind == "pressure"
    assert profile.vertical_units == "dbar"
    # Values are raw dbar numbers — no silent conversion applied.
    raw_zax = [float(v) for v in ds["ZAX"].values]
    assert profile.depths_meters == sorted(raw_zax)

    depth_range = ncp.get_depth_range(ds)
    assert depth_range is not None
    assert depth_range.vertical_kind == "pressure"
    assert depth_range.vertical_units == "dbar"
