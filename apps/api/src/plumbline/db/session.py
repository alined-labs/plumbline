"""The only way the application reaches tenant data: a transaction that runs as the role
plumbline_app with app.tenant_id set, so the row-level security policies of migration 0002
apply to every statement in it. Both settings are transaction-local and vanish at commit or
rollback, so a pooled connection never carries a tenant into the next request."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

APP_ROLE = "plumbline_app"


@asynccontextmanager
async def tenant_session(
    sessions: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """A session inside one transaction acting for `tenant_id`; commits on success."""
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        yield session
