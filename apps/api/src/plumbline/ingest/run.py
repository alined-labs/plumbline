"""Running the index stage (Lane D, task D4): one ingestion job per unit, a source in one
variant, claimed and run by a worker.

A job is self-describing: its payload names the configuration and the content hash, so a
worker rebuilds the unit from the job alone (the parse from data/processed, the chunks
from the chunker) and refuses to run if the hash differs, that is, if the source, the
parser, the chunker or the configuration changed since the job was queued.

Idempotent by content, with the index the judge of what is done: a unit whose job
succeeded is skipped while the index still holds its chunks and vectors, and run again
when it does not (a table emptied, migration 0004 reversed).

Embedding is the slow part (about 50 tokens a second on CPU), so it goes in batches of one
TEI request: each batch is recorded as it returns, so a run that dies loses at most one
batch, and each reports progress to the job's event stream.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

import anyio.to_thread
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.config import EvalConfig
from plumbline.core.types import ParsedDocument
from plumbline.corpus.manifest import Source
from plumbline.db.models import PUBLIC_TENANT, IngestionJob
from plumbline.db.session import tenant_session
from plumbline.ingest.index import Embedder, index_document, stored_counts
from plumbline.ingest.plan import Unit, plan_unit
from plumbline.jobs.queue import (
    QUEUED,
    SUCCEEDED,
    JobContext,
    add_event,
    enqueue,
    requeue_stale,
    work,
)

log = logging.getLogger(__name__)

KIND: Final = "index"
EMBED_BATCH: Final = 32  # texts per embedder call: one TEI request, the most a crash loses
STALE: Final = timedelta(hours=2)  # a running job older than this lost its worker


class InputsChanged(RuntimeError):
    """The source, parser, chunker or configuration changed since the job was queued."""


@dataclass(frozen=True)
class Outcome:
    unit: Unit
    status: str  # indexed, current, failed or busy
    detail: Mapping[str, Any]  # the job's result, or {"error": ...}


@dataclass(frozen=True)
class Indexer:
    """The job handler: embeds a unit's chunks and writes the unit to the index."""

    sessions: async_sessionmaker[AsyncSession]
    sources: Mapping[str, Source]
    configs: Mapping[str, EvalConfig]
    load_document: Callable[[Source], ParsedDocument]
    embedder_for: Callable[[Source, str], Embedder]  # a source's own cache, by model

    async def __call__(self, job: JobContext) -> Mapping[str, Any]:
        started = time.perf_counter()
        source = self.sources[job.source_id]
        config = self.configs[str(job.payload["config"])]
        unit = plan_unit(source, self.load_document(source), config, job.payload["configs"])
        if unit.content_hash != job.payload["hash"]:
            raise InputsChanged(f"{source.id} is not what this job was queued for")
        embedder = self.embedder_for(source, unit.embedding_model)
        # Identical texts (an unchanged paragraph in every version of an article) embed once.
        texts = list(dict.fromkeys(chunk.text_for_search for chunk in unit.embedded))
        vectors: dict[str, list[float]] = {}
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            vectors.update(
                zip(
                    batch,
                    await anyio.to_thread.run_sync(embedder.embed_documents, batch),
                    strict=True,
                )
            )
            await job.progress(
                f"embedded {len(vectors)} of {len(texts)} texts",
                {"done": len(vectors), "total": len(texts)},
            )
        embedded = {chunk.id for chunk in unit.embedded}
        await index_document(
            self.sessions,
            unit.document,
            unit.chunks,
            [vectors[c.text_for_search] if c.id in embedded else None for c in unit.chunks],
            variant=unit.variant,
        )
        return {
            "variant": unit.variant,
            "configs": list(unit.configs),
            "chunks": len(unit.chunks),
            "embedded": len(unit.embedded),
            "unique_texts": len(texts),
            "seconds": round(time.perf_counter() - started, 1),
        }


async def run_units(
    sessions: async_sessionmaker[AsyncSession],
    units: Sequence[Unit],
    indexer: Indexer,
    *,
    worker: str,
) -> list[Outcome]:
    """Queue what the index does not hold, work the queue, and say what became of each unit."""
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        await requeue_stale(session, STALE)
    job_ids: dict[int, Any] = {}
    outcomes: dict[int, Outcome] = {}
    for position, unit in enumerate(units):
        async with tenant_session(sessions, PUBLIC_TENANT) as session:
            job, queued = await enqueue(
                session,
                tenant_id=PUBLIC_TENANT,
                kind=KIND,
                source_id=unit.source.id,
                content_hash=unit.content_hash,
                payload={
                    "config": unit.config.name,
                    "configs": list(unit.configs),
                    "variant": unit.variant,
                    "hash": unit.content_hash,
                },
            )
            job_ids[position] = job.id
            if not queued and job.status == SUCCEEDED:
                held = await stored_counts(sessions, unit.variant, unit.source.id)
                if held == (len(unit.chunks), len(unit.embedded)):
                    outcomes[position] = Outcome(unit, "current", dict(job.result or {}))
                else:
                    job.status, job.error, job.finished_at = QUEUED, None, None
                    add_event(session, job.id, PUBLIC_TENANT, "requeued", f"the index holds {held}")
            elif not queued and job.status != QUEUED:
                outcomes[position] = Outcome(unit, "busy", {"status": job.status})
    ran = await work(sessions, PUBLIC_TENANT, {KIND: indexer}, worker)
    log.info("%d jobs run", ran)
    for position, unit in enumerate(units):
        if position in outcomes:
            continue
        async with tenant_session(sessions, PUBLIC_TENANT) as session:
            job = await session.get_one(IngestionJob, job_ids[position])
            result, error, status = dict(job.result or {}), job.error, job.status
        outcomes[position] = (
            Outcome(unit, "indexed", result)
            if status == SUCCEEDED
            else Outcome(unit, "failed", {"error": error or status})
        )
    return [outcomes[position] for position in range(len(units))]
