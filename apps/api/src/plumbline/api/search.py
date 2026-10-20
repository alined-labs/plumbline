"""The retrieval debug route (Lane D): GET /api/search shows what retrieval returns for a
question and every score behind each hit (dense, BM25, RRF, rerank), so a reader of an
evaluation can see why a passage was or was not found.

It runs the same steps the answer pipeline runs (search `rerank_candidates` when the
configuration reranks, else `top_k`; rerank the candidates' text_for_search; cut with
generation.pipeline.reorder), so the scores it shows are the ones an answer would use.
The date follows the pipeline too: the question's `as_of` reaches the search only when the
configuration filters by date, and the search always reads the law in force on one day, that
date or today (UTC). The result names that day (`law_date`), and each hit's chunk carries its
own validity (status, effective_from, effective_to, validity_note), so an evaluation can see
why a provision in force on another day was left out.

It returns whole chunks, fetch-only sources included, so it takes the admin token and does
not exist while none is set. Retrieval itself is Lane A's: the app is given a factory that
builds a search and a reranker for a configuration, and without one the route answers 503.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from plumbline.api.admin import require_admin
from plumbline.core.config import EvalConfig, load_config
from plumbline.core.types import Jurisdiction, Retrieved
from plumbline.generation.pipeline import ChunkSearch, Reranker, reorder
from plumbline.generation.router import utc_today
from plumbline.settings import ROOT, Settings

router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_admin)])
CONFIGS = ROOT / "evals" / "configs"


class Retrieval(Protocol):
    """What the route needs for one configuration: a search, and a reranker when the
    configuration reranks."""

    @property
    def search(self) -> ChunkSearch: ...

    @property
    def reranker(self) -> Reranker | None: ...


class RetrievalFactory(Protocol):
    def __call__(self, config: EvalConfig, /) -> Retrieval: ...


class SearchResult(BaseModel):
    query: str
    config: str
    config_hash: str
    k: int
    jurisdictions: list[Jurisdiction]
    as_of: date | None  # the date asked for
    as_of_filter: bool  # whether the configuration searches the law as of the asked date
    law_date: date  # the day whose law was searched: as_of when filtered, else today (UTC)
    candidates: int  # what search returned before the reranker cut it to k
    timings_ms: dict[str, float]
    hits: list[Retrieved]


@router.get("/search")
async def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=2000, description="The question.")],
    k: Annotated[
        int | None,
        Query(ge=1, le=50, description="Hits to return; default: the configuration's top_k."),
    ] = None,
    jurisdictions: Annotated[list[Jurisdiction] | None, Query()] = None,
    as_of: date | None = None,
    config: Annotated[str | None, Query(description="A configuration of evals/configs.")] = None,
) -> SearchResult:
    settings: Settings = request.app.state.settings
    factory: RetrievalFactory | None = request.app.state.retrieval
    if factory is None:
        raise HTTPException(status_code=503, detail="Retrieval is not configured on this server.")
    chosen = _config(config or settings.answer_config)
    retrieval = factory(chosen)
    cut = k or chosen.retrieval.top_k
    reranker = retrieval.reranker
    timings: dict[str, float] = {}
    # As the pipeline does: a configuration without the as-of filter searches today's law.
    searched_as_of = as_of if chosen.retrieval.as_of_filter else None

    started = time.perf_counter()
    found = await asyncio.to_thread(
        retrieval.search.search,
        q,
        k=chosen.retrieval.rerank_candidates if reranker else cut,
        jurisdictions=jurisdictions or None,
        as_of=searched_as_of,
    )
    timings["search"] = _since(started)
    candidates = len(found)
    if reranker is not None and found:
        started = time.perf_counter()
        scores = await asyncio.to_thread(
            reranker.scores, q, [hit.chunk.text_for_search for hit in found]
        )
        found = reorder(found, scores, cut)
        timings["rerank"] = _since(started)
    return SearchResult(
        query=q,
        config=chosen.name,
        config_hash=chosen.config_hash(),
        k=cut,
        jurisdictions=jurisdictions or [],
        as_of=as_of,
        as_of_filter=chosen.retrieval.as_of_filter,
        law_date=searched_as_of or utc_today(),
        candidates=candidates,
        timings_ms=timings,
        hits=found[:cut],
    )


def _config(name: str) -> EvalConfig:
    # A configuration is named by a short word, never a path.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or not (CONFIGS / f"{name}.yaml").is_file():
        raise HTTPException(status_code=404, detail="No such configuration.")
    return load_config(CONFIGS / f"{name}.yaml")


def _since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
