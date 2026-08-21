"""NetCDF parser tests against the synthetic sample dataset."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion import netcdf_parser as ncp
from app.testing_utils import create_synthetic_dataset


@pytest.fixture()
def ds(sample_netcdf_file: Path):
    dataset = ncp.open_dataset(sample_netcdf_file)
    yield dataset
    ncp.close_dataset(dataset)


def test_open_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ncp.open_dataset(tmp_path / "missing.nc")


def test_open_rejects_non_netcdf_suffix(tmp_path: Path) -> None:
    evil = tmp_path / "not_ocean.txt"
    evil.write_text("hello")
    with pytest.raises(ncp.NetCDFParseError):
        ncp.open_dataset(evil)


def test_metadata_extraction(ds) -> None:
    metadata = ncp.build_metadata(ds, dataset_id="local_synthetic_ocean")
    assert metadata.title.startswith("EchoShield synthetic")
    assert set(metadata.dimensions) >= {"time", "depth", "latitude", "longitude"}
    var_names = {v.name for v in metadata.variables}
    assert {"temperature", "salinity", "u", "v"} <= var_names
    assert metadata.time_range is not None and metadata.time_range.count == 8
    assert metadata.depth_range is not None and metadata.depth_range.min_meters == 0.0
    assert metadata.spatial_bounds is not None
    assert metadata.spatial_bounds.south == pytest.approx(5.0)


def test_variable_discovery_excludes_coords(ds) -> None:
    variables = ncp.list_variables(ds)
    names = [v.name for v in variables]
    assert "latitude" not in names and "longitude" not in names
    temp = next(v for v in variables if v.name == "temperature")
    assert temp.units == "degC"
    assert temp.standard_name == "sea_water_temperature"


def test_coordinate_detection(ds) -> None:
    cmap = ncp.CoordinateMap(ds)
    assert cmap.lat == "latitude"
    assert cmap.lon == "longitude"
    assert cmap.time == "time"
    assert cmap.depth == "depth"


def test_time_range_and_values(ds) -> None:
    time_range = ncp.get_time_range(ds)
    assert time_range is not None
    assert time_range.start == "2024-01-01T00:00:00"
    values = ncp.get_time_values(ds)
    assert len(values) == time_range.count


def test_depth_range_meters(ds) -> None:
    depths = ncp.get_depth_values_meters(ds)
    assert depths == pytest.approx([0.0, 10.0, 20.0, 50.0, 100.0])
    depth_range = ncp.get_depth_range(ds)
    assert depth_range is not None and depth_range.positive_down is True


def test_slice_shape_and_nan_safety(ds) -> None:
    slice_ = ncp.read_slice(ds, "temperature", time_index=0)
    assert len(slice_.latitude) == 10
    assert len(slice_.longitude) == 12
    assert len(slice_.values) == 10
    # Cell (0,0) was deliberately NaN -> must be serialized as null.
    assert slice_.values[0][0] is None
    assert any(v is not None for row in slice_.values[1:] for v in row)
    assert slice_.units == "degC"


def test_slice_with_depth_selection(ds) -> None:
    shallow = ncp.read_slice(ds, "temperature", time_index=0, depth_meters=11.0)
    assert shallow.depth_meters == pytest.approx(10.0)


def test_slice_downsampling_respects_limit(ds) -> None:
    tiny = ncp.read_slice(ds, "temperature", max_grid_points=20)
    cells = len(tiny.latitude) * len(tiny.longitude)
    assert cells <= 20 * 2 + 2  # stride math overshoots by at most one row/col
    assert "longitude_stride" in tiny.downsampling


def test_slice_unknown_variable(ds) -> None:
    with pytest.raises(KeyError):
        ncp.read_slice(ds, "not_a_var")


def test_slice_invalid_timestep(ds) -> None:
    with pytest.raises(IndexError):
        ncp.read_slice(ds, "temperature", time_index=99)


def test_profile_nearest_grid(ds) -> None:
    profile = ncp.read_profile(ds, "temperature", latitude=5.4, longitude=60.9, time_index=0)
    assert profile.latitude == pytest.approx(5.0)
    assert len(profile.depths_meters) == len(profile.values)
    assert profile.depths_meters[0] == pytest.approx(0.0)


def test_point_sample_multiple_variables(ds) -> None:
    sample = ncp.read_point(
        ds,
        ["temperature", "salinity"],
        latitude=7.0,
        longitude=63.0,
        time_index=1,
        depth_meters=20.0,
    )
    assert set(sample.values) == {"temperature", "salinity"}
    assert sample.nearest_grid["latitude"] == pytest.approx(7.0)
    assert sample.units["temperature"] == "degC"


def test_point_unknown_variable(ds) -> None:
    with pytest.raises(KeyError):
        ncp.read_point(ds, ["bogus"], latitude=7.0, longitude=63.0)


def test_synthetic_dataset_is_labelled() -> None:
    ds2 = create_synthetic_dataset(n_time=2)
    assert "SYNTHETIC" in str(ds2.attrs["summary"])
