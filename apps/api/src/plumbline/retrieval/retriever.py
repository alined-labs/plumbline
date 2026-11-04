"""The retriever one configuration describes: dense, BM25 or hybrid search over its chunk
set (its variant), then the parent-article merge when the configuration asks for it.

`Retriever.search` is generation.pipeline.ChunkSearch, so the answer pipeline, the API's
debug route and the evaluation runner all search the same way. Reranking is not here:
the pipeline reorders candidates with generation.pipeline.reorder, the one ordering the
answers and the offline metrics share (ADR-0005: nothing reranks online).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from plumbline.cache import ResponseCache
from plumbline.core.config import EvalConfig
from plumbline.core.types import (
    Chunk,
    Jurisdiction,
    Language,
    RetrievalScores,
    Retrieved,
)
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.db.models import PUBLIC_TENANT, ChunkRow
from plumbline.db.session import tenant_session_sync
from plumbline.generation.lawsource import to_chunk
from plumbline.generation.llm import client_for
from plumbline.generation.pipeline import ChunkSearch, Reranker
from plumbline.retrieval import sql
from plumbline.retrieval.embed import TeiEmbedder
from plumbline.retrieval.fusion import Hit, merge_parents
from plumbline.retrieval.index import variant_key
from plumbline.retrieval.rewrite import REWRITE_MODEL, spanish_rewriter
from plumbline.settings import Settings


class QueryEmbedder(Protocol):
    def embed_query(self, question: str) -> list[float]: ...


def utc_today() -> date:
    return datetime.now(UTC).date()


class Retriever:
    """generation.pipeline.ChunkSearch over the chunks table, for one configuration."""

    def __init__(
        self,
        config: EvalConfig,
        sessions: sessionmaker[Session],
        embedder: QueryEmbedder | None,
        *,
        spanish: Callable[[str], str] | None = None,  # the cross-lingual rewrite (A6)
        tenant_id: uuid.UUID = PUBLIC_TENANT,
        today: Callable[[], date] = utc_today,
    ) -> None:
        mode = config.retrieval.mode
        if mode == "none":
            raise ValueError(f"{config.name} retrieves nothing: give the pipeline a LawSource")
        if mode != "bm25" and embedder is None:
            raise ValueError(f"{config.name} searches by embedding: give it an embedder")
        self.config = config
        self.mode: sql.Mode = mode
        self.variant = variant_key(config)
        self.sessions = sessions
        self.embedder = embedder
        self.spanish = spanish if config.retrieval.cross_lingual_rewrite else None
        self.tenant_id = tenant_id
        self.today = today

    def search(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: Sequence[Jurisdiction] | None,
        as_of: date | None,
        languages: Sequence[Language] | None = None,
    ) -> list[Retrieved]:
        """The best `k` chunks, or with merge_parent the best `k` articles, each in the
        place of its best-ranked paragraph. Without a date the law as it stands today
        answers: the as-of filter always applies (see sql)."""
        retrieval = self.config.retrieval
        vector = (
            self.embedder.embed_query(question)
            if self.embedder is not None and self.mode != "bm25"
            else None
        )
        filters = sql.Filters(self.variant, as_of or self.today(), jurisdictions, languages)
        with tenant_session_sync(self.sessions, self.tenant_id) as session:
            hits = sql.search(
                session,
                self.mode,
                filters,
                vector=vector,
                query=question,
                spanish_query=self.spanish(question) if self.spanish else None,
                candidates=retrieval.candidates,
                rrf_k=retrieval.rrf_k,
            )
            leaves = self._load(session, [h.id for h in hits])
            if not self.config.chunker.merge_parent:
                return [
                    _retrieved(leaves[hit.id], rank, hit.score, hit)
                    for rank, hit in enumerate(hits[:k], start=1)
                ]
            ranked = [Hit(h.id, leaves[h.id].parent_id, h.score) for h in hits]
            articles = merge_parents(ranked, k)
            parents = self._load(
                session, [a.chunk_id for a in articles if a.chunk_id not in leaves]
            )
        by_id = {h.id: h for h in hits}
        return [
            _retrieved(
                leaves.get(article.chunk_id) or parents[article.chunk_id],
                rank,
                article.score,
                by_id[article.matched[0]],  # the scores shown are its best paragraph's
            )
            for rank, article in enumerate(articles, start=1)
        ]

    def _load(self, session: Session, ids: Sequence[str]) -> dict[str, Chunk]:
        if not ids:
            return {}
        rows = session.scalars(
            select(ChunkRow).where(ChunkRow.variant == self.variant, ChunkRow.id.in_(ids))
        )
        found = {row.id: to_chunk(row) for row in rows}
        if missing := set(ids) - set(found):
            raise LookupError(f"variant {self.variant} lacks chunks {sorted(missing)[:3]}")
        return found


def _retrieved(chunk: Chunk, rank: int, score: float, hit: sql.SqlHit) -> Retrieved:
    scores = RetrievalScores(
        dense=hit.dense,
        bm25=hit.bm25,
        rrf=hit.rrf,
        dense_rank=hit.dense_rank,
        bm25_rank=hit.bm25_rank,
    )
    return Retrieved(chunk=chunk, rank=rank, score=score, scores=scores)


@dataclass(frozen=True)
class Retrieval:
    """api.search.Retrieval: a configuration's search, and its reranker (none online)."""

    search: ChunkSearch
    reranker: Reranker | None = None


def online_retrieval(settings: Settings, cache: ResponseCache) -> Callable[[EvalConfig], Retrieval]:
    """api.search.RetrievalFactory for the API: one blocking engine for every
    configuration, a TEI embedder for the configuration's model, and no reranker
    (ADR-0005). The question's embedding is recorded in `cache`; it holds no source text."""
    sessions = make_sync_sessionmaker(make_sync_engine(settings.database_url))

    def build(config: EvalConfig) -> Retrieval:
        embedder = TeiEmbedder(settings.embed_url, cache, model=config.retrieval.embedding_model)
        # A6 rewrites the question into Spanish for the keyword search; the request holds
        # only the question, so it records in the same cache as the embedding.
        spanish = (
            spanish_rewriter(client_for(REWRITE_MODEL, cache=cache, settings=settings))
            if config.retrieval.cross_lingual_rewrite
            else None
        )
        return Retrieval(search=Retriever(config, sessions, embedder, spanish=spanish))

    return build
