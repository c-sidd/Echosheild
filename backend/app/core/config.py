"""Application configuration.

All environment-specific values flow through :class:`Settings` so that no
infrastructure URL is ever hardcoded in application code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """EchoShield backend settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    APP_NAME: str = "echoshield-backend"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS --------------------------------------------------------------
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept comma-separated strings or JSON arrays for CORS_ORIGINS."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                try:
                    parsed = json.loads(text)
                    return [str(item).strip() for item in parsed]
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    # --- THREDDS / scientific services -------------------------------------
    THREDDS_BASE_URL: str | None = None
    THREDDS_CATALOG_URL: str | None = None
    OPENDAP_BASE_URL: str | None = None
    WMS_BASE_URL: str | None = None
    WCS_BASE_URL: str | None = None
    INCOIS_ERDDAP_URL: str | None = "https://erddap.incois.gov.in/erddap"

    # --- Argo ingestion ----------------------------------------------------
    ARGO_SOURCE: Literal["erddap", "gdac"] = "erddap"
    ARGO_DATASET: str = "phy"
    # Provider selection: "auto" prefers local .nc files in ARGO_CACHE_DIR.
    # Without local files, "auto" stays offline via NullArgoClient.
    # Set ARGO_PROVIDER=remote explicitly to enable live argopy fetching.
    ARGO_PROVIDER: Literal["auto", "local", "remote"] = "auto"
    # Timeout for argopy upstream HTTP requests (seconds).
    # Ifremer ERDDAP bulk-region queries for the Indian Ocean can exceed
    # argopy's default 60 s; 120 s is safe for production.
    ARGO_API_TIMEOUT: int = 120
    # Override the argopy ERDDAP / GDAC server (empty → argopy default).
    ARGO_ERDDAP_URL: str = ""
    ARGO_GDAC_URL: str = ""

    # --- Glider ingestion (future providers) --------------------------------
    GLIDER_DATA_URL: str | None = None

    # --- Data locations ----------------------------------------------------
    DATA_ROOT: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data")
    NETCDF_DATA_ROOT: Path | None = None
    ARGO_CACHE_DIR: Path | None = None
    GLIDER_CACHE_DIR: Path | None = None

    # --- Reliability / limits ----------------------------------------------
    REQUEST_TIMEOUT: float = 30.0
    MAX_DATA_POINTS: int = 200_000
    MAX_PROFILE_POINTS: int = 500
    MAX_GRID_POINTS: int = 100_000
    CACHE_TTL_SECONDS: int = 3600

    # --- Derived helpers ---------------------------------------------------
    @property
    def netcdf_data_root(self) -> Path:
        return self.NETCDF_DATA_ROOT or (self.DATA_ROOT / "sample_netcdf")

    @property
    def argo_cache_dir(self) -> Path:
        return self.ARGO_CACHE_DIR or (self.DATA_ROOT / "argo_cache")

    @property
    def glider_cache_dir(self) -> Path:
        return self.GLIDER_CACHE_DIR or (self.DATA_ROOT / "glider_cache")

    @property
    def metadata_root(self) -> Path:
        return self.DATA_ROOT

    @property
    def version(self) -> str:
        from app import __version__

        return __version__

    def resolve_data_path(self, relative: str) -> Path:
        """Resolve *relative* inside DATA_ROOT, refusing path traversal."""
        root = self.DATA_ROOT.resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"path escapes DATA_ROOT: {relative!r}")
        return candidate

    def ensure_directories(self) -> None:
        for directory in (
            self.DATA_ROOT,
            self.netcdf_data_root,
            self.argo_cache_dir,
            self.glider_cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    settings = Settings()
    settings.ensure_directories()
    return settings
