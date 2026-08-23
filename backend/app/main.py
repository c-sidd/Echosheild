"""EchoShield FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import argo, glider, health, model_data
from app.api.routes.argo import UpstreamUnavailable as ArgoUpstreamUnavailable
from app.core.config import Settings, get_settings
from app.core.logging import add_request_logging_middleware, configure_logging
from app.ingestion.argo_client import (
    ArgoClientError,
    NullArgoClient,
    create_argo_client,
)
from app.ingestion.thredds_client import ThreddsClient, ThreddsClientError
from app.services.dataset_registry import DatasetRegistry
from app.services.glider import GliderService
from app.services.model_service import (
    DatasetNotAccessibleError,
    ModelDataService,
    UpstreamUnavailableError,
)

_LOG = logging.getLogger("echoshield")


@asynccontextmanager
async def _lifespan_for(app: FastAPI, settings: Settings) -> AsyncIterator[None]:
    settings.ensure_directories()

    registry = DatasetRegistry(settings, thredds_client=app.state.thredds_client)
    discovered = registry.discover()
    _LOG.info("startup datasets_registered=%d", discovered)

    app.state.settings = settings
    app.state.registry = registry
    app.state.model_service = ModelDataService(registry, settings)
    try:
        app.state.argo_client = create_argo_client(settings)
    except Exception as exc:  # noqa: BLE001 - Argo is optional; never block startup
        _LOG.warning(
            "argo_client_init_failed error=%r — /argo endpoints will answer 503", exc
        )
        app.state.argo_client = NullArgoClient()
    app.state.glider_service = GliderService(settings)
    app.state.registry.refresh_in_background()
    try:
        yield
    finally:
        app.state.model_service.close_all()
        if app.state.thredds_client is not None:
            await app.state.thredds_client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the configured EchoShield backend application."""
    resolved_settings = settings or get_settings()
    configure_logging()

    app = FastAPI(
        title="EchoShield Backend",
        version=__version__,
        summary="Application API for the EchoShield 3D ocean-data visualization platform.",
        description=(
            "Serves ocean model data (NetCDF via xarray), Argo observations"
            " (argopy) and THREDDS/ERDDAP service endpoints to the frontend."
            " Scientific data serving (OPeNDAP/WMS/WCS) is delegated to THREDDS."
        ),
        lifespan=lambda application: _lifespan_for(application, resolved_settings),
        docs_url="/docs",
        redoc_url="/redoc",
        separate_input_output_schemas=False,
    )
    app.state.thredds_client = ThreddsClient(resolved_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    add_request_logging_middleware(app)

    api_prefix = resolved_settings.API_V1_PREFIX
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(model_data.router, prefix=api_prefix)
    app.include_router(argo.router, prefix=api_prefix)
    app.include_router(glider.router, prefix=api_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": resolved_settings.APP_NAME,
            "version": __version__,
            "docs": "/docs",
        }

    # --- error translation --------------------------------------------------

    @app.exception_handler(KeyError)
    async def _not_found(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": str(exc.args[0] if exc.args else exc)}
        )

    @app.exception_handler(IndexError)
    async def _index_out_of_range(request: Request, exc: IndexError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _bad_request(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    for upstream_error in (
        UpstreamUnavailableError,
        ArgoClientError,
        ThreddsClientError,
        ArgoUpstreamUnavailable,
    ):

        @app.exception_handler(upstream_error)
        async def _upstream_unavailable(request: Request, exc: Exception) -> JSONResponse:
            message = getattr(exc, "args", [""])[0] or type(exc).__name__
            return JSONResponse(
                status_code=503, content={"detail": f"upstream unavailable: {message}"}
            )

    @app.exception_handler(DatasetNotAccessibleError)
    async def _metadata_only(request: Request, exc: DatasetNotAccessibleError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return app


app = create_app()
