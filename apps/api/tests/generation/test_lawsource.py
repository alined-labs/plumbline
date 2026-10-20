"""The whole law from the index for the long-context baseline: article chunks of one
variant and the jurisdictions asked for, in force on the date, in the law's order."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from plumbline.core.types import Jurisdiction
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, ChunkRow, Document
from plumbline.generation.lawsource import SqlLawSource, article_key
from plumbline.generation.pipeline import LawSource

VARIANT = "5b405538b487"


def test_articles_sort_as_their_laws_number_them() -> None:
    articles = ["83.43", "10", "83.425", "9 bis", "83.42", "9", "83.5", "83.49"]
    assert sorted(articles, key=article_key) == [
        "9", "9 bis", "10", "83.42", "83.425", "83.43", "83.49", "83.5",
    ]  # fmt: skip
    guide = ["Decree 43/2013 art. 10", "Decree 43/2013 art. 2"]
    assert sorted(guide, key=article_key) == guide[::-1]


@pytest.fixture
def sessions(database_url: str) -> Iterator[sessionmaker[Session]]:
    engine = make_sync_engine(database_url)
    yield make_sync_sessionmaker(engine)
    engine.dispose()


def _document(source_id: str, law: str, jurisdiction: str, language: str) -> Document:
    return Document(
        id=source_id,
        tenant_id=PUBLIC_TENANT,
        law=law,
        jurisdiction=jurisdiction,
        language=language,
        edition="test",
        sha256="0" * 64,
        parser="test",
        page_count=1,
    )


def _chunk(
    document: Document,
    article: str,
    *,
    suffix: str = "",
    variant: str = VARIANT,
    parent: str | None = None,
    start: date | None = None,
    end: date | None = None,
    status: str = "in_force",
) -> ChunkRow:
    chunk_id = f"{document.id}:{article}{suffix}"
    return ChunkRow(
        variant=variant,
        id=chunk_id,
        tenant_id=PUBLIC_TENANT,
        document_id=document.id,
        parent_id=parent,
        jurisdiction=document.jurisdiction,
        law=document.law,
        language=document.language,
        edition="test",
        article=article,
        label=f"{document.law} {article}",
        text=f"Text of {article}{suffix}.",
        text_for_search=f"Text of {article}{suffix}.",
        effective_from=start,
        effective_to=end,
        status=status,
    )


@pytest.mark.db
def test_the_law_source_reads_one_variant_in_force_in_order(
    sessions: sessionmaker[Session],
) -> None:
    florida = _document("lawsource-fl", "fl-stat-83", "florida", "en")
    spain = _document("lawsource-es", "es-lau", "spain", "es")
    rows = [
        _chunk(florida, "83.49"),
        _chunk(florida, "83.425"),
        _chunk(florida, "83.42"),
        _chunk(florida, "83.49", suffix="(3)", parent="lawsource-fl:83.49"),  # a paragraph
        _chunk(florida, "83.40", variant="1cf9eaa7d607"),  # another chunk set
        _chunk(florida, "83.41", status="repealed"),
        _chunk(spain, "18", suffix="@2019", start=date(2019, 3, 6), end=date(2026, 10, 1)),
        _chunk(spain, "18", suffix="@2026", start=date(2026, 10, 1)),
        _chunk(spain, "9"),
    ]
    with sessions() as owner, owner.begin():
        owner.add_all([florida, spain])
        owner.flush()
        owner.add_all([r for r in rows if r.parent_id is None])
        owner.flush()  # the article before the paragraph that points at it
        owner.add_all([r for r in rows if r.parent_id is not None])
    law: LawSource = SqlLawSource(sessions, VARIANT)  # mypy checks it is the pipeline's

    florida_only = law.articles([Jurisdiction.FLORIDA], None)
    assert [c.article for c in florida_only] == ["83.42", "83.425", "83.49"]
    assert all(c.parent_id is None for c in florida_only)

    march = law.articles([Jurisdiction.SPAIN], date(2026, 3, 1))
    assert [c.id for c in march] == ["lawsource-es:9", "lawsource-es:18@2019"]
    today = law.articles([Jurisdiction.SPAIN], None)
    assert [c.id for c in today] == ["lawsource-es:9", "lawsource-es:18@2026"]

    assert SqlLawSource(sessions, VARIANT).jurisdictions() == {
        Jurisdiction.FLORIDA,
        Jurisdiction.SPAIN,
    }
    assert SqlLawSource(sessions, "no-such-variant").jurisdictions() == frozenset()

    everything = law.articles(None, date(2026, 10, 20))
    assert [c.jurisdiction for c in everything] == [Jurisdiction.FLORIDA] * 3 + [
        Jurisdiction.SPAIN
    ] * 2
