"""Database access (Lane D): one async SQLAlchemy engine over psycopg 3. Migrations live in
apps/api/migrations (Alembic) and use the same URL. Tenant data is reached only through
plumbline.db.session.tenant_session."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from plumbline.settings import get_settings


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or get_settings().database_url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
