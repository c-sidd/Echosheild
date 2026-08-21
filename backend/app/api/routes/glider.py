"""Glider API (explicitly reports *not configured* until a source exists)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import GliderNotConfigured

router = APIRouter(prefix="/glider", tags=["glider"])


@router.get(
    "/status",
    summary="Glider ingestion status",
    description="Whether a glider data source is configured for this deployment.",
)
async def status(request: Request) -> dict[str, object]:
    service = request.app.state.glider_service
    return {
        "configured": service.configured,
        "provider": "null" if not service.configured else type(service._client).__name__,
    }


@router.get(
    "/missions",
    response_model=GliderNotConfigured,
    summary="List glider missions",
    description=(
        "Returns an explicit *not configured* response until a real glider"
        " source is registered; glider data is never fabricated."
    ),
)
async def missions(request: Request) -> GliderNotConfigured:
    result = await request.app.state.glider_service.list_missions()
    if isinstance(result, GliderNotConfigured):
        return result
    return GliderNotConfigured(detail=str(result))


@router.get(
    "/missions/{mission_id}/profiles",
    response_model=GliderNotConfigured,
    summary="Profiles for one mission",
    responses={200: {"description": "Not configured (or profiles once a source exists)"}},
)
async def mission_profiles(mission_id: str, request: Request) -> GliderNotConfigured:
    result = await request.app.state.glider_service.mission_profiles(mission_id)
    if isinstance(result, GliderNotConfigured):
        return result
    return GliderNotConfigured(detail=str(result))
