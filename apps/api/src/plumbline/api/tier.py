"""The demo tier (Lane D): the degradation ladder's switch, full, free or static, kept in the
settings table so it flips without a redeploy (ADR-0002).

GET /api/settings/tier is public, for the model-and-tier badge; PUT /api/admin/settings/tier
takes the admin token. Each process reads the tier through a 10-second cache: a flip
reaches every worker within ten seconds, at one query per worker per ten seconds. Until
the table holds a value, the tier is the server's DEMO_TIER setting, and so it is while the
database cannot be read: a switch for degrading must not take the API down with it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.admin import require_admin
from plumbline.core.types import DemoTier
from plumbline.db.models import PUBLIC_TENANT, Setting
from plumbline.db.session import tenant_session

log = logging.getLogger(__name__)

TIER_KEY: Final = "demo_tier"
TTL_S: Final = 10.0


class TierState(BaseModel):
    tier: DemoTier
    updated_at: datetime | None  # None: never set, so the server's DEMO_TIER applies


class TierChange(BaseModel):
    tier: DemoTier


class TierStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        default: DemoTier,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessions = sessions
        self._default = default
        self._clock = clock
        self._cached: tuple[float, TierState] | None = None

    async def current(self) -> DemoTier:
        return (await self.state()).tier

    async def state(self) -> TierState:
        now = self._clock()
        if self._cached is not None and now - self._cached[0] < TTL_S:
            return self._cached[1]
        state = TierState(tier=self._default, updated_at=None)
        try:
            async with tenant_session(self._sessions, PUBLIC_TENANT) as session:
                row = await session.get(Setting, TIER_KEY)
            if row is not None:
                state = TierState(tier=DemoTier(row.value), updated_at=row.updated_at)
        except (SQLAlchemyError, OSError) as exc:
            log.warning("the tier cannot be read, so it is %s for now: %s", state.tier, exc)
        self._cached = (now, state)
        return state

    async def set(self, tier: DemoTier) -> TierState:
        async with tenant_session(self._sessions, PUBLIC_TENANT) as session:
            updated_at = await session.scalar(
                insert(Setting)
                .values(key=TIER_KEY, value=tier.value, updated_at=func.now())
                .on_conflict_do_update(
                    index_elements=[Setting.key],
                    set_={"value": tier.value, "updated_at": func.now()},
                )
                .returning(Setting.updated_at)
            )
        state = TierState(tier=tier, updated_at=updated_at)
        self._cached = (self._clock(), state)  # this process sees the flip at once
        return state


def tier_store(request: Request) -> TierStore:
    store: TierStore = request.app.state.tier
    return store


router = APIRouter(tags=["settings"])


Store = Annotated[TierStore, Depends(tier_store)]


@router.get("/api/settings/tier")
async def get_tier(store: Store) -> TierState:
    return await store.state()


@router.put("/api/admin/settings/tier", tags=["admin"], dependencies=[Depends(require_admin)])
async def put_tier(change: TierChange, store: Store) -> TierState:
    return await store.set(change.tier)
