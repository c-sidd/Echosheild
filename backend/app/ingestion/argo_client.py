"""Argo ingestion built on top of ``argopy``.

The client converts argopy outputs into small, frontend-friendly structures.
All upstream access goes through a single seam (``_create_fetcher``) that is
easy to mock in tests; responses are cached on the filesystem.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.core.reliability.retry import call_with_retry
from app.models.schemas import (
    ArgoFloatDetail,
    ArgoFloatSummary,
    ArgoProfile,
    ArgoProfilePoint,
    SpatialBounds,
    TimeRange,
)
from app.services.cache import FileCache

if TYPE_CHECKING:  # pragma: no cover
    pass

_LOG = logging.getLogger("echoshield.argo")

_DEFAULT_BOX = [50.0, 100.0, -10.0, 30.0]  # Indian Ocean default (lon0, lon1, lat0, lat1)


class ArgoClientError(RuntimeError):
    """Raised when the Argo upstream cannot be reached or parsed."""


def _create_fetcher(
    source: str,
    dataset: str,
    mode: str = "standard",
    **options: Any,
) -> Any:
    """Seam for tests: build an argopy DataFetcher."""
    import argopy

    return argopy.DataFetcher(src=source, ds=dataset, mode=mode, **options)


def _clean(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class ArgoClient:
    """High-level Argo access (search, float detail, profile retrieval)."""

    def __init__(self, settings: Settings, cache: FileCache | None = None) -> None:
        self._settings = settings
        self._cache = cache or FileCache(settings.argo_cache_dir, settings.CACHE_TTL_SECONDS)

    # -- internals -----------------------------------------------------------

    def _cached(self, key: str, producer: Any) -> Any:
        def produce() -> Any:
            value = producer()
            return value

        return self._cache.get_or_set(key, produce)

    def _fetch_region(self, box: list[float]) -> pd.DataFrame:
        try:
            fetcher = call_with_retry(
                lambda: _create_fetcher(
                    self._settings.ARGO_SOURCE, self._settings.ARGO_DATASET
                ).region(box)
            )
            frame = fetcher.to_dataframe()
        except Exception as exc:  # noqa: BLE001
            raise ArgoClientError(f"Argo upstream request failed: {exc}") from exc
        if frame.empty:
            raise ArgoClientError("no Argo floats found for the requested region/time")
        return frame

    @staticmethod
    def _column(frame: pd.DataFrame, *candidates: str) -> str | None:
        lowered = {str(col).upper(): str(col) for col in list(frame.columns)}
        for candidate in candidates:
            if candidate.upper() in lowered:
                return lowered[candidate.upper()]
        return None

    # -- public API ----------------------------------------------------------

    def search_floats(
        self,
        *,
        lon_min: float = _DEFAULT_BOX[0],
        lon_max: float = _DEFAULT_BOX[1],
        lat_min: float = _DEFAULT_BOX[2],
        lat_max: float = _DEFAULT_BOX[3],
        start: str | None = None,
        end: str | None = None,
        max_floats: int = 50,
    ) -> list[ArgoFloatSummary]:
        """Search floats in a geographic box (optionally time-bounded)."""
        # argopy requires 6 elements (lon0 lon1 lat0 lat1 depth0 depth1),
        # optionally +2 time bounds -> 8.
        box: list[Any] = [lon_min, lon_max, lat_min, lat_max, 0, 2000]
        if start:
            end_value = pd.Timestamp(end) if end else pd.Timestamp.now("UTC").tz_localize(None)
            box.extend([pd.Timestamp(start), end_value])

        cache_key = f"search:{box}:{max_floats}"
        payload = self._cache.get(cache_key)
        if payload is None:

            def produce() -> list[dict[str, Any]]:
                frame = self._fetch_region(box)
                return self._summarise_frame(frame, max_floats)

            payload = self._cached(cache_key, produce)

        return [
            ArgoFloatSummary(
                platform_wmo=int(row["platform_wmo"]),
                cycles=int(row["cycles"]),
                last_location=(
                    (row["last_lon"], row["last_lat"])
                    if row.get("last_lon") is not None and row.get("last_lat") is not None
                    else None
                ),
                last_time=row.get("last_time"),
            )
            for row in payload
        ]

    def _summarise_frame(self, frame: pd.DataFrame, max_floats: int) -> list[dict[str, Any]]:
        wmo_col = self._column(frame, "PLATFORM_NUMBER", "WMO", "platform")
        cycle_col = self._column(frame, "CYCLE_NUMBER", "CYCLE")
        time_col = self._column(frame, "TIME", "JULD", "date")
        lat_col = self._column(frame, "LATITUDE", "LAT")
        lon_col = self._column(frame, "LONGITUDE", "LON")
        if wmo_col is None:
            raise ArgoClientError("Argo frame lacks PLATFORM_NUMBER column")

        work = frame.copy()
        work["_wmo"] = pd.to_numeric(work[wmo_col], errors="coerce").fillna(0).astype("int64")
        grouped = work.groupby("_wmo")
        summaries: list[dict[str, Any]] = []
        for wmo, group in grouped:
            if int(wmo) <= 0:
                continue
            last_row = group.iloc[-1]
            last_time = None
            if time_col is not None:
                parsed = pd.to_datetime(last_row[time_col], errors="coerce")
                last_time = parsed.isoformat() if pd.notna(parsed) else None
            last_lon = _clean(last_row[lon_col]) if lon_col else None
            last_lat = _clean(last_row[lat_col]) if lat_col else None
            if cycle_col is not None:
                cycles = int(pd.to_numeric(group[cycle_col], errors="coerce").nunique())
            else:
                cycles = int(len(group))
            summaries.append(
                {
                    "platform_wmo": int(wmo),
                    "cycles": cycles,
                    "last_lon": last_lon,
                    "last_lat": last_lat,
                    "last_time": last_time,
                }
            )
        summaries.sort(key=lambda item: item.get("last_time") or "", reverse=True)
        return summaries[:max_floats]

    def float_detail(self, wmo: int, *, max_profiles: int = 5) -> ArgoFloatDetail:
        """Fetch metadata + recent profiles for one float."""
        cache_key = f"float:{wmo}:{max_profiles}"
        payload = self._cache.get(cache_key)
        if payload is None:

            def produce() -> dict[str, Any]:
                try:
                    fetcher = call_with_retry(
                        lambda: _create_fetcher(
                            self._settings.ARGO_SOURCE, self._settings.ARGO_DATASET
                        ).float(wmo)
                    )
                    data = fetcher.data
                except Exception as exc:  # noqa: BLE001
                    raise ArgoClientError(f"Argo float {wmo} unavailable: {exc}") from exc
                return self._profiles_from_xarray(data, wmo, max_profiles)

            payload = self._cached(cache_key, produce)

        profiles = [ArgoProfile(**p) for p in payload["profiles"]]
        times = [p.time for p in profiles if p.time]
        lats = [p.latitude for p in profiles if p.latitude is not None]
        lons = [p.longitude for p in profiles if p.longitude is not None]
        return ArgoFloatDetail(
            platform_wmo=wmo,
            profiles_available=payload["profiles_available"],
            time_range=TimeRange(start=min(times), end=max(times), count=len(times))
            if times
            else None,
            spatial_bounds=SpatialBounds(
                west=min(lons), east=max(lons), south=min(lats), north=max(lats)
            )
            if lats and lons
            else None,
            recent_profiles=profiles,
        )

    def float_profile(self, wmo: int, cycle: int | None = None) -> ArgoProfile:
        """Retrieve one profile (latest when ``cycle`` omitted)."""
        detail = self.float_detail(wmo, max_profiles=10)
        if not detail.recent_profiles:
            raise ArgoClientError(f"no profiles available for float {wmo}")
        if cycle is None:
            return detail.recent_profiles[0]
        for profile in detail.recent_profiles:
            if profile.cycle_number == cycle:
                return profile
        raise ArgoClientError(f"cycle {cycle} not found for float {wmo}")

    def _profiles_from_xarray(self, data: Any, wmo: int, max_profiles: int) -> dict[str, Any]:
        """Normalise argopy xarray output into serialisable profile dicts."""
        try:
            frame = data.to_dataframe().reset_index()
        except Exception:  # noqa: BLE001
            frame = data.reset_index()  # already a dataset-like frame fallback

        prof_col = self._column(frame, "N_PROF", "CYCLE_NUMBER")
        pres_col = self._column(frame, "PRES", "PRESSURE")
        temp_col = self._column(frame, "TEMP", "TEMPERATURE")
        psal_col = self._column(frame, "PSAL", "SALINITY")
        time_col = self._column(frame, "TIME", "JULD")
        lat_col = self._column(frame, "LATITUDE", "LAT")
        lon_col = self._column(frame, "LONGITUDE", "LON")
        depth_col = self._column(frame, "DEPTH")

        profiles: list[dict[str, Any]] = []
        groups = frame.groupby(prof_col) if prof_col else [(0, frame)]
        total_cycles = frame[prof_col].nunique() if prof_col else 1

        for _, group in groups:
            if len(profiles) >= max_profiles:
                break
            points: list[ArgoProfilePoint] = []
            pressures = group[pres_col].astype(float) if pres_col else None
            order = (
                pressures.sort_values(na_position="last").index
                if pressures is not None
                else group.index
            )
            for idx in order:
                row = group.loc[idx]
                pressure = _clean(row[pres_col]) if pres_col else None
                temperature = _clean(row[temp_col]) if temp_col else None
                salinity = _clean(row[psal_col]) if psal_col else None
                if pressure is None and temperature is None and salinity is None:
                    continue
                depth_m = None
                if depth_col:
                    depth_m = _clean(row[depth_col])
                elif pressure is not None:
                    depth_m = pressure * 1.019716  # dbar -> m approximation
                points.append(
                    ArgoProfilePoint(
                        pressure_dbar=pressure,
                        depth_meters=depth_m,
                        temperature_c=temperature,
                        salinity_psu=salinity,
                    )
                )
            if not points:
                continue
            first = group.loc[group.index[0]]
            profile_time = None
            if time_col:
                parsed = pd.to_datetime(first[time_col], errors="coerce")
                profile_time = parsed.isoformat() if pd.notna(parsed) else None
            cycle_number = None
            cycle_col = self._column(frame, "CYCLE_NUMBER", "CYCLE")
            if cycle_col is not None:
                raw_cycle = np.asarray(first[cycle_col]).ravel()[0]
                cleaned_cycle = _clean(raw_cycle)
                cycle_number = int(cleaned_cycle) if cleaned_cycle is not None else None
            elif prof_col:
                raw_cycle = np.asarray(first[prof_col]).ravel()[0]
                cleaned_cycle = _clean(raw_cycle)
                cycle_number = int(cleaned_cycle) if cleaned_cycle is not None else None
            profiles.append(
                {
                    "platform_wmo": wmo,
                    "cycle_number": cycle_number,
                    "time": profile_time,
                    "latitude": _clean(first[lat_col]) if lat_col else None,
                    "longitude": _clean(first[lon_col]) if lon_col else None,
                    "points": [p.model_dump() for p in points[:500]],
                }
            )

        return {"profiles_available": int(total_cycles), "profiles": profiles}
