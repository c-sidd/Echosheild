"""Provider-agnostic glider service."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.core.config import Settings
from app.ingestion.glider_netcdf import NetCDFGliderClient
from app.models.schemas import GliderNotConfigured

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
    return GliderNotConfigured(detail="No glider data source is configured. Set GLIDER_DATA_URL to an authorized NetCDF/OPeNDAP source.")


class GliderService:
    """Facade that selects the configured real glider provider."""

    def __init__(self, settings: Settings, client: GliderClient | None = None) -> None:
        self._settings = settings
        self._client: GliderClient = client if client is not None else self._default_client(settings)

    @staticmethod
    def _default_client(settings: Settings) -> GliderClient:
        source = getattr(settings, "GLIDER_DATA_URL", "") or ""
        if source:
            try:
                return NetCDFGliderClient(source)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("glider_client_init_failed error=%r", exc)
        return NullGliderClient()

    @property
    def configured(self) -> bool:
        return self._client.configured

    async def list_missions(self, **filters: Any) -> Any:
        return await self._client.search_missions(**filters)

    async def mission_profiles(self, mission_id: str) -> Any:
        return await self._client.get_profiles(mission_id)
