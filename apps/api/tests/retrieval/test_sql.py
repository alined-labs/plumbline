"""The SQL retriever on a small index: the chunker's Florida, Spain and Dubai fixtures,
written by Lane D's index_document under A2's and A4's variants. A bag-of-words embedding
stands in for the model (each word hashed to a dimension), so the dense leg ranks by
shared words and every test runs offline and the same way twice."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from plumbline.chunking.chunker import chunk_document
from plumbline.core.config import EvalConfig, load_config
from plumbline.core.types import Chunk, Jurisdiction, Language, ParsedDocument, ProvisionStatus
from plumbline.db import make_engine, make_sessionmaker, make_sync_engine, make_sync_sessionmaker
from plumbline.db.models import EMBEDDING_DIM, Tenant
from plumbline.db.session import tenant_session_sync
from plumbline.ingest.index import index_document
from plumbline.ingest.plan import leaves
from plumbline.retrieval import sql
from plumbline.retrieval.fusion import rrf
from plumbline.retrieval.index import variant_key
from plumbline.retrieval.retriever import Retriever
from plumbline.settings import ROOT

pytestmark = pytest.mark.db
FIXTURES = ROOT / "apps" / "api" / "tests" / "chunking" / "fixtures"
LAWS = {"florida": "Fla. Stat. ch. 83", "spain": "LAU", "dubai": "Law No. 26 of 2007"}


def configuration(name: str) -> EvalConfig:
    """The configuration, with this file's bag-of-words embedding named as its model: its
    own variant, so the chunks other tests index under the real configurations stay out."""
    config = load_config(ROOT / "evals" / "configs" / f"{name}.yaml")
    retrieval = config.retrieval.model_copy(update={"embedding_model": "test/bag-of-words"})
    return config.model_copy(update={"retrieval": retrieval})


A2 = configuration("A2")
A4 = configuration("A4")  # deterministic headers
TODAY = date(2026, 10, 20)
# A tenant of its own, so the documents written here never meet other tests' rows.
TENANT = uuid.uuid4()


def embed(text: str) -> list[float]:
    """Each lower-cased word adds 1 to one of 1,024 dimensions; the vector has unit length."""
    vector = [0.0] * EMBEDDING_DIM
    for word in re.findall(r"\w+", text.lower()):
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
    vector[0] += 1e-3  # never the zero vector
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


class Embedder:
    def embed_query(self, question: str) -> list[float]:
        return embed(question)


@pytest.fixture(scope="module")
def sessions(database_url: str) -> Iterator[sessionmaker[Session]]:
    async def index() -> None:
        engine = make_engine(database_url)
        writer = make_sessionmaker(engine)
        async with writer() as session, session.begin():  # as the owner: the app adds no tenants
            session.add(Tenant(id=TENANT, slug=f"t-{TENANT.hex}", name="SQL retrieval test"))
        for name, law in LAWS.items():
            doc = ParsedDocument.model_validate_json((FIXTURES / f"{name}.json").read_text())
            doc = doc.model_copy(update={"source_id": f"{doc.source_id}-sql-test"})
            for config in (A2, A4):
                chunks = chunk_document(
                    doc, config.chunker, law_name=law, headers=config.retrieval.headers
                )
                searched = {c.id for c in leaves(chunks)}
                vectors = [embed(c.text_for_search) if c.id in searched else None for c in chunks]
                await index_document(
                    writer, doc, chunks, vectors, variant=variant_key(config), tenant_id=TENANT
                )
        versions = versioned()
        await index_document(
            writer,
            VERSIONED,
            versions,
            [embed(c.text) for c in versions],
            variant=variant_key(A2),
            tenant_id=TENANT,
        )
        await engine.dispose()

    asyncio.run(index())
    engine = make_sync_engine(database_url)
    yield make_sync_sessionmaker(engine)
    engine.dispose()


VERSIONED = ParsedDocument.model_validate_json((FIXTURES / "spain.json").read_text()).model_copy(
    update={"source_id": "es-versions-test", "law": "es-versions"}
)


def versioned() -> list[Chunk]:
    """An invented article in three versions, the way the chunker dates the BOE's: in force
    until a reform, then repealed for a while, then added back."""
    periods = [
        (date(1995, 1, 1), date(2001, 1, 8), ProvisionStatus.IN_FORCE, "plazo original"),
        (date(2001, 1, 8), date(2026, 10, 1), ProvisionStatus.REPEALED, "(Derogado)"),
        (date(2026, 10, 1), None, ProvisionStatus.IN_FORCE, "plazo reformado"),
    ]
    return [
        Chunk(
            id=f"es-versions-test:{n}",
            document_id="es-versions-test",
            jurisdiction=Jurisdiction.SPAIN,
            law="es-versions",
            language=Language.ES,
            edition="test",
            article="90",
            label="Invented, art. 90",
            text=f"Artículo noventa invented {words}",
            text_for_search=f"Artículo noventa invented {words}",
            effective_from=start,
            effective_to=end,
            status=status,
        )
        for n, (start, end, status, words) in enumerate(periods)
    ]


def retriever(
    sessions: sessionmaker[Session], config: EvalConfig = A2, **update: object
) -> Retriever:
    if update:
        retrieval = config.retrieval.model_copy(update=update)
        config = config.model_copy(update={"retrieval": retrieval})
    return Retriever(config, sessions, Embedder(), tenant_id=TENANT, today=lambda: TODAY)


def leg(
    sessions: sessionmaker[Session], mode: sql.Mode, question: str, **filters: object
) -> list[sql.SqlHit]:
    with tenant_session_sync(sessions, TENANT) as session:
        return sql.search(
            session,
            mode,
            sql.Filters(variant_key(A4), filters.pop("as_of", TODAY), **filters),  # type: ignore[arg-type]
            vector=embed(question),
            query=question,
            spanish_query=None,
            candidates=10,
            rrf_k=60,
        )


@pytest.mark.parametrize(
    ("question", "jurisdiction", "label"),
    [
        ("83.49", Jurisdiction.FLORIDA, "Fla. Stat. § 83.49"),
        ("Artículo 9", Jurisdiction.SPAIN, "LAU, art. 9"),
        ("Article 25", Jurisdiction.DUBAI, "Law No. 26 of 2007, Art. 25"),
    ],
)
def test_statute_numbers_survive_tokenization_and_match(
    sessions: sessionmaker[Session], question: str, jurisdiction: Jurisdiction, label: str
) -> None:
    # The deterministic header names the article ("s. 83.49", "Artículo 9", "Article 25");
    # unicode_words keeps 83.49 whole, so 83.493 and 83.4 do not match it. Within its
    # jurisdiction: BM25's document frequencies are the whole index's, every variant and
    # every other test's rows included, so across jurisdictions a lone "9" can outscore
    # "artículo 9" depending on what else is indexed.
    hits = retriever(sessions, A4, mode="bm25").search(
        question, k=3, jurisdictions=[jurisdiction], as_of=None
    )
    assert hits
    assert hits[0].chunk.label == label  # the whole article, by the parent merge


def test_hybrid_is_rrf_of_its_two_legs_in_one_statement(sessions: sessionmaker[Session]) -> None:
    question = "security deposit returned to the tenant"
    dense, bm25 = leg(sessions, "dense", question), leg(sessions, "bm25", question)
    fused = leg(sessions, "hybrid", question)
    expected = rrf([[h.id for h in dense], [h.id for h in bm25]], k=60)
    assert [(h.id, h.rrf) for h in fused] == [(f.id, f.score) for f in expected]
    assert {h.id for h in fused} == {h.id for h in dense} | {h.id for h in bm25}


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(1999, 6, 1), ["plazo original"]),
        (date(2010, 1, 1), []),  # repealed: nothing answers
        (date(2026, 10, 1), ["plazo reformado"]),
        (None, ["plazo reformado"]),  # no date: the law as it stands today
    ],
)
def test_the_as_of_filter_serves_only_the_version_in_force(
    sessions: sessionmaker[Session], day: date | None, expected: list[str]
) -> None:
    hits = retriever(sessions, mode="bm25").search(
        "noventa invented plazo", k=8, jurisdictions=[Jurisdiction.SPAIN], as_of=day
    )
    found = [h.chunk.text.removeprefix("Artículo noventa invented ") for h in hits]
    assert [t for t in found if t.startswith(("plazo", "("))] == expected


def test_jurisdiction_and_language_filters_run_inside_the_query(
    sessions: sessionmaker[Session],
) -> None:
    # Every leg keeps its full quota after the filter: the filter is not applied after
    # the best ten across all jurisdictions were cut.
    spanish = leg(sessions, "bm25", "83.49 deposit 9", jurisdictions=[Jurisdiction.SPAIN])
    assert spanish
    english = leg(sessions, "hybrid", "rent deposit", languages=[Language.EN])
    assert len(english) >= 10
    assert {c.language for c in chunks(sessions, english)} == {Language.EN}
    assert {c.jurisdiction for c in chunks(sessions, spanish)} == {Jurisdiction.SPAIN}


def chunks(sessions: sessionmaker[Session], hits: list[sql.SqlHit]) -> list[Chunk]:
    with tenant_session_sync(sessions, TENANT) as session:
        return list(
            Retriever(A4, sessions, Embedder(), tenant_id=TENANT)
            ._load(session, [h.id for h in hits])
            .values()
        )


def test_the_parent_merge_hands_back_whole_articles(sessions: sessionmaker[Session]) -> None:
    hits = retriever(sessions).search(
        "landlord deposit money advance rent", k=3, jurisdictions=[Jurisdiction.FLORIDA], as_of=None
    )
    assert [h.rank for h in hits] == [1, 2, 3]
    assert all(h.chunk.parent_id is None for h in hits)
    assert len({h.chunk.article for h in hits}) == 3
    assert hits[0].chunk.article == "83.49"
    assert hits[0].scores.rrf == hits[0].score  # its best paragraph's fused score


def test_without_the_merge_paragraphs_come_back_as_they_ranked(
    sessions: sessionmaker[Session],
) -> None:
    config = A2.model_copy(
        update={"chunker": A2.chunker.model_copy(update={"merge_parent": False})}
    )
    hits = Retriever(config, sessions, Embedder(), tenant_id=TENANT, today=lambda: TODAY).search(
        "landlord deposit money advance rent", k=5, jurisdictions=None, as_of=None
    )
    assert len(hits) == 5
    assert any(h.chunk.parent_id is not None for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_a_configuration_that_retrieves_nothing_is_refused(
    sessions: sessionmaker[Session],
) -> None:
    lc = load_config(Path(ROOT / "evals" / "configs" / "LC.yaml"))
    with pytest.raises(ValueError, match="LawSource"):
        Retriever(lc, sessions, Embedder())
    with pytest.raises(ValueError, match="embedder"):
        Retriever(A2, sessions, None)
