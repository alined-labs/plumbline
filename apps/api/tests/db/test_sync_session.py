"""tenant_session_sync: the blocking twin of tenant_session, for worker threads."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, Document, Tenant
from plumbline.db.session import tenant_session_sync

pytestmark = pytest.mark.db


@pytest.fixture
def sessions(database_url: str) -> Iterator[sessionmaker[Session]]:
    engine = make_sync_engine(database_url)
    yield make_sync_sessionmaker(engine)
    engine.dispose()


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


def test_a_blocking_session_sees_its_tenant_and_the_public_corpus_only(
    sessions: sessionmaker[Session],
) -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()
    with sessions() as owner, owner.begin():  # as the owner: the app adds no tenants
        owner.add_all([Tenant(id=t, slug=f"t-{t.hex}", name="Test") for t in (alice, bob)])
        owner.flush()  # the tenants first: nothing in the models tells the ORM the order
        owner.add_all([_document(t) for t in (PUBLIC_TENANT, alice, bob)])
    with tenant_session_sync(sessions, alice) as session:
        assert set(session.scalars(select(Document.tenant_id))) >= {alice, PUBLIC_TENANT}
        assert bob not in set(session.scalars(select(Document.tenant_id)))


def test_the_role_and_the_tenant_end_with_the_transaction(sessions: sessionmaker[Session]) -> None:
    with tenant_session_sync(sessions, PUBLIC_TENANT) as session:
        assert session.scalar(text("SELECT current_user")) == "plumbline_app"
    with sessions() as session:
        assert session.scalar(text("SELECT current_user")) != "plumbline_app"
        assert not session.scalar(text("SELECT current_setting('app.tenant_id', true)"))
