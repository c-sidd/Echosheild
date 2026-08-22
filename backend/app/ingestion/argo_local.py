"""Local Argo observation client.

Reads Argo-profile NetCDF files that already exist under ``ARGO_CACHE_DIR``
(``data/argo_cache``). No downloads happen here; when the cache is empty the
API transparently falls back to the remote argopy-based client.

Supported file layout (tolerant to naming/case):

* dimension ``N_PROF`` (multi-profile single-float or multi-float files)
* platform id: ``PLATFORM_NUMBER``
* cycle: ``CYCLE_NUMBER``
* time: ``JULD`` / ``TIME``
* location: ``LATITUDE`` / ``LONGITUDE``
* measurements: ``PRES``, ``TEMP``, ``PSAL`` (+ ``*_ADJUSTED`` variants)

Pressure is reported as pressure (``pressure_dbar``). Depth is only filled
when a file actually carries a depth variable — it is never derived from
pressure by this client.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.config import Settings
from app.models.schemas import (
    ArgoFloatDetail,
    ArgoFloatSummary,
    ArgoProfile,
    ArgoProfilePoint,
    SpatialBounds,
    TimeRange,
)

_LOG = logging.getLogger("echoshield.argo_local")

_PLATFORM_KEYS = ("platform_number", "platform")
_CYCLE_KEYS = ("cycle_number", "cycle")
_TIME_KEYS = ("juld", "time", "ftime")
_LAT_KEYS = ("latitude", "lat")
_LON_KEYS = ("longitude", "lon")
_PRES_KEYS = ("pres_adjusted", "pres", "pressure")
_TEMP_KEYS = ("temp_adjusted", "temp", "temperature")
_PSAL_KEYS = ("psal_adjusted", "psal", "salinity")


def _pick(keys: tuple[str, ...], available: set[str]) -> str | None:
    lowered = {name.lower(): name for name in available}
    for candidate in keys:
        if candidate in lowered:
            return lowered[candidate]
    return None


@dataclass(frozen=True)
class _Level:
    pressure_dbar: float | None
    temperature_c: float | None
    salinity_psu: float | None


@dataclass(frozen=True)
class _ProfileRecord:
    wmo: int
    cycle: int
    latitude: float | None
    longitude: float | None
    time: pd.Timestamp | None
    levels: tuple[_Level, ...]


def _finite(value: object) -> float | None:
    try:
        value_f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value_f if math.isfinite(value_f) else None


class LocalArgoClient:
    """Argo provider serving whatever real profiles exist in the cache."""

    source: str = "local"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- internal helpers ------------------------------------------------------

    def _candidate_files(self) -> list[Path]:
        root = self._settings.argo_cache_dir
        if not root.is_dir():
            return []
        return sorted(root.glob("*.nc"))

    def _open(self, path: Path) -> xr.Dataset | None:
        """Open one cached file; unreadable/foreign files are skipped."""
        try:
            ds = xr.open_dataset(path, decode_times=True)
        except Exception as exc:  # noqa: BLE001 - corrupt files are isolated
            _LOG.warning("local_argo_unreadable file=%s error=%s", path.name, exc)
            return None
        variables_lower = {str(v).lower() for v in ds.variables}
        has_platform = any(key in variables_lower for key in _PLATFORM_KEYS)
        if "N_PROF" not in {str(s).upper() for s in ds.sizes} and not has_platform:
            ds.close()
            return None
        return ds

    def _column(self, ds: xr.Dataset, keys: tuple[str, ...]) -> np.ndarray | None:
        name = _pick(keys, set(map(str, ds.variables)))
        if name is None:
            return None
        values = np.asarray(ds[name].values)
        if values.dtype.kind not in "fiu":
            return None
        filled = np.asarray(
            values.filled(np.nan) if hasattr(values, "filled") else values, dtype=float
        )
        return filled

    def _iter_profiles(self, ds: xr.Dataset) -> Iterator[_ProfileRecord]:
        platform = self._column(ds, _PLATFORM_KEYS)
        cycle = self._column(ds, _CYCLE_KEYS)
        lat = self._column(ds, _LAT_KEYS)
        lon = self._column(ds, _LON_KEYS)
        pres = self._column(ds, _PRES_KEYS)
        temp = self._column(ds, _TEMP_KEYS)
        psal = self._column(ds, _PSAL_KEYS)

        time_name = _pick(_TIME_KEYS, set(map(str, ds.variables)))
        times: np.ndarray = (
            np.asarray(ds[time_name].values).ravel()
            if time_name is not None
            else np.array([], dtype="datetime64[ns]")
        )

        n_prof = (
            int(ds.sizes.get("N_PROF", 1))
            if "N_PROF" in ds.sizes
            else len(platform)
            if platform is not None
            else 0
        )
        for i in range(n_prof):
            wmo = _finite(platform[i]) if platform is not None and i < len(platform) else None
            cycle_no = _finite(cycle[i]) if cycle is not None and i < len(cycle) else None
            stamp: pd.Timestamp | None = None
            if times.size > i:
                with np.errstate(invalid="ignore"):
                    stamp = pd.Timestamp(times[i]) if not np.isnat(times[i]) else None

            levels: list[_Level] = []
            n_levels = pres.shape[1] if pres is not None and pres.ndim == 2 else 0
            for level in range(n_levels):
                pressure = _finite(pres[i, level]) if pres is not None else None
                temperature = _finite(temp[i, level]) if temp is not None else None
                salinity = _finite(psal[i, level]) if psal is not None else None
                if pressure is None and temperature is None and salinity is None:
                    continue
                levels.append(
                    _Level(
                        pressure_dbar=pressure,
                        temperature_c=temperature,
                        salinity_psu=salinity,
                    )
                )

            yield _ProfileRecord(
                wmo=int(wmo) if wmo else 0,
                cycle=int(cycle_no) if cycle_no else i + 1,
                latitude=_finite(lat[i]) if lat is not None and i < len(lat) else None,
                longitude=_finite(lon[i]) if lon is not None and i < len(lon) else None,
                time=stamp,
                levels=tuple(levels),
            )

    def _all_profiles(self) -> list[tuple[Path, list[_ProfileRecord]]]:
        out: list[tuple[Path, list[_ProfileRecord]]] = []
        for path in self._candidate_files():
            ds = self._open(path)
            if ds is None:
                continue
            try:
                records = [r for r in self._iter_profiles(ds) if r.wmo]
            finally:
                ds.close()
            if records:
                out.append((path, records))
        return out

    # -- public surface (mirrors RemoteArgoClient) ------------------------------

    def search_floats(
        self,
        *,
        lon_min: float = -180.0,
        lon_max: float = 180.0,
        lat_min: float = -90.0,
        lat_max: float = 90.0,
        start: str | None = None,
        end: str | None = None,
        max_floats: int = 50,
    ) -> list[ArgoFloatSummary]:
        start_ts = pd.Timestamp(start) if start else None
        end_ts = pd.Timestamp(end) if end else None

        max_cycle: dict[int, int] = {}
        last_seen: dict[int, _ProfileRecord] = {}
        matched: set[int] = set()

        for _, records in self._all_profiles():
            for record in records:
                if record.latitude is None or record.longitude is None:
                    continue
                in_box = (
                    lon_min <= record.longitude <= lon_max and lat_min <= record.latitude <= lat_max
                )
                in_window = True
                if start_ts and record.time is not None:
                    in_window &= record.time >= start_ts
                if end_ts and record.time is not None:
                    in_window &= record.time <= end_ts
                if not (in_box and in_window):
                    continue
                matched.add(record.wmo)
                max_cycle[record.wmo] = max(max_cycle.get(record.wmo, 0), record.cycle)
                previous = last_seen.get(record.wmo)
                if previous is None or (
                    record.time and (previous.time is None or record.time > previous.time)
                ):
                    last_seen[record.wmo] = record

        summaries: list[ArgoFloatSummary] = []
        for wmo in sorted(matched)[:max_floats]:
            record = last_seen[wmo]
            lon = record.longitude
            lat = record.latitude
            if lon is None or lat is None:
                continue
            summaries.append(
                ArgoFloatSummary(
                    platform_wmo=wmo,
                    cycles=max_cycle[wmo],
                    last_location=(lon, lat),
                    last_time=str(record.time) if record.time is not None else None,
                )
            )
        if not summaries:
            raise KeyError("no local Argo floats matched the requested region")
        return summaries

    def float_detail(self, wmo: int, *, max_profiles: int = 5) -> ArgoFloatDetail:
        profiles: list[ArgoProfile] = []
        for _, records in self._all_profiles():
            for record in records:
                if record.wmo != wmo or not record.levels:
                    continue
                points = [
                    ArgoProfilePoint(
                        pressure_dbar=level.pressure_dbar,
                        depth_meters=None,  # never derived silently
                        temperature_c=level.temperature_c,
                        salinity_psu=level.salinity_psu,
                    )
                    for level in record.levels
                ]
                profiles.append(
                    ArgoProfile(
                        platform_wmo=wmo,
                        cycle_number=record.cycle,
                        time=str(record.time) if record.time is not None else None,
                        latitude=record.latitude,
                        longitude=record.longitude,
                        points=points,
                    )
                )
        if not profiles:
            raise KeyError(f"local Argo float {wmo} not found in cache")

        profiles.sort(key=lambda p: p.cycle_number or 0)
        stamps = [p.time for p in profiles if p.time]
        lats = [float(p.latitude) for p in profiles if p.latitude is not None]
        lons = [float(p.longitude) for p in profiles if p.longitude is not None]
        return ArgoFloatDetail(
            platform_wmo=wmo,
            profiles_available=len(profiles),
            time_range=(
                TimeRange(start=min(stamps), end=max(stamps), count=len(stamps)) if stamps else None
            ),
            spatial_bounds=(
                SpatialBounds(west=min(lons), east=max(lons), south=min(lats), north=max(lats))
                if lats and lons
                else None
            ),
            recent_profiles=profiles[-max_profiles:],
        )

    def float_profile(self, wmo: int, cycle: int | None = None) -> ArgoProfile:
        detail = self.float_detail(wmo, max_profiles=10_000)
        if cycle is None:
            return detail.recent_profiles[-1]
        for profile in detail.recent_profiles:
            if profile.cycle_number == cycle:
                return profile
        raise KeyError(f"profile cycle {cycle} not found for float {wmo}")
