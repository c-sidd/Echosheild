"""Glider API backed by the configured real-data provider."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import GliderMission, GliderMissionSummary, GliderNotConfigured

router = APIRouter(prefix="/glider", tags=["glider"])


@router.get("/status", summary="Glider ingestion status")
async def status(request: Request) -> dict[str, object]:
    service = request.app.state.glider_service
    client = getattr(service, "_client", None)
    return {
        "configured": service.configured,
        "provider": type(client).__name__ if service.configured else "null",
    }


@router.get(
    "/missions",
    response_model=list[GliderMissionSummary] | GliderNotConfigured,
    summary="List real glider missions",
)
async def missions(request: Request) -> list[GliderMissionSummary] | GliderNotConfigured:
    result = await request.app.state.glider_service.list_missions()
    return result


@router.get(
    "/missions/{mission_id}/profiles",
    response_model=GliderMission | GliderNotConfigured,
    summary="Get profiles for one real glider mission",
)
async def mission_profiles(
    mission_id: str, request: Request
) -> GliderMission | GliderNotConfigured:
    result = await request.app.state.glider_service.mission_profiles(mission_id)
    return result


# Stable collection aliases used by the frontend/provider adapters.
@router.get(
    "/gliders",
    response_model=list[GliderMissionSummary] | GliderNotConfigured,
    include_in_schema=False,
)
async def list_gliders(request: Request) -> list[GliderMissionSummary] | GliderNotConfigured:
    return await missions(request)


@router.get(
    "/gliders/{glider_id}",
    response_model=GliderMission | GliderNotConfigured,
    include_in_schema=False,
)
async def get_glider(glider_id: str, request: Request) -> GliderMission | GliderNotConfigured:
    return await mission_profiles(glider_id, request)
