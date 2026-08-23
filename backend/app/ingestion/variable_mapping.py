"""Canonical variable/coordinate resolution driven by CF metadata.

Maps real-world dataset naming onto EchoShield canonical concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import xarray as xr

CanonicalVariable = Literal["temperature", "salinity", "u_current", "v_current", "chlorophyll"]
VerticalKind = Literal["depth", "pressure", "other"]

_TEMPERATURE_NAMES = ("temp", "temperature", "thetao", "potemp", "sst", "sea_water_temperature")
_SALINITY_NAMES = ("sal", "salinity", "psal", "so", "sss", "sea_water_salinity")
_U_NAMES = ("u", "uo", "usurf", "u_current", "ucur", "eastward_velocity", "eastward_sea_water_velocity", "geo_u", "geostrophic_u")
_V_NAMES = ("v", "vo", "vsurf", "v_current", "vcur", "northward_velocity", "northward_sea_water_velocity", "geo_v", "geostrophic_v")
_CHLOROPHYLL_NAMES = ("chl", "chla", "chlorophyll", "chlor_a", "chlorophyll_a", "chlorophyll_concentration")
_TIME_NAMES = ("time", "taxis", "t", "juld", "ftime")
_LATITUDE_NAMES = ("lat", "latitude", "yaxis", "y", "latitude_nv")
_LONGITUDE_NAMES = ("lon", "longitude", "xaxis", "x", "longitude_nv")
_VERTICAL_NAMES = ("depth", "zax", "lev", "level", "pres", "pressure", "pres_adjusted", "depth_m", "z")
_PRESSURE_UNIT_TOKENS = ("dbar", "decibar", "pascal", " pa", "hpa")
_METER_TOKENS = ("m", "meter", "metre")


def _attrs_of(da: xr.DataArray) -> dict[str, str]:
    lowered: dict[str, str] = {}
    for key, value in da.attrs.items():
        if isinstance(value, (str, bytes, int, float)):
            text = value.decode(errors="replace") if isinstance(value, bytes) else str(value)
            lowered[str(key).lower()] = text.strip()
    return lowered


def _matches_standard_name(attrs: dict[str, str], *tokens: str) -> bool:
    standard = attrs.get("standard_name", "").lower()
    return any(token in standard for token in tokens)


def _matches_unit(attrs: dict[str, str], *tokens: str) -> bool:
    units = attrs.get("units", "").lower()
    return any(token in units for token in tokens)


@dataclass(frozen=True)
class ResolvedCoordinates:
    time: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    vertical: str | None = None
    vertical_kind: VerticalKind = "other"
    vertical_units: str | None = None
    mapping: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str | None]:
        result = {"time": self.time, "latitude": self.latitude, "longitude": self.longitude, "vertical": self.vertical}
        return {key: value for key, value in result.items() if value is not None}


def _resolve_by_axis(ds: xr.Dataset, axis_letter: str, fallback_names: tuple[str, ...], *, unit_tokens: tuple[str, ...] = (), standard_tokens: tuple[str, ...] = ()) -> str | None:
    lowered = {str(n).lower(): str(n) for n in ds.variables}
    for name in ds.variables:
        attrs = _attrs_of(ds[name])
        if attrs.get("axis", "").upper() == axis_letter:
            return str(name)
        if standard_tokens and _matches_standard_name(attrs, *standard_tokens):
            return str(name)
        if unit_tokens and _matches_unit(attrs, *unit_tokens):
            return str(name)
    for candidate in fallback_names:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _vertical_kind(ds: xr.Dataset, vertical_name: str) -> tuple[VerticalKind, str | None]:
    attrs = _attrs_of(ds[vertical_name])
    units = attrs.get("units")
    if _matches_unit(attrs, *_PRESSURE_UNIT_TOKENS) or _matches_standard_name(attrs, "sea_water_pressure"):
        return "pressure", units
    if _matches_unit(attrs, *_METER_TOKENS) or _matches_standard_name(attrs, "depth"):
        return "depth", units
    if attrs.get("positive", "").lower() == "down":
        return "depth", units
    return ("other", units) if units else ("depth", units)


def resolve_coordinates(ds: xr.Dataset) -> ResolvedCoordinates:
    lowered = {str(n).lower(): str(n) for n in ds.variables}
    time_name = _resolve_by_axis(ds, "T", _TIME_NAMES, standard_tokens=("time",))
    lat_name = _resolve_by_axis(ds, "Y", _LATITUDE_NAMES, unit_tokens=("degrees_north", "degree_north"), standard_tokens=("latitude",))
    lon_name = _resolve_by_axis(ds, "X", _LONGITUDE_NAMES, unit_tokens=("degrees_east", "degree_east"), standard_tokens=("longitude",))
    if lon_name is not None and lon_name == lat_name:
        lon_name = None

    vertical_name = next((lowered[c] for c in _VERTICAL_NAMES if c in lowered), None)
    if vertical_name is None:
        for name in ds.variables:
            attrs = _attrs_of(ds[name])
            if attrs.get("axis", "").upper() == "Z" or _matches_standard_name(attrs, "sea_water_pressure", "depth"):
                vertical_name = str(name)
                break

    vertical_kind: VerticalKind = "other"
    vertical_units: str | None = None
    if vertical_name is not None:
        vertical_kind, vertical_units = _vertical_kind(ds, vertical_name)

    mapping: dict[str, str] = {}
    if time_name: mapping["time"] = time_name
    if lat_name: mapping["latitude"] = lat_name
    if lon_name: mapping["longitude"] = lon_name
    if vertical_name:
        mapping["depth" if vertical_kind == "depth" else "pressure" if vertical_kind == "pressure" else "vertical"] = vertical_name

    return ResolvedCoordinates(time_name, lat_name, lon_name, vertical_name, vertical_kind, vertical_units, mapping)


def classify_variable(name: str, attrs: dict[str, str]) -> CanonicalVariable | None:
    lower = name.lower()
    if _matches_standard_name(attrs, "eastward_sea_water_velocity") or lower in _U_NAMES:
        return "u_current"
    if _matches_standard_name(attrs, "northward_sea_water_velocity") or lower in _V_NAMES:
        return "v_current"
    if _matches_standard_name(attrs, "mass_concentration_of_chlorophyll", "chlorophyll") or lower in _CHLOROPHYLL_NAMES:
        return "chlorophyll"
    if _matches_standard_name(attrs, "sea_water_temperature", "sea_water_potential_temperature") or lower in _TEMPERATURE_NAMES:
        return "temperature"
    if _matches_unit(attrs, "degc", "°c", "celsius", " k", "kelvin") and any(token in lower for token in ("temp", "theta", "sst")):
        return "temperature"
    if _matches_standard_name(attrs, "sea_water_practical_salinity", "sea_water_salinity") or lower in _SALINITY_NAMES:
        return "salinity"
    if lower.startswith("sal") or lower.startswith("psal"):
        return "salinity"
    if _matches_unit(attrs, "psu", "1e-3", "ppt", "practical salinity") and "sal" in lower:
        return "salinity"
    return None


def classify_dataset_variables(ds: xr.Dataset) -> dict[CanonicalVariable, str]:
    found: dict[CanonicalVariable, str] = {}
    for name, da in ds.data_vars.items():
        canonical = classify_variable(str(name), _attrs_of(da))
        if canonical is not None and canonical not in found:
            found[canonical] = str(name)
    return found
