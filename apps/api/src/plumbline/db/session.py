"""The only way the application reaches tenant data: a transaction that runs as the role
plumbline_app with app.tenant_id set, so the row-level security policies of migration 0002
apply to every statement in it. Both settings are transaction-local and vanish at commit or
rollback, so a pooled connection never carries a tenant into the next request."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

APP_ROLE = "plumbline_app"
# Run first in every transaction the application opens, async or not.
SET_ROLE = f"SET LOCAL ROLE {APP_ROLE}"
SET_TENANT = "SELECT set_config('app.tenant_id', :tenant, true)"


@asynccontextmanager
async def tenant_session(
    sessions: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """A session inside one transaction acting for `tenant_id`; commits on success."""
    async with sessions() as session, session.begin():
        await session.execute(text(SET_ROLE))
        await session.execute(text(SET_TENANT), {"tenant": str(tenant_id)})
        yield session


@contextmanager
def tenant_session_sync(sessions: sessionmaker[Session], tenant_id: uuid.UUID) -> Iterator[Session]:
    """`tenant_session` for code that runs in a worker thread, such as the answer
    pipeline's search, which asyncio.to_thread calls: the same role and tenant, a blocking
    connection."""
    with sessions() as session, session.begin():
        session.execute(text(SET_ROLE))
        session.execute(text(SET_TENANT), {"tenant": str(tenant_id)})
        yield session
