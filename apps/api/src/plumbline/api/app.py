"""The FastAPI application (Lane D). Run it with `make api`, which uses the factory:
`uvicorn plumbline.api.app:create_app --factory`."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api import admin, tier
from plumbline.api.openapi import build_openapi
from plumbline.api.routes import router
from plumbline.core.stream import AnswerPipeline
from plumbline.db import make_engine, make_sessionmaker
from plumbline.generation.stub import StubPipeline
from plumbline.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    pipeline: AnswerPipeline | None = None,
    sessions: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Plumbline API",
        version=version("plumbline"),
        summary="Tenancy-law answers with verified citations. Legal information, not legal advice.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.pipeline = pipeline or StubPipeline(delay_ms=settings.stub_delay_ms)
    # The engine connects on first use, so an app that never touches the database (the
    # stub, the OpenAPI export) runs without one.
    app.state.sessions = sessions or make_sessionmaker(make_engine(settings.database_url))
    app.state.tier = tier.TierStore(app.state.sessions, settings.demo_tier)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    app.include_router(router)
    app.include_router(admin.router)
    app.include_router(tier.router)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
