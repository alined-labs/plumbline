"""The health route (Lane D): the version, the demo tier and the cache mode, for the
tunnel's and the deploy's checks."""

from __future__ import annotations

from importlib.metadata import version

from fastapi import APIRouter, Request

from plumbline.api.schemas import Health
from plumbline.api.tier import tier_store
from plumbline.settings import Settings

router = APIRouter(prefix="/api", tags=["ops"])


@router.get("/health")
async def health(request: Request) -> Health:
    settings: Settings = request.app.state.settings
    tier = await tier_store(request).current()
    return Health(version=version("plumbline"), tier=tier, cache_mode=settings.cache_mode)
