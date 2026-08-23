"""Provider-neutral glider ingestion with an optional ERDDAP tabledap backend."""

from __future__ import annotations

import io
import logging
from typing import Any, Protocol

import httpx
import pandas as pd

from app.core.config import Settings
from app.models.schemas import (
    GliderMission,
    GliderMissionSummary,
    GliderNotConfigured,
    GliderProfilePoint,
)

_LOG = logging.getLogger("echoshield.glider")


class GliderClient(Protocol):
    @property
    def configured(self) -> bool: ...

    async def search_missions(self, **filters: Any) -> Any: ...

    async def get_profiles(self, mission_id: str) -> Any: ...


class NullGliderClient:
    @property
    def configured(self) -> bool:
        return False

    async def search_missions(self, **filters: Any) -> GliderNotConfigured:
        return _not_configured()

    async def get_profiles(self, mission_id: str) -> GliderNotConfigured:
        return _not_configured()


def _not_configured() -> GliderNotConfigured:
    return GliderNotConfigured(
        detail=(
            "No glider data source is configured. Set GLIDER_DATA_URL to a real "
            "ERDDAP tabledap CSV endpoint."
        )
    )


class ErddapGliderClient:
    """Read real glider observations from an ERDDAP tabledap CSV endpoint.

    The adapter accepts common CF/ERDDAP aliases instead of forcing one vendor
    schema. It never invents missing measurements; absent columns become null.
    """

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def _read(self, mission_id: str | None = None) -> pd.DataFrame:
        params = {}
        if mission_id:
            # Request only the mission rows when the source exposes a mission_id
            # column. If it does not, the server will return an explicit error.
            params["mission_id"] = mission_id
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(f"{self.url}.csv0", params=params)
            response.raise_for_status()
        return pd.read_csv(io.BytesIO(response.content))

    @staticmethod
    def _column(df: pd.DataFrame, *names: str) -> str | None:
        lowered = {str(c).strip().lower(): c for c in df.columns}
        for name in names:
            if name.lower() in lowered:
                return str(lowered[name.lower()])
        return None

    @classmethod
    def _mission_column(cls, df: pd.DataFrame) -> str | None:
        return cls._column(df, "mission_id", "mission", "deployment_id", "deployment", "glider_id", "platform")

    @classmethod
    def _point(cls, row: pd.Series) -> GliderProfilePoint:
        def value(*names: str) -> float | None:
            col = cls._column(pd.DataFrame([row]), *names)
            if not col:
                return None
            try:
                v = float(row[col])
                return v if pd.notna(v) else None
            except (TypeError, ValueError):
                return None

        def text(*names: str) -> str | None:
            col = cls._column(pd.DataFrame([row]), *names)
            if not col or pd.isna(row[col]):
                return None
            return str(row[col])

        return GliderProfilePoint(
            time=text("time", "timestamp", "datetime", "date"),
            latitude=value("latitude", "lat", "y"),
            longitude=value("longitude", "lon", "long", "x"),
            depth_meters=value("depth", "depth_m", "depth_meters", "z"),
            temperature_c=value("temperature", "temp", "temperature_c", "water_temperature"),
            salinity_psu=value("salinity", "sal", "salinity_psu", "psu"),
            chlorophyll=value("chlorophyll", "chlorophyll_a", "chl", "chla"),
        )

    async def search_missions(self, **filters: Any) -> list[GliderMissionSummary]:
        df = await self._read()
        mission_col = self._mission_column(df)
        if not mission_col:
            raise ValueError("configured glider dataset has no mission/glider identifier column")
        lat_col = self._column(df, "latitude", "lat", "y")
        lon_col = self._column(df, "longitude", "lon", "long", "x")
        time_col = self._column(df, "time", "timestamp", "datetime", "date")
        summaries: list[GliderMissionSummary] = []
        for mission_id, group in df.groupby(mission_col, dropna=True):
            last = group.iloc[-1]
            lat = float(last[lat_col]) if lat_col and pd.notna(last[lat_col]) else None
            lon = float(last[lon_col]) if lon_col and pd.notna(last[lon_col]) else None
            last_time = str(last[time_col]) if time_col and pd.notna(last[time_col]) else None
            summaries.append(GliderMissionSummary(
                mission_id=str(mission_id), latitude=lat, longitude=lon,
                last_time=last_time, profiles=len(group), source=self.url,
            ))
        return summaries

    async def get_profiles(self, mission_id: str) -> GliderMission:
        df = await self._read(mission_id)
        mission_col = self._mission_column(df)
        if not mission_col:
            raise ValueError("configured glider dataset has no mission/glider identifier column")
        matches = df[df[mission_col].astype(str) == mission_id]
        if matches.empty:
            raise KeyError(f"glider mission not found: {mission_id}")
        return GliderMission(
            mission_id=mission_id,
            source=self.url,
            points=[self._point(row) for _, row in matches.iterrows()],
        )


class GliderService:
    def __init__(self, settings: Settings, client: GliderClient | None = None) -> None:
        self._settings = settings
        self._client: GliderClient = client if client is not None else self._default_client()

    def _default_client(self) -> GliderClient:
        if self._settings.GLIDER_DATA_URL:
            return ErddapGliderClient(self._settings.GLIDER_DATA_URL, self._settings.REQUEST_TIMEOUT)
        return NullGliderClient()

    @property
    def configured(self) -> bool:
        return self._client.configured

    async def list_missions(self, **filters: Any) -> Any:
        return await self._client.search_missions(**filters)

    async def mission_profiles(self, mission_id: str) -> Any:
        return await self._client.get_profiles(mission_id)
