"""The law itself, searched (Lane D, task D8): what the MCP server's `search_law` tool calls,
and anyone else who wants the provisions behind a question without an answer.

    GET /api/law/search?q=&jurisdiction=&as_of=&k=   the k best provisions, best first
    POST /api/law/check-clause                       one clause against the law it touches

It searches as the served configuration does (its Claude twin's retrieval, as /api/ask), and
calls no model: one embedding of the query. Each hit carries what a citation needs, its id
(for GET /api/chunks/{id}), reference, label and source, and the provision's text, except for
a source whose terms forbid republishing it (api/restricted.py): a hit quotes nothing, so a
restricted hit's text is empty and `restricted` says why; GET /api/chunks/{id}?quote= then
shows the passage an answer quotes, and no more. Searches count against a daily allowance of
their own (api/quota.py).

A clause check (the MCP server's `check_clause`) is a lease check of one clause: the same
tier rule, daily cap and allowance as a whole lease, the same redaction before any model
reads it (until Presidio's redactor lands, every clause is refused), and Lane C's check on
Claude. It answers a finding resting on verified quotes, or none when the law found does
not address the clause, always with the lease checker's disclaimer.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from plumbline.api import answering
from plumbline.api.chunks import SourceLink, _sources
from plumbline.api.leases import LeaseChecker
from plumbline.api.problems import MEDIA_TYPE, ApiError
from plumbline.api.quota import Quota, set_visitor_cookie
from plumbline.api.restricted import is_restricted
from plumbline.api.search import RetrievalFactory
from plumbline.api.tier import tier_store
from plumbline.core.types import ArticleRef, Jurisdiction, Language, ProvisionStatus, Retrieved
from plumbline.corpus.leases import lease_disclaimer
from plumbline.generation.router import RedactionRefused, RouteRefused
from plumbline.leases.schema import Finding
from plumbline.settings import Settings

MAX_K: Final = 10
MAX_CLAUSE: Final = 4000  # characters: one clause, not a lease

router = APIRouter(prefix="/api/law", tags=["law"])


def _problem(description: str) -> dict[str, object]:
    schema = {"$ref": "#/components/schemas/Problem"}
    return {"description": description, "content": {MEDIA_TYPE: {"schema": schema}}}


class LawHit(BaseModel):
    rank: int = Field(ge=1)
    chunk_id: str  # for GET /api/chunks/{chunk_id}
    ref: ArticleRef
    label: str  # how a citation names it: "Fla. Stat. § 83.49(3)(a)"
    heading: str | None  # None for a restricted source
    text: str  # empty for a restricted source
    language: Language
    status: ProvisionStatus
    effective_from: date | None
    effective_to: date | None  # exclusive; None while in force
    source: SourceLink | None  # None for a document outside the manifest
    restricted: bool  # True: the source's terms allow no more than a quoted passage


class LawSearch(BaseModel):
    query: str
    jurisdiction: Jurisdiction | None
    as_of: date | None  # None: the law in force today
    config_name: str  # the served configuration whose retrieval answered
    hits: list[LawHit]


def hit(retrieved: Retrieved) -> LawHit:
    chunk = retrieved.chunk
    source = _sources().get(chunk.document_id)
    restricted = is_restricted(source)
    return LawHit(
        rank=retrieved.rank,
        chunk_id=chunk.id,
        ref=chunk.ref,
        label=chunk.label,
        heading=None if restricted else chunk.heading,
        text="" if restricted else chunk.text,
        language=chunk.language,
        status=chunk.status,
        effective_from=chunk.effective_from,
        effective_to=chunk.effective_to,
        source=SourceLink(id=source.id, title=source.title, url=str(source.url))
        if source
        else None,
        restricted=restricted,
    )


@router.get(
    "/search",
    responses={
        429: _problem(
            "`quota_reached`: today's searches are used up; Retry-After gives the seconds"
            " until 00:00 UTC."
        ),
        503: _problem("This server has no retrieval (a development server)."),
    },
)
async def search_law(
    request: Request,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=1000, description="What to look for.")],
    jurisdiction: Annotated[
        Jurisdiction | None, Query(description="Search one jurisdiction; all when absent.")
    ] = None,
    as_of: Annotated[
        date | None, Query(description="The law in force on this date; today when absent.")
    ] = None,
    k: Annotated[int, Query(ge=1, le=MAX_K, description="How many provisions.")] = 5,
) -> LawSearch:
    state = request.app.state
    factory: RetrievalFactory | None = state.retrieval
    if factory is None:
        raise HTTPException(503, "This server has no retrieval.")
    settings: Settings = state.settings
    quota: Quota = state.quota
    visitor = await quota.admit(request, "search")
    config = answering.served_config(settings.answer_config)
    found = await asyncio.to_thread(
        factory(config).search.search,
        q,
        k=k,
        jurisdictions=[jurisdiction] if jurisdiction else None,
        as_of=as_of,
    )
    set_visitor_cookie(response, visitor, settings)
    return LawSearch(
        query=q,
        jurisdiction=jurisdiction,
        as_of=as_of,
        config_name=config.name,
        hits=[hit(r) for r in found[:k]],
    )


class ClauseRequest(BaseModel):
    clause: Annotated[str, Field(min_length=1, max_length=MAX_CLAUSE)]  # one clause's text
    jurisdiction: Jurisdiction  # the law the lease is under
    as_of: date | None = None  # the law in force on this date (the signing date); None: today


class ClauseResult(BaseModel):
    jurisdiction: Jurisdiction
    as_of: date | None
    finding: Finding | None  # None: the law found does not address the clause
    disclaimer: str


@router.post(
    "/check-clause",
    responses={
        429: _problem(
            "`quota_reached`: today's lease checks are used up (a clause counts as one)."
        ),
        503: _problem(
            "`lease_checks_paused` (the demo tier or today's budget does not run them) or"
            " `redaction_refused` (the clause cannot be redacted, so no model may read it)."
        ),
    },
)
async def check_clause(request: Request, response: Response, body: ClauseRequest) -> ClauseResult:
    state = request.app.state
    checker: LeaseChecker = state.lease_checker
    try:
        route = await checker.route(await tier_store(request).current())
    except RouteRefused as exc:
        raise ApiError(503, "lease_checks_paused", str(exc)) from exc
    quota: Quota = state.quota
    visitor = await quota.admit(request, "lease")
    try:
        finding = await checker.clause(
            body.clause, route, jurisdiction=body.jurisdiction, as_of=body.as_of
        )
    except RedactionRefused:
        # From None: the redactor's message may quote the text it refused.
        raise ApiError(
            503, "redaction_refused", "This clause can't be checked until it can be redacted."
        ) from None
    except RouteRefused as exc:
        raise ApiError(503, "lease_checks_paused", str(exc)) from exc
    set_visitor_cookie(response, visitor, state.settings)
    response.headers["Cache-Control"] = "no-store"  # a reader's own clause
    return ClauseResult(
        jurisdiction=body.jurisdiction,
        as_of=body.as_of,
        finding=finding,
        disclaimer=lease_disclaimer(),
    )
