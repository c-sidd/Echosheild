"""Canonical variable/coordinate resolution driven by CF metadata.

Maps real-world dataset naming (including INCOIS products that use TEMP,
SAL, TAXIS, XAXIS, YAXIS, ZAX) onto EchoShield's canonical concepts:

* variables: temperature, salinity, u_current, v_current, chlorophyll
* coordinates: time, latitude, longitude, vertical (depth *or* pressure)

Resolution order (most trustworthy first):

1. CF ``standard_name``
2. ``axis`` attribute (T/X/Y/Z)
3. ``units`` (e.g. ``dbar`` identifies pressure, ``degrees_north`` latitude)
4. known variable-name candidates

Nothing here renames data on disk; it only resolves identities so services
can address the correct source variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import xarray as xr

CanonicalVariable = Literal[
    "temperature",
    "salinity",
    "u_current",
    "v_current",
    "chlorophyll",
]

VerticalKind = Literal["depth", "pressure", "other"]

# --- name candidates (lower-case matching) -----------------------------------

_TEMPERATURE_NAMES = (
    "temp",
    "temperature",
    "thetao",
    "potemp",
    "sst",
    "sea_water_temperature",
)
_SALINITY_NAMES = (
    "sal",
    "salinity",
    "psal",
    "so",
    "sss",
    "sea_water_salinity",
)
_U_NAMES = (
    "u",
    "uo",
    "usurf",
    "u_current",
    "ucur",
    "eastward_velocity",
    "eastward_sea_water_velocity",
)
_V_NAMES = (
    "v",
    "vo",
    "vsurf",
    "v_current",
    "vcur",
    "northward_velocity",
    "northward_sea_water_velocity",
)
_CHLOROPHYLL_NAMES = (
    "chl",
    "chla",
    "chlorophyll",
    "chlor_a",
    "chlorophyll_a",
)

_TIME_NAMES = (
    "time",
    "taxis",
    "t",
    "juld",
    "ftime",
)
_LATITUDE_NAMES = (
    "lat",
    "latitude",
    "yaxis",
    "y",
    "latitude_nv",
)
_LONGITUDE_NAMES = (
    "lon",
    "longitude",
    "xaxis",
    "x",
    "longitude_nv",
)
_VERTICAL_NAMES = (
    "depth",
    "zax",
    "lev",
    "level",
    "pres",
    "pressure",
    "pres_adjusted",
    "depth_m",
    "z",
)

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


# --- coordinate resolution ----------------------------------------------------


@dataclass(frozen=True)
class ResolvedCoordinates:
    """Canonical coordinate identity for one dataset."""

    time: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    vertical: str | None = None
    vertical_kind: VerticalKind = "other"
    vertical_units: str | None = None
    mapping: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {
            "time": self.time,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "vertical": self.vertical,
        }
        return {key: value for key, value in result.items() if value is not None}


def _resolve_by_axis(
    ds: xr.Dataset,
    axis_letter: str,
    fallback_names: tuple[str, ...],
    *,
    unit_tokens: tuple[str, ...] = (),
    standard_tokens: tuple[str, ...] = (),
) -> str | None:
    """Resolve one canonical axis via attrs, then unit hints, then names."""
    lowered: dict[str, str] = {str(n).lower(): str(n) for n in ds.variables}
    for name in ds.variables:
        attrs = _attrs_of(ds[name])
        axis_attr = attrs.get("axis", "").upper()
        if axis_attr == axis_letter:
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
    if _matches_unit(attrs, *_PRESSURE_UNIT_TOKENS) or _matches_standard_name(
        attrs, "sea_water_pressure"
    ):
        return "pressure", units
    if _matches_unit(attrs, *_METER_TOKENS) or _matches_standard_name(attrs, "depth"):
        return "depth", units
    positive = attrs.get("positive", "").lower()
    if positive == "down":
        return "depth", units
    if units:
        return "other", units
    return "depth", units


def resolve_coordinates(ds: xr.Dataset) -> ResolvedCoordinates:
    """Identify time / latitude / longitude / vertical coordinates."""
    lowered: dict[str, str] = {str(n).lower(): str(n) for n in ds.variables}

    time_name = _resolve_by_axis(
        ds,
        "T",
        _TIME_NAMES,
        standard_tokens=("time",),
    )

    lat_name = _resolve_by_axis(
        ds,
        "Y",
        _LATITUDE_NAMES,
        unit_tokens=("degrees_north", "degree_north"),
        standard_tokens=("latitude",),
    )
    lon_name = _resolve_by_axis(
        ds,
        "X",
        _LONGITUDE_NAMES,
        unit_tokens=("degrees_east", "degree_east"),
        standard_tokens=("longitude",),
    )
    # Guard against unit-less datasets where both axes fell back to bare
    # candidate collisions (e.g. dims literally named x/y are fine, but make
    # sure we never resolve the same variable twice).
    if lon_name is not None and lon_name == lat_name:
        lon_name = None

    vertical_name: str | None = None
    for candidate in _VERTICAL_NAMES:
        if candidate in lowered:
            vertical_name = lowered[candidate]
            break
    if vertical_name is None:
        for name in ds.variables:
            attrs = _attrs_of(ds[name])
            if attrs.get("axis", "").upper() == "Z" or _matches_standard_name(
                attrs, "sea_water_pressure", "depth"
            ):
                vertical_name = str(name)
                break

    vertical_kind: VerticalKind = "other"
    vertical_units: str | None = None
    if vertical_name is not None:
        vertical_kind, vertical_units = _vertical_kind(ds, vertical_name)

    mapping: dict[str, str] = {}
    if time_name:
        mapping["time"] = time_name
    if lat_name:
        mapping["latitude"] = lat_name
    if lon_name:
        mapping["longitude"] = lon_name
    if vertical_name:
        mapping[
            "depth"
            if vertical_kind == "depth"
            else "pressure"
            if vertical_kind == "pressure"
            else "vertical"
        ] = vertical_name

    return ResolvedCoordinates(
        time=time_name,
        latitude=lat_name,
        longitude=lon_name,
        vertical=vertical_name,
        vertical_kind=vertical_kind,
        vertical_units=vertical_units,
        mapping=mapping,
    )


# --- data-variable classification ----------------------------------------------


def classify_variable(name: str, attrs: dict[str, str]) -> CanonicalVariable | None:
    """Classify one data variable against canonical concepts via metadata."""
    lower = name.lower()

    if _matches_standard_name(attrs, "eastward_sea_water_velocity") or lower in _U_NAMES:
        return "u_current"
    if _matches_standard_name(attrs, "northward_sea_water_velocity") or lower in _V_NAMES:
        return "v_current"
    if (
        _matches_standard_name(attrs, "mass_concentration_of_chlorophyll", "chlorophyll")
        or lower in _CHLOROPHYLL_NAMES
    ):
        return "chlorophyll"

    is_temp_like = (
        _matches_standard_name(attrs, "sea_water_temperature", "sea_water_potential_temperature")
        or lower in _TEMPERATURE_NAMES
    )
    if is_temp_like:
        return "temperature"
    # Temperature-like units as a secondary hint (K, degC, Celsius...).
    if _matches_unit(attrs, "degc", "°c", "celsius", " k", "kelvin") and any(
        token in lower for token in ("temp", "theta", "sst")
    ):
        return "temperature"

    if _matches_standard_name(attrs, "sea_water_practical_salinity", "sea_water_salinity") or (
        lower in _SALINITY_NAMES
    ):
        return "salinity"
    if lower.startswith("sal") or lower.startswith("psal"):
        return "salinity"
    if _matches_unit(attrs, "psu", "1e-3", "ppt", "practical salinity") and "sal" in lower:
        return "salinity"

    return None


def classify_dataset_variables(ds: xr.Dataset) -> dict[CanonicalVariable, str]:
    """Return ``{canonical: source_name}`` for every recognised data variable."""
    found: dict[CanonicalVariable, str] = {}
    for name, da in ds.data_vars.items():
        canonical = classify_variable(str(name), _attrs_of(da))
        if canonical is not None and canonical not in found:
            found[canonical] = str(name)
    return found
