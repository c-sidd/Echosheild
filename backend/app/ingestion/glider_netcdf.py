"""Generic NetCDF glider provider for an authorized GLIDER_DATA_URL."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from app.ingestion.variable_mapping import classify_variable, resolve_coordinates


class NetCDFGliderClient:
    """Provider for a real glider NetCDF file or OPeNDAP URL.

    The exact mission schema differs between deployments, so this adapter uses
    CF coordinates and common variable aliases instead of hard-coding a vendor
    format. It is intentionally read-only.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self._ds: xr.Dataset | None = None

    @property
    def configured(self) -> bool:
        return bool(self.source)

    def _open(self) -> xr.Dataset:
        if self._ds is not None:
            return self._ds
        engine = "pydap" if self.source.startswith(("http://", "https://")) else None
        self._ds = xr.open_dataset(self.source, engine=engine, decode_times=True)
        return self._ds

    def _variables(self, ds: xr.Dataset) -> dict[str, str]:
        found: dict[str, str] = {}
        for name, da in ds.data_vars.items():
            canonical = classify_variable(str(name), {str(k).lower(): str(v) for k, v in da.attrs.items() if isinstance(v, (str, int, float))})
            if canonical and canonical not in found:
                found[canonical] = str(name)
        return found

    async def search_missions(self, **filters: Any) -> list[dict[str, Any]]:
        ds = await asyncio.to_thread(self._open)
        coords = resolve_coordinates(ds)
        if not coords.latitude or not coords.longitude:
            return []
        lat = np.asarray(ds[coords.latitude].values).ravel().astype(float)
        lon = np.asarray(ds[coords.longitude].values).ravel().astype(float)
        valid = np.isfinite(lat) & np.isfinite(lon)
        if not valid.any():
            return []
        return [{
            "mission_id": str(ds.attrs.get("mission_id") or ds.attrs.get("platform") or Path(self.source).stem),
            "platform": str(ds.attrs.get("platform") or "glider"),
            "latitude": float(lat[valid][-1]),
            "longitude": float(lon[valid][-1]),
            "source": self.source,
        }]

    async def get_profiles(self, mission_id: str) -> dict[str, Any]:
        ds = await asyncio.to_thread(self._open)
        coords = resolve_coordinates(ds)
        variables = self._variables(ds)
        result = {"mission_id": mission_id, "source": self.source, "profiles": []}
        if not coords.latitude or not coords.longitude:
            return result
        for index in range(int(ds.sizes.get(coords.time, 1))) if coords.time else [0]:
            point: dict[str, Any] = {"time_index": index}
            if coords.time:
                point["time"] = str(ds[coords.time].values[index])
            for key, name in variables.items():
                if coords.time and coords.time in ds[name].dims:
                    value = np.asarray(ds[name].isel({coords.time: index}).values).ravel()
                else:
                    value = np.asarray(ds[name].values).ravel()
                finite = value[np.isfinite(value)] if value.size else value
                point[key] = float(finite[-1]) if finite.size else None
            result["profiles"].append(point)
        return result
