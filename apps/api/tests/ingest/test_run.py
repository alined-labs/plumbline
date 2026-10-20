"""The index stage end to end, on Florida chapter 83 and a fake embedder (no model server):
chunks, vectors and jobs in Postgres; every section found by its exact article reference;
a second run that does nothing; a run that repairs a lost index; failures that retry."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.config import EvalConfig, load_configs
from plumbline.corpus.manifest import Source, load_manifest
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, ChunkRow, IngestionJob, IngestionJobEvent
from plumbline.db.session import tenant_session
from plumbline.ingest.plan import Unit, plan_units
from plumbline.ingest.processed import read_processed
from plumbline.ingest.run import EMBED_BATCH, Indexer, InputsChanged, run_units
from plumbline.jobs.queue import JobContext
from plumbline.settings import ROOT

from .fakes import FakeEmbedder

pytestmark = [pytest.mark.db, pytest.mark.anyio]
Sessions = async_sessionmaker[AsyncSession]
SOURCE_ID = "fl-stat-83-2026"
TWINS_ID = "fl-twins-test"
TWINS = """83.50 First section.—

(1) The same paragraph, word for word.

(2) A paragraph only the first section has.

History.—s. 1, ch. 1.

83.51 Second section.—

(1) The same paragraph, word for word.

(2) A paragraph only the second section has.

History.—s. 2, ch. 2.
"""
CONFIGS = load_configs(ROOT / "evals" / "configs")


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[Sessions]:
    owner = create_engine(database_url)
    with owner.begin() as connection:  # every test starts with nothing indexed
        for source_id in (SOURCE_ID, TWINS_ID):
            connection.execute(
                text("DELETE FROM chunks WHERE document_id = :id"), {"id": source_id}
            )
            connection.execute(
                text("DELETE FROM ingestion_jobs WHERE source_id = :id"), {"id": source_id}
            )
    owner.dispose()
    engine = make_engine(database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def source() -> Source:
    return load_manifest().by_id()[SOURCE_ID]


def _units(source: Source, *names: str) -> list[Unit]:
    document = read_processed(source)
    assert document is not None
    return plan_units([source], {source.id: document}, [CONFIGS[n] for n in names])


def _indexer(sessions: Sessions, source: Source, embedder: FakeEmbedder) -> Indexer:
    configs: dict[str, EvalConfig] = dict(CONFIGS)
    document = read_processed(source)
    assert document is not None
    return Indexer(
        sessions=sessions,
        sources={source.id: source},
        configs=configs,
        load_document=lambda _: document,
        embedder_for=lambda _source, _model: embedder,
    )


async def _held(sessions: Sessions, variant: str) -> tuple[int, int]:
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        row = (
            await session.execute(
                select(func.count(), func.count(ChunkRow.embedding)).where(
                    ChunkRow.variant == variant, ChunkRow.document_id == SOURCE_ID
                )
            )
        ).one()
    return int(row[0]), int(row[1])


async def _job_count(sessions: Sessions) -> int:
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.source_id == SOURCE_ID)
            )
            or 0
        )


async def test_each_variant_is_chunked_embedded_and_written(
    sessions: Sessions, source: Source
) -> None:
    units = _units(source, "A0", "A2")
    embedder = FakeEmbedder()
    outcomes = await run_units(sessions, units, _indexer(sessions, source, embedder), worker="t")
    assert [o.status for o in outcomes] == ["indexed", "indexed"]
    for unit in units:
        assert await _held(sessions, unit.variant) == (len(unit.chunks), len(unit.embedded))
    article = units[1]
    assert len(article.embedded) < len(article.chunks)  # parents carry no vector
    sent = [t for call in embedder.calls for t in call]
    assert len(sent) == len(set(sent))  # no text is embedded twice
    # One TEI request per call, and the most a crash can lose: 32 texts, not the constant.
    assert 1 < max(len(call) for call in embedder.calls) <= 32


async def test_identical_texts_are_embedded_once(sessions: Sessions, source: Source) -> None:
    # An unchanged paragraph repeats in every version of a Spanish article: one recording.
    document = read_processed(source)
    assert document is not None
    twins = document.model_copy(
        update={
            "source_id": TWINS_ID,
            "pages": [document.pages[0].model_copy(update={"markdown": TWINS})],
        }
    )
    twin_source = source.model_copy(update={"id": TWINS_ID})
    (unit,) = plan_units([twin_source], {TWINS_ID: twins}, [CONFIGS["A2"]])
    embedder = FakeEmbedder()
    indexer = Indexer(
        sessions=sessions,
        sources={TWINS_ID: twin_source},
        configs=dict(CONFIGS),
        load_document=lambda _: twins,
        embedder_for=lambda _source, _model: embedder,
    )
    (outcome,) = await run_units(sessions, [unit], indexer, worker="t")
    assert outcome.status == "indexed"
    sent = [t for call in embedder.calls for t in call]
    assert len(sent) == len(set(sent))
    assert len(unit.embedded) > len(sent)  # the twin paragraphs share one vector
    assert outcome.detail["unique_texts"] == len(sent)


async def test_every_section_is_found_by_its_exact_reference(
    sessions: Sessions, source: Source
) -> None:
    (unit,) = _units(source, "A2")
    await run_units(sessions, [unit], _indexer(sessions, source, FakeEmbedder()), worker="t")
    document = read_processed(source)
    assert document is not None
    sections = set(re.findall(r"^(\d+\.\d+) ", document.markdown, re.MULTILINE))
    assert len(sections) >= 40  # all of chapter 83, part II
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        for number in sorted(sections):
            found = await session.scalar(
                select(func.count()).where(
                    ChunkRow.variant == unit.variant,
                    ChunkRow.jurisdiction == "florida",
                    ChunkRow.law == "fl-stat-83",
                    ChunkRow.article == number,
                    ChunkRow.edition == "2026",
                    ChunkRow.parent_id.is_(None),
                )
            )
            assert found == 1, f"s. {number} is not in the index once"


async def test_a_second_run_does_nothing(sessions: Sessions, source: Source) -> None:
    units = _units(source, "A2")
    await run_units(sessions, units, _indexer(sessions, source, FakeEmbedder()), worker="t")
    jobs = await _job_count(sessions)
    again = FakeEmbedder()
    outcomes = await run_units(sessions, units, _indexer(sessions, source, again), worker="t")
    assert [o.status for o in outcomes] == ["current"]
    assert again.calls == []
    assert await _job_count(sessions) == jobs


async def test_a_lost_index_is_rebuilt_by_the_job_that_wrote_it(
    sessions: Sessions, source: Source
) -> None:
    (unit,) = _units(source, "A2")
    await run_units(sessions, [unit], _indexer(sessions, source, FakeEmbedder()), worker="t")
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        await session.execute(text("DELETE FROM chunks WHERE variant = :v"), {"v": unit.variant})
    assert await _held(sessions, unit.variant) == (0, 0)
    outcomes = await run_units(
        sessions, [unit], _indexer(sessions, source, FakeEmbedder()), worker="t"
    )
    assert [o.status for o in outcomes] == ["indexed"]
    assert await _held(sessions, unit.variant) == (len(unit.chunks), len(unit.embedded))
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        kinds = list(
            await session.scalars(
                select(IngestionJobEvent.kind)
                .order_by(IngestionJobEvent.id)
                .where(
                    IngestionJobEvent.job_id
                    == select(IngestionJob.id)
                    .where(IngestionJob.source_id == SOURCE_ID)
                    .scalar_subquery()
                )
            )
        )
    assert "requeued" in kinds
    assert await _job_count(sessions) == 1  # the same job, run again


async def test_a_failed_job_is_retried_by_the_next_run(sessions: Sessions, source: Source) -> None:
    units = _units(source, "A2")
    (failed,) = await run_units(
        sessions, units, _indexer(sessions, source, FakeEmbedder(fail=True)), worker="t"
    )
    assert failed.status == "failed"
    assert "ConnectionError: the embedding server is down" in str(failed.detail["error"])
    assert await _held(sessions, units[0].variant) == (0, 0)  # nothing half-written
    (retried,) = await run_units(
        sessions, units, _indexer(sessions, source, FakeEmbedder()), worker="t"
    )
    assert retried.status == "indexed"
    assert await _job_count(sessions) == 1


async def test_progress_is_reported_a_batch_at_a_time(sessions: Sessions, source: Source) -> None:
    (unit,) = _units(source, "A2")
    await run_units(sessions, [unit], _indexer(sessions, source, FakeEmbedder()), worker="t")
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        messages = list(
            await session.scalars(
                select(IngestionJobEvent.message)
                .where(IngestionJobEvent.kind == "progress")
                .order_by(IngestionJobEvent.id)
            )
        )
    mine = [m for m in messages if re.fullmatch(r"embedded \d+ of \d+ texts", m)]
    assert mine
    total = int(mine[-1].split()[3])
    assert mine[-1] == f"embedded {total} of {total} texts"
    assert len(mine) >= total // EMBED_BATCH


async def test_a_job_whose_inputs_changed_is_refused(sessions: Sessions, source: Source) -> None:
    async def progress(message: str, data: Mapping[str, Any]) -> None:
        return None

    job = JobContext(
        id=uuid.uuid4(),
        kind="index",
        source_id=source.id,
        payload={"config": "A2", "configs": ["A2"], "hash": "0" * 64},
        progress=progress,
    )
    with pytest.raises(InputsChanged, match="not what this job was queued for"):
        await _indexer(sessions, source, FakeEmbedder())(job)
