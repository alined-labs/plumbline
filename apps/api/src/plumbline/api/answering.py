"""What the API answers with (Lane D, task D5b): Lane C's answer pipeline and lease
checker, wired to the index in Postgres, and the rule for when the stand-ins may serve.

The configuration is the settings' `answer_config`. One that retrieves needs a retrieval
factory (Lane A's Retriever, task A5b); until the server has one, the API answers with the
long-context baseline (LC) instead, which reads the whole law of the question's
jurisdictions from the index (Lane C's SqlLawSource), and the answer's trace names LC, so nobody mistakes it for
the configured one. The lease checker needs a search, so without retrieval it is paused.

The stand-ins (generation/stub.py, api/lease_stub.py) serve in dev and test, so the tests
and a front-end developer's `make api` stay instant and free; ENVIRONMENT=prod answers for
real (also the way to try the real pipeline locally), and refuses to start on either
stand-in (`refuse_stubs`). The switch is the environment alone: a key copied into .env from
.env.example must not change which pipeline answers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Final

from redis.asyncio import Redis
from sqlalchemy.orm import Session, sessionmaker

from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.api.leases import LeaseChecker
from plumbline.api.search import CONFIGS, Retrieval, RetrievalFactory
from plumbline.core.config import EvalConfig, load_config
from plumbline.core.stream import AnswerPipeline, Question, StreamError, StreamEvent
from plumbline.core.types import DemoTier, Jurisdiction
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.generation.lawsource import SqlLawSource
from plumbline.generation.llm import client_for
from plumbline.generation.pipeline import MODELS, Pipeline
from plumbline.generation.router import (
    ROUTES,
    Kind,
    MeteredClient,
    RedisSpendMeter,
    Route,
    Router,
    RouteRefused,
    SpendMeter,
    SyntheticOnlyRedactor,
    Upload,
)
from plumbline.generation.stub import StubPipeline
from plumbline.leases.checker import LeaseEvent
from plumbline.leases.service import LeaseChecker as RealLeaseChecker
from plumbline.retrieval.index import variant_key
from plumbline.settings import Settings

log = logging.getLogger(__name__)
LONG_CONTEXT: Final = "LC"
# What the public API answers and checks leases with: Claude, whatever route a
# configuration names. The human's call on 2026-10-20: Gemini has a few dollars left for
# the golden cross-check and nothing else, while Claude's spend is not the constraint.
SERVED_ROUTE: Final = "premium"
PAUSED: Final = "Lease checks are not available on this server yet."


class StubRefused(RuntimeError):
    """Production was handed a stand-in."""


def wants_real(settings: Settings) -> bool:
    return settings.environment == "prod"


def refuse_stubs(settings: Settings, pipeline: object, lease_checker: object) -> None:
    if settings.environment != "prod":
        return
    for part in (pipeline, lease_checker):
        if isinstance(part, StubPipeline | StubLeaseChecker):
            raise StubRefused(f"production refuses to start on {type(part).__name__}")


def default_retrieval(settings: Settings) -> RetrievalFactory | None:
    """Lane A's retrieval for a configuration. None until A5b's Retriever lands."""
    return None


def router_for(settings: Settings, meter: SpendMeter) -> Router:
    caps = {
        "gemini": settings.gemini_daily_cap_usd,
        "anthropic": settings.anthropic_daily_cap_usd,
        "cohere": settings.cohere_daily_cap_usd,
    }
    return Router(meter, caps)


def spend_meter(settings: Settings) -> SpendMeter:
    return RedisSpendMeter(Redis.from_url(settings.redis_url))


def default_pipeline(
    settings: Settings,
    retrieval: RetrievalFactory | None,
    sessions: sessionmaker[Session],
    meter: SpendMeter,
) -> AnswerPipeline:
    if not wants_real(settings):
        return StubPipeline(delay_ms=settings.stub_delay_ms)
    config = load_config(CONFIGS / f"{settings.answer_config}.yaml")
    if _retrieves(config) and retrieval is None:
        log.warning(
            "no retrieval on this server: answering with %s, not %s", LONG_CONTEXT, config.name
        )
        config = load_config(CONFIGS / f"{LONG_CONTEXT}.yaml")
    config = on_claude(config)
    return ServedPipeline(
        lambda: _build(config, retrieval, sessions, meter), router_for(settings, meter)
    )


def default_lease_checker(
    settings: Settings,
    retrieval: RetrievalFactory | None,
    meter: SpendMeter,
) -> LeaseChecker:
    if not wants_real(settings):
        return StubLeaseChecker(delay_ms=settings.stub_delay_ms)
    if retrieval is None:
        log.warning("no retrieval on this server: lease checks are paused")
        return PausedLeaseChecker()
    search = retrieval(load_config(CONFIGS / f"{settings.answer_config}.yaml")).search
    # Real uploads stay refused until Presidio's redactor (P2) replaces this one.
    return ClaudeLeaseChecker(
        router=router_for(settings, meter),
        meter=meter,
        redactor=SyntheticOnlyRedactor(),
        search=search,
    )


def on_claude(config: EvalConfig) -> EvalConfig:
    """The configuration on SERVED_ROUTE, renamed so the trace says what answered: its hash
    covers the route, and "-claude" keeps it from passing for the evaluated original."""
    if config.generation.route == SERVED_ROUTE:
        return config
    generation = config.generation.model_copy(update={"route": SERVED_ROUTE})
    return config.model_copy(update={"name": f"{config.name}-claude", "generation": generation})


class ClaudeLeaseChecker(RealLeaseChecker):
    """Lane C's checker with the Router's refusals (the tier) but SERVED_ROUTE's model."""

    async def route(self, tier: DemoTier) -> Route:
        lease = await super().route(tier)  # RouteRefused off the full tier
        served = ROUTES[SERVED_ROUTE]
        return Route(lease.name, served.model, served.provider)


class PausedLeaseChecker:
    """No search, no lease check: every start answers 503 lease_checks_paused."""

    async def route(self, tier: DemoTier) -> Route:
        raise RouteRefused(PAUSED)

    def stream(
        self, upload: Upload, route: Route, *, jurisdiction: Jurisdiction | None, as_of: date | None
    ) -> AsyncIterator[LeaseEvent]:
        raise RouteRefused(PAUSED)


class ServedPipeline:
    """Lane C's Pipeline, built on the first question rather than at start-up (it asks the
    index which jurisdictions it holds, and an app that never answers, such as the OpenAPI
    export, must not need a database), behind the tier: on the static tier it refuses."""

    def __init__(self, build: Callable[[], Pipeline], router: Router) -> None:
        self._build = build
        self._router = router
        self._pipeline: Pipeline | None = None
        self._lock = asyncio.Lock()

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        try:
            await self._router.route(Kind.QUESTION, tier=question.tier)
        except RouteRefused as exc:
            yield StreamError(message=str(exc), retryable=False)
            return
        async with self._lock:
            if self._pipeline is None:
                self._pipeline = await asyncio.to_thread(self._build)
        async for event in self._pipeline.stream(question):
            yield event


def _retrieves(config: EvalConfig) -> bool:
    return not (config.generation.long_context or config.retrieval.mode == "none")


def _build(
    config: EvalConfig,
    retrieval: RetrievalFactory | None,
    sessions: sessionmaker[Session],
    meter: SpendMeter,
) -> Pipeline:
    client = MeteredClient(client_for(MODELS[config.generation.route]), meter)
    if not _retrieves(config):
        law = SqlLawSource(sessions, variant_key(config))
        return Pipeline(config, law=law, reranker=None, indexed=law.jurisdictions(), client=client)
    if retrieval is None:  # default_pipeline falls back to LC before this can happen
        raise ValueError(f"{config.name} retrieves and the server has no retrieval")
    parts: Retrieval = retrieval(config)
    indexed = SqlLawSource(sessions, variant_key(config)).jurisdictions()
    return Pipeline(
        config, search=parts.search, reranker=parts.reranker, indexed=indexed, client=client
    )


def sync_sessions(settings: Settings) -> sessionmaker[Session]:
    return make_sync_sessionmaker(make_sync_engine(settings.database_url))
