"""The cited article for the source panel (Lane D): GET /api/chunks/{chunk_id}?quote=...

A citation names a chunk, which may be one paragraph of an article; the panel shows the
whole article as published, with the cited span marked. The article is the chunk itself
when it is one, else its parent. Every variant of a chunk shares its text and its parent
(variants differ in text_for_search and vectors), so any row with the id will do.

The span is found ignoring case and whitespace, so a quote whose line breaks differ from
the article's is still found, and is given in characters of the article's own text.

A source whose terms forbid republishing it (api/restricted.py) is shown only as the quoted
passage: `text` is the passage, the heading and the editor's note are left out, `span` covers
the passage, and `restricted` says so, so the panel can say why there is no more.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.restricted import is_restricted
from plumbline.core.types import ArticleRef, Jurisdiction, Language, ProvisionStatus
from plumbline.corpus.manifest import Source, load_manifest
from plumbline.db.models import PUBLIC_TENANT, ChunkRow
from plumbline.db.session import tenant_session

router = APIRouter(prefix="/api/chunks", tags=["sources"])


class Span(BaseModel):
    start: int
    end: int  # exclusive


class SourceLink(BaseModel):
    id: str
    title: str
    url: str


class PublishedArticle(BaseModel):
    ref: ArticleRef
    label: str
    heading: str | None
    text: str
    language: Language
    page: int | None
    status: ProvisionStatus
    validity_note: str | None
    effective_from: date | None
    effective_to: date | None


class ChunkArticle(BaseModel):
    chunk_id: str
    article: PublishedArticle
    span: Span | None  # where the quote is in article.text; None when it is not there
    source: SourceLink | None  # None for a document outside the manifest
    restricted: bool  # True: article.text is only the quoted passage (the source's terms)


def find_span(text: str, quote: str) -> Span | None:
    """The first place `quote` appears in `text`, ignoring case and whitespace."""
    wanted = " ".join(quote.casefold().split())
    if not wanted:
        return None
    # The text, normalized, with the index each normalized character came from.
    normalized: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            if normalized and normalized[-1] != " ":
                normalized.append(" ")
                origin.append(index)
            continue
        folded = char.casefold()
        normalized.extend(folded)
        origin.extend([index] * len(folded))
    start = "".join(normalized).find(wanted)
    if start < 0:
        return None
    return Span(start=origin[start], end=origin[start + len(wanted) - 1] + 1)


@lru_cache(maxsize=1)
def _sources() -> dict[str, Source]:
    return load_manifest().by_id()


@router.get("/{chunk_id}")
async def chunk_article(
    request: Request,
    chunk_id: str,
    quote: Annotated[str | None, Query(max_length=2000)] = None,
) -> ChunkArticle:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        chunk = await session.scalar(select(ChunkRow).where(ChunkRow.id == chunk_id).limit(1))
        if chunk is None:
            raise HTTPException(status_code=404, detail="No such chunk.")
        article = chunk
        if chunk.parent_id is not None:
            parent = await session.get(ChunkRow, (chunk.variant, chunk.parent_id))
            article = parent or chunk
    source = _sources().get(article.document_id)
    restricted = is_restricted(source)
    text = article.text
    span = find_span(text, quote) if quote else None
    if restricted:
        text = text[span.start : span.end] if span else ""
        span = Span(start=0, end=len(text)) if span else None
    return ChunkArticle(
        chunk_id=chunk_id,
        article=PublishedArticle(
            ref=ArticleRef(
                jurisdiction=Jurisdiction(article.jurisdiction),
                law=article.law,
                article=article.article,
                edition=article.edition,
            ),
            label=article.label,
            heading=None if restricted else article.heading,
            text=text,
            language=Language(article.language),
            page=article.page,
            status=ProvisionStatus(article.status),
            validity_note=None if restricted else article.validity_note,
            effective_from=article.effective_from,
            effective_to=article.effective_to,
        ),
        span=span,
        source=SourceLink(id=source.id, title=source.title, url=str(source.url))
        if source
        else None,
        restricted=restricted,
    )
