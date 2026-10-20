"""The BM25 index of migration 0004, queried the way Lane A's retrieval does: one field per
language, a variant filter, and statute numbers kept whole."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import anyio
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, ChunkRow, Document
from plumbline.db.session import tenant_session
from plumbline.settings import ROOT

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]
# The field's expression must be the indexed one, literal for literal, and an alias is a
# type modifier, never a parameter: so one fixed query per language.
SEARCH = {
    language: text(
        "SELECT id FROM chunks"  # noqa: S608 (the language comes from the constant tuple below)
        f" WHERE (CASE WHEN language = '{language}' THEN text_for_search END)"
        f"::pdb.alias('search_{language}') ||| :query AND variant = :variant"
        " ORDER BY pdb.score(key) DESC, id"
    )
    for language in ("en", "es")
}


@pytest.fixture
async def variants(database_url: str) -> AsyncIterator[tuple[Sessions, str, str]]:
    """Two variants of a tiny corpus: two Florida sections and one Spanish article."""
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    one, two = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    rows = [
        ("fl", "florida", "en", "83.49", "s. 83.49 Deposit money or advance rent."),
        ("fl", "florida", "en", "83.493", "s. 83.493 Late fees for rent paid late."),
        ("es", "spain", "es", "9", "Artículo 9. La duración del arrendamiento será libre."),
    ]
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        for prefix in ("fl", "es"):
            session.add(
                Document(
                    id=f"{prefix}-{one}",
                    tenant_id=PUBLIC_TENANT,
                    law=f"{prefix}-law",
                    jurisdiction="florida" if prefix == "fl" else "spain",
                    language="en" if prefix == "fl" else "es",
                    edition="2026",
                    sha256="0" * 64,
                    parser="test",
                    page_count=1,
                )
            )
        await session.flush()
        for variant in (one, two):
            for prefix, jurisdiction, language, article, body in rows:
                session.add(
                    ChunkRow(
                        variant=variant,
                        id=f"{prefix}:{article}",
                        tenant_id=PUBLIC_TENANT,
                        document_id=f"{prefix}-{one}",
                        jurisdiction=jurisdiction,
                        law=f"{prefix}-law",
                        language=language,
                        edition="2026",
                        article=article,
                        label=article,
                        text=body,
                        text_for_search=body,
                    )
                )
    yield sessions, one, two
    await engine.dispose()


async def _search(sessions: Sessions, language: str, query: str, variant: str) -> list[str]:
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        rows = await session.scalars(SEARCH[language], {"query": query, "variant": variant})
        return list(rows)


async def test_a_statute_number_is_one_token(variants: tuple[Sessions, str, str]) -> None:
    sessions, one, _ = variants
    assert await _search(sessions, "en", "83.49", one) == ["fl:83.49"]


async def test_spanish_is_stemmed_and_folded_in_its_own_field(
    variants: tuple[Sessions, str, str],
) -> None:
    sessions, one, _ = variants
    assert await _search(sessions, "es", "articulos arrendamientos", one) == ["es:9"]
    assert await _search(sessions, "en", "arrendamiento", one) == []  # not an English row


async def test_each_variant_is_searched_alone(variants: tuple[Sessions, str, str]) -> None:
    sessions, one, two = variants
    assert await _search(sessions, "en", "rent", one) == ["fl:83.49", "fl:83.493"]
    assert await _search(sessions, "en", "rent", two) == ["fl:83.49", "fl:83.493"]
    assert await _search(sessions, "en", "rent", uuid.uuid4().hex[:12]) == []


async def test_the_migrations_reverse_with_chunks_in_several_variants(
    variants: tuple[Sessions, str, str], database_url: str
) -> None:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    await anyio.to_thread.run_sync(command.downgrade, config, "0003")
    await anyio.to_thread.run_sync(command.upgrade, config, "head")
