"""The SQLAlchemy models match migration 0002, and tenant_session is how they are used."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plumbline.db import make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, Base, Document, Tenant
from plumbline.db.session import tenant_session

pytestmark = pytest.mark.db


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # One pooled connection, so consecutive sessions reuse it.
    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    yield make_sessionmaker(engine)
    await engine.dispose()


def _document(tenant: uuid.UUID) -> Document:
    return Document(
        id=f"doc-{uuid.uuid4().hex}",
        tenant_id=tenant,
        law="fl-stat-83",
        jurisdiction="florida",
        language="en",
        edition="2026",
        sha256="0" * 64,
        parser="test",
        page_count=1,
    )


def test_the_models_match_the_migrated_database(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    tables = set(Base.metadata.tables)
    # Tables the models do not describe (alembic_version, and PostGIS's spatial_ref_sys in
    # the ParadeDB image) show up as removals; anything else is a real difference.
    assert [d for d in diff if not (d[0] == "remove_table" and d[1].name not in tables)] == []


@pytest.mark.anyio
async def test_a_tenant_session_reads_its_own_rows_and_the_public_corpus(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()
    async with sessions() as session, session.begin():  # as the owner: tenants are not the app's
        session.add_all([Tenant(id=t, slug=f"t-{t.hex}", name="Test") for t in (alice, bob)])
        session.add(_document(PUBLIC_TENANT))
    for tenant in (alice, bob):
        async with tenant_session(sessions, tenant) as session:
            session.add(_document(tenant))
    async with tenant_session(sessions, alice) as session:
        seen = set(await session.scalars(select(Document.tenant_id)))
    assert seen == {alice, PUBLIC_TENANT}


@pytest.mark.anyio
async def test_the_role_and_the_tenant_end_with_the_transaction(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        assert await session.scalar(text("SELECT current_user")) == "plumbline_app"
    async with sessions() as session:  # a new transaction, on a pooled connection
        assert await session.scalar(text("SELECT current_user")) != "plumbline_app"
        assert not await session.scalar(text("SELECT current_setting('app.tenant_id', true)"))
