"""What the tools return: Plumbline's public API payloads, mirrored so the package depends on
nothing but the protocol and HTTP. tests/test_models.py holds every model to the API's own
schema (packages/ts-client/openapi.json), so a change there fails here first. Unknown fields
are ignored: a newer API may add some."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Jurisdiction = Literal["dubai", "spain", "colombia", "florida"]
Language = Literal["en", "es"]


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class ArticleRef(Model):
    jurisdiction: Jurisdiction
    law: str
    article: str
    paragraph: str | None = None
    edition: str


class SourceLink(Model):
    id: str
    title: str
    url: str


class LawHit(Model):
    rank: int
    chunk_id: str = Field(description="Pass it to get_article for the whole article.")
    ref: ArticleRef
    label: str = Field(description="How to cite it, e.g. 'Fla. Stat. § 83.49(3)'.")
    heading: str | None
    text: str = Field(description="The provision's text; empty when the source is restricted.")
    language: Language
    status: str
    effective_from: date | None
    effective_to: date | None
    source: SourceLink | None
    restricted: bool = Field(
        description="The source's terms allow showing no more than a quoted passage."
    )


class LawSearch(Model):
    query: str
    jurisdiction: Jurisdiction | None
    as_of: date | None
    config_name: str
    hits: list[LawHit]


class Span(Model):
    start: int
    end: int


class PublishedArticle(Model):
    ref: ArticleRef
    label: str
    heading: str | None
    text: str
    language: Language
    page: int | None
    status: str
    validity_note: str | None
    effective_from: date | None
    effective_to: date | None


class ChunkArticle(Model):
    chunk_id: str
    article: PublishedArticle
    span: Span | None = Field(description="Where the quote sits in article.text, if found.")
    source: SourceLink | None
    restricted: bool = Field(description="True: article.text is only the quoted passage.")


class Citation(Model):
    n: int
    chunk_id: str
    ref: ArticleRef
    label: str
    quote: str
    gloss: str | None = None
    language: Language
    verified: bool
    page: int | None = None


class Finding(Model):
    n: int
    clause_number: str
    clause_text: str
    clause_language: Language
    severity: Literal["conflict", "check", "note", "match"]
    title: str
    why: str
    citations: list[Citation]
    confidence: float


class ClauseResult(Model):
    jurisdiction: Jurisdiction
    as_of: date | None
    finding: Finding | None = Field(description="None: the law found does not address the clause.")
    disclaimer: str
