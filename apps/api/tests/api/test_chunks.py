"""GET /api/chunks/{chunk_id}: the cited article as published, with the quote's span."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import chunks
from plumbline.api.app import create_app
from plumbline.api.chunks import Span, find_span
from plumbline.core.types import CacheMode
from plumbline.corpus.manifest import Source
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, ChunkRow, Document
from plumbline.db.session import tenant_session
from plumbline.settings import Settings

Sessions = async_sessionmaker[AsyncSession]
ARTICLE = (
    "Artículo 9. Plazo mínimo.\n1. La duración del arrendamiento será libremente pactada\n"
    "por las partes.\n2. Se entenderán celebrados por un año."
)


def test_a_span_ignores_case_and_line_breaks() -> None:
    span = find_span(ARTICLE, "libremente pactada por las PARTES")
    assert span is not None
    assert ARTICLE[span.start : span.end] == "libremente pactada\npor las partes"
    assert find_span(ARTICLE, "no está") is None
    assert find_span(ARTICLE, "  ") is None
    assert find_span("Straße", "STRASSE") == Span(start=0, end=6)  # casefold widens ß


@pytest.fixture
async def article(database_url: str) -> AsyncIterator[tuple[Sessions, str]]:
    """An article and one of its paragraphs, in two variants."""
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    key = uuid.uuid4().hex[:8]
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        session.add(
            Document(
                id=f"es-lau-{key}",
                tenant_id=PUBLIC_TENANT,
                law="es-lau",
                jurisdiction="spain",
                language="es",
                edition="boe-2026-10-13",
                sha256="0" * 64,
                parser="test",
                page_count=1,
            )
        )
        await session.flush()
        for variant in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
            common = {
                "variant": variant,
                "tenant_id": PUBLIC_TENANT,
                "document_id": f"es-lau-{key}",
                "jurisdiction": "spain",
                "law": "es-lau",
                "language": "es",
                "edition": "boe-2026-10-13",
                "article": "9",
                "label": "LAU art. 9",
                "status": "in_force",
            }
            session.add(
                ChunkRow(
                    id=f"a9-{key}",
                    text=ARTICLE,
                    text_for_search=ARTICLE,
                    heading="Plazo mínimo",
                    **common,
                )
            )
            await session.flush()
            paragraph = "1. La duración del arrendamiento será libremente pactada por las partes."
            session.add(
                ChunkRow(
                    id=f"a9-1-{key}",
                    parent_id=f"a9-{key}",
                    text=paragraph,
                    text_for_search=paragraph,
                    **common,
                )
            )
    yield sessions, key
    await engine.dispose()


@pytest.fixture
async def api(article: tuple[Sessions, str]) -> AsyncIterator[httpx.AsyncClient]:
    sessions, _ = article
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY)
    transport = httpx.ASGITransport(app=create_app(settings, sessions=sessions))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.db
@pytest.mark.anyio
async def test_a_paragraph_citation_opens_its_whole_article(
    api: httpx.AsyncClient, article: tuple[Sessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, key = article
    source = Source.model_validate(
        {
            "id": f"es-lau-{key}",
            "law": "es-lau",
            "title": "Ley de Arrendamientos Urbanos",
            "jurisdiction": "spain",
            "language": "es",
            "url": "https://www.boe.es/buscar/act.php?id=BOE-A-1994-26003",
            "edition": "boe-2026-10-13",
            "retrieved_on": "2026-10-13",
            "sha256": "0" * 64,
            "format": "xml",
            "license_basis": "test",
            "committed": True,
            "path": "data/corpus/raw/es-lau.xml",
        }
    )
    monkeypatch.setattr(chunks, "_sources", lambda: {source.id: source})
    response = await api.get(f"/api/chunks/a9-1-{key}", params={"quote": "pactada por las partes"})
    body = response.json()
    assert body["article"]["text"] == ARTICLE
    assert body["article"]["ref"] == {
        "jurisdiction": "spain",
        "law": "es-lau",
        "article": "9",
        "paragraph": None,
        "edition": "boe-2026-10-13",
    }
    assert ARTICLE[body["span"]["start"] : body["span"]["end"]] == "pactada\npor las partes"
    assert body["source"]["title"] == "Ley de Arrendamientos Urbanos"


@pytest.mark.db
@pytest.mark.anyio
async def test_a_whole_article_citation_and_a_missing_quote(
    api: httpx.AsyncClient, article: tuple[Sessions, str]
) -> None:
    _, key = article
    body = (await api.get(f"/api/chunks/a9-{key}", params={"quote": "no está aquí"})).json()
    assert (body["article"]["label"], body["span"], body["source"]) == ("LAU art. 9", None, None)


@pytest.mark.db
@pytest.mark.anyio
async def test_an_unknown_chunk_is_404(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/chunks/nowhere")
    assert (response.status_code, response.headers["content-type"]) == (
        404,
        "application/problem+json",
    )
