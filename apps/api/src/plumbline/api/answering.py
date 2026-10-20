"""What the API answers with (Lane D, task D5b): Lane C's answer pipeline and lease
checker, wired to the index in Postgres, and the rule for when the stand-ins may serve.

The configuration is the settings' `answer_config`. One that retrieves needs a retrieval
factory (Lane A's Retriever, `default_retrieval`); a server without one answers with the
long-context baseline (LC) instead, which reads the whole law of the question's
jurisdictions from the index (Lane C's SqlLawSource), and the answer's trace names LC, so
nobody mistakes it for the configured one. Either way the API serves the configuration's
Claude twin from evals/configs (`served_config`). The lease checker needs a search, so without retrieval it is paused.

The stand-ins (generation/stub.py, api/lease_stub.py) serve in dev and test, so the tests
and a front-end developer's `make api` stay instant and free; ENVIRONMENT=prod answers for
real (also the way to try the real pipeline locally), and refuses to start on either
stand-in (`refuse_stubs`). The switch is the environment alone: a key copied into .env from
.env.example must not change which pipeline answers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from datetime import date
from typing import Final

from redis.asyncio import Redis
from sqlalchemy.orm import Session, sessionmaker

from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.api.leases import LeaseChecker
from plumbline.api.search import CONFIGS, Retrieval, RetrievalFactory
from plumbline.cache import get_cache
from plumbline.core.config import EvalConfig, load_config
from plumbline.core.stream import AnswerPipeline, Question, StreamError, StreamEvent
from plumbline.core.types import DemoTier, Jurisdiction
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.generation.lawsource import SqlLawSource
from plumbline.generation.llm import client_for
from plumbline.generation.pipeline import MODELS, LawSource, Pipeline
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
from plumbline.ingest.upload import guess_language
from plumbline.leases.check import check_clause
from plumbline.leases.checker import LeaseEvent
from plumbline.leases.schema import Finding
from plumbline.leases.service import LeaseChecker as RealLeaseChecker
from plumbline.retrieval.index import variant_key
from plumbline.retrieval.jurisdiction import detect as detect_jurisdictions
from plumbline.retrieval.retriever import online_retrieval
from plumbline.settings import Settings

log = logging.getLogger(__name__)
LONG_CONTEXT: Final = "LC"
# What the public API answers and checks leases with: Claude, whatever route a
# configuration names. The human's call on 2026-10-20: Gemini has a few dollars left for
# the golden cross-check and nothing else, while Claude's spend is not the constraint.
SERVED_ROUTE: Final = "premium"
PAUSED: Final = "Lease checks are not available on this server yet."
SPENT: Final = (
    "Today's budget for live answers is used up. Plumbline answers again from 00:00 UTC;"
    " until then, browse the stored answers and the cited articles."
)
# The most law the long-context path sends in one call. Claude counted Florida's whole law
# (208,467 characters) as 69,257 input tokens, about 3 characters a token; 150k tokens keeps
# an answer well inside the context window, at about US$0.30 on Sonnet.
MAX_LAW_TOKENS: Final = 150_000
CHARS_PER_TOKEN: Final = 3
TOO_MUCH_LAW: Final = (
    "This question would need the whole law of {names} at once, more than Plumbline reads in"
    " one answer for now. Please ask about one jurisdiction at a time."
)


class StubRefused(RuntimeError):
    """Production was handed a stand-in, or a configuration nobody evaluated on Claude."""


def wants_real(settings: Settings) -> bool:
    return settings.environment == "prod"


def refuse_stubs(settings: Settings, pipeline: object, lease_checker: object) -> None:
    if settings.environment != "prod":
        return
    for part in (pipeline, lease_checker):
        if isinstance(part, StubPipeline | StubLeaseChecker):
            raise StubRefused(f"production refuses to start on {type(part).__name__}")


def default_retrieval(settings: Settings) -> RetrievalFactory | None:
    """Lane A's retrieval (A5b) where the API answers for real: SQL search over the index, the
    question embedded by TEI through the response cache. Outside production, None: the
    stand-ins need no search, and the debug route answers 503."""
    if not wants_real(settings):
        return None
    return online_retrieval(settings, get_cache(settings.cache_mode, settings.cache_dir))


def router_for(settings: Settings, meter: SpendMeter) -> Router:
    caps = {
        "gemini": settings.gemini_daily_cap_usd,
        "anthropic": settings.anthropic_daily_cap_usd,
        "cohere": settings.cohere_daily_cap_usd,
    }
    return Router(meter, caps)


async def spent(router: Router) -> bool:
    """Whether SERVED_ROUTE's provider has spent its daily cap. The API checks before every
    live answer and lease check, so the cap holds on its own; the kill switch (P5) reads the
    same counters and lowers the tier for the site as a whole. A call already running when
    the cap is crossed finishes, so a day can end over the cap by every call then in flight."""
    provider = ROUTES[SERVED_ROUTE].provider
    return await router.meter.spent_today(provider) >= router.caps.get(provider, 0.0)


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
    config = served_config(settings.answer_config)
    if _retrieves(config) and retrieval is None:
        log.warning(
            "no retrieval on this server: answering with %s, not %s", LONG_CONTEXT, config.name
        )
        config = served_config(LONG_CONTEXT)
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
    search = retrieval(served_config(settings.answer_config)).search
    # Real uploads stay refused until Presidio's redactor (P2) replaces this one.
    return ClaudeLeaseChecker(
        router=router_for(settings, meter),
        meter=meter,
        redactor=SyntheticOnlyRedactor(),
        search=search,
    )


def served_config(name: str) -> EvalConfig:
    """The evaluated configuration the API serves for `name`: the file itself when it is on
    SERVED_ROUTE, otherwise its Claude twin (Lane A's `<name>-claude.yaml`), so the trace's
    hash is exactly the one /evals reports. A configuration with no twin refuses to start."""
    config = load_config(CONFIGS / f"{name}.yaml")
    if config.generation.route == SERVED_ROUTE:
        return config
    twin = CONFIGS / f"{name}-claude.yaml"
    if twin.exists():
        config = load_config(twin)
        if config.generation.route == SERVED_ROUTE:
            return config
    raise StubRefused(f"{name} has no configuration on the {SERVED_ROUTE} route to serve")


class ClaudeLeaseChecker(RealLeaseChecker):
    """Lane C's checker with the Router's refusals (the tier) but SERVED_ROUTE's model."""

    async def route(self, tier: DemoTier) -> Route:
        lease = await super().route(tier)  # RouteRefused off the full tier
        if await spent(self.router):
            raise RouteRefused(SPENT)
        served = ROUTES[SERVED_ROUTE]
        return Route(lease.name, served.model, served.provider)

    async def clause(
        self,
        text: str,
        route: Route,
        *,
        jurisdiction: Jurisdiction,
        as_of: date | None,
    ) -> Finding | None:
        # As a whole lease is (leases/checker.py): redacted before any model sees it, in a
        # worker thread, refused rather than sent unredacted.
        language = guess_language(text)
        upload = Upload(text=text, language=language, synthetic=False)
        redacted = await asyncio.to_thread(self.redactor.redact, upload)
        kwargs = {"cache": self.cache} if self.cache is not None else {}
        client = MeteredClient(self.client_for_model(route.model, **kwargs), self.meter)
        checked = await check_clause(
            "1",
            redacted,
            language,
            jurisdiction=jurisdiction,
            search=self.search,
            client=client,
            as_of=as_of,
            model=route.model,
        )
        return checked.finding


class PausedLeaseChecker:
    """No search, no lease check: every start answers 503 lease_checks_paused."""

    async def route(self, tier: DemoTier) -> Route:
        raise RouteRefused(PAUSED)

    def stream(
        self, upload: Upload, route: Route, *, jurisdiction: Jurisdiction | None, as_of: date | None
    ) -> AsyncIterator[LeaseEvent]:
        raise RouteRefused(PAUSED)

    async def clause(
        self, text: str, route: Route, *, jurisdiction: Jurisdiction, as_of: date | None
    ) -> Finding | None:
        raise RouteRefused(PAUSED)


class ServedPipeline:
    """Lane C's Pipeline, built on the first question rather than at start-up (it asks the
    index which jurisdictions it holds, and an app that never answers, such as the OpenAPI
    export, must not need a database), behind the tier: on the static tier it refuses."""

    def __init__(self, build: Callable[[], AnswerPipeline], router: Router) -> None:
        self._build = build
        self._router = router
        self._pipeline: AnswerPipeline | None = None
        self._lock = asyncio.Lock()

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        try:
            await self._router.route(Kind.QUESTION, tier=question.tier)
        except RouteRefused as exc:
            yield StreamError(message=str(exc), retryable=False)
            return
        if await spent(self._router):
            yield StreamError(message=SPENT, retryable=False)
            return
        async with self._lock:
            if self._pipeline is None:
                self._pipeline = await asyncio.to_thread(self._build)
        async for event in self._pipeline.stream(question):
            yield event


class LawBudget:
    """The long-context path behind a size check: a question whose jurisdictions' whole law
    is over MAX_LAW_TOKENS ends with an error before any model call, instead of a slow,
    costly call that may overflow the context window. The sizes are measured once, when the
    pipeline is built (the law changes only on a new ingest, which restarts nothing yet: a
    larger law is caught by the model's own limit, as before)."""

    def __init__(
        self,
        pipeline: AnswerPipeline,
        chars: Mapping[Jurisdiction, int],
        detect: Callable[[str], list[Jurisdiction]] = detect_jurisdictions,
    ) -> None:
        self.pipeline = pipeline
        self.chars = chars
        self.detect = detect

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        # The pipeline's own rule: named jurisdictions, else detected ones (all, when none).
        asked = question.jurisdictions or self.detect(question.text)
        if sum(self.chars.get(j, 0) for j in asked) > MAX_LAW_TOKENS * CHARS_PER_TOKEN:
            names = ", ".join(j.value.title() for j in asked if j in self.chars)
            yield StreamError(message=TOO_MUCH_LAW.format(names=names), retryable=False)
            return
        async for event in self.pipeline.stream(question):
            yield event


def law_chars(law: LawSource, jurisdictions: Iterable[Jurisdiction]) -> dict[Jurisdiction, int]:
    return {j: sum(len(c.text) for c in law.articles([j], None)) for j in jurisdictions}


def _retrieves(config: EvalConfig) -> bool:
    return not (config.generation.long_context or config.retrieval.mode == "none")


def _build(
    config: EvalConfig,
    retrieval: RetrievalFactory | None,
    sessions: sessionmaker[Session],
    meter: SpendMeter,
) -> AnswerPipeline:
    client = MeteredClient(client_for(MODELS[config.generation.route]), meter)
    if not _retrieves(config):
        law = SqlLawSource(sessions, variant_key(config))
        indexed = law.jurisdictions()
        pipeline = Pipeline(config, law=law, reranker=None, indexed=indexed, client=client)
        return LawBudget(pipeline, law_chars(law, indexed))
    if retrieval is None:  # default_pipeline falls back to LC before this can happen
        raise ValueError(f"{config.name} retrieves and the server has no retrieval")
    parts: Retrieval = retrieval(config)
    indexed = SqlLawSource(sessions, variant_key(config)).jurisdictions()
    return Pipeline(
        config, search=parts.search, reranker=parts.reranker, indexed=indexed, client=client
    )


def sync_sessions(settings: Settings) -> sessionmaker[Session]:
    return make_sync_sessionmaker(make_sync_engine(settings.database_url))
