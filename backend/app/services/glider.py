"""Glider ingestion architecture.

EchoShield must support future glider sources without coupling the backend to
a single provider. A concrete ``GliderClient`` can be registered later (ERDDAP
tabledap, THREDDS-hosted NetCDF, vendor APIs...). When no source is
configured, :class:`NullGliderClient` returns an explicit *not configured*
response — real glider data is never fabricated.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.core.config import Settings
from app.models.schemas import GliderNotConfigured

_LOG = logging.getLogger("echoshield.glider")


class GliderClient(Protocol):
    """Contract every glider provider client must satisfy."""

    @property
    def configured(self) -> bool:
        """Whether a real data source is available."""
        ...

    async def search_missions(self, **filters: Any) -> Any:
        """List missions/floats matching filters."""
        ...

    async def get_profiles(self, mission_id: str) -> Any:
        """Fetch profiles for one mission."""
        ...


class NullGliderClient:
    """Default client used when no glider source is configured."""

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
            "No glider data source is configured. Set GLIDER_DATA_URL"
            " and register a GliderClient implementation to enable this API."
        )
    )


class GliderService:
    """Provider-agnostic facade over the configured :class:`GliderClient`."""

    def __init__(self, settings: Settings, client: GliderClient | None = None) -> None:
        self._settings = settings
        self._client: GliderClient = client if client is not None else self._default_client()

    @staticmethod
    def _default_client() -> GliderClient:
        # Future: choose ERDDAP/THREDDS/vendor clients based on settings.
        return NullGliderClient()

    @property
    def configured(self) -> bool:
        return self._client.configured

    async def list_missions(self, **filters: Any) -> Any:
        return await self._client.search_missions(**filters)

    async def mission_profiles(self, mission_id: str) -> Any:
        return await self._client.get_profiles(mission_id)
