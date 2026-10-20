"""The FastAPI application (Lane D). Run it with `make api`, which uses the factory:
`uvicorn plumbline.api.app:create_app --factory`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import (
    admin,
    answering,
    answers,
    chunks,
    health,
    leases,
    problems,
    search,
    sources,
    tier,
)
from plumbline.api.leases import LeaseChecker
from plumbline.api.openapi import build_openapi
from plumbline.api.quota import Counter, Quota, RedisCounter
from plumbline.api.runs import Runs
from plumbline.api.search import RetrievalFactory
from plumbline.api.sources import Corpus
from plumbline.core.stream import AnswerPipeline
from plumbline.corpus.manifest import load_manifest
from plumbline.db import make_engine, make_sessionmaker
from plumbline.settings import ROOT, Settings, get_settings

# One router per module, registered here at start-up, in the order the schema lists them.
ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    answers.router,
    admin.router,
    tier.router,
    sources.router,
    search.router,
    chunks.router,
    leases.router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.runs.close()  # lease checks still going end as interrupted


def create_app(
    settings: Settings | None = None,
    pipeline: AnswerPipeline | None = None,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    corpus: Corpus | None = None,
    retrieval: RetrievalFactory | None = None,
    counter: Counter | None = None,
    lease_checker: LeaseChecker | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Plumbline API",
        version=version("plumbline"),
        summary="Tenancy-law answers with verified citations. Legal information, not legal advice.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Lane A's retrieval, when the server has it. What answers without one, and when the
    # stand-ins may, is api/answering.py's rule; production refuses to start on a stand-in.
    retrieval = retrieval or answering.default_retrieval(settings)
    app.state.retrieval = retrieval
    meter = answering.spend_meter(settings)
    app.state.pipeline = pipeline or answering.default_pipeline(
        settings, retrieval, answering.sync_sessions(settings), meter
    )
    app.state.lease_checker = lease_checker or answering.default_lease_checker(
        settings, retrieval, meter
    )
    answering.refuse_stubs(settings, app.state.pipeline, app.state.lease_checker)
    app.state.runs = Runs(leases.failure)
    # The engine connects on first use, so an app that never touches the database (the
    # stub, the OpenAPI export) runs without one.
    app.state.sessions = sessions or make_sessionmaker(make_engine(settings.database_url))
    app.state.tier = tier.TierStore(app.state.sessions, settings.demo_tier)
    app.state.corpus = corpus or Corpus(load_manifest, ROOT)
    app.state.quota = Quota(
        settings, app.state.sessions, counter or RedisCounter(settings.redis_url)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
        allow_credentials=True,  # the visitor cookie travels with the front end's requests
        expose_headers=["Retry-After", "Location"],  # a cross-origin page reads these too
    )
    problems.install(app)
    for module_router in ROUTERS:
        app.include_router(module_router)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
