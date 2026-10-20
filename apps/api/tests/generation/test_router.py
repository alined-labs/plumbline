"""The router, the spend meters and the redaction stand-in."""

import asyncio
import secrets
from collections.abc import AsyncIterator
from datetime import date

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from plumbline.core.types import DemoTier, Jurisdiction, Language
from plumbline.generation.llm import LLMRequest, LLMResult, Message, Usage
from plumbline.generation.router import (
    ROUTES,
    Kind,
    MemorySpendMeter,
    MeteredClient,
    RedactionRefused,
    RedisSpendMeter,
    Router,
    RouteRefused,
    SyntheticOnlyRedactor,
    Upload,
)
from plumbline.settings import Settings

FULL, FREE, STATIC = DemoTier.FULL, DemoTier.FREE, DemoTier.STATIC
CAPS = {"gemini": 1.0, "anthropic": 0.5}


def route(meter: MemorySpendMeter | None = None, kind: Kind = Kind.QUESTION, **kw: object) -> str:
    router = Router(meter or MemorySpendMeter(), CAPS)
    return asyncio.run(router.route(kind, **kw)).name  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "jurisdictions", "expected"),
    [
        ("How long does my landlord have to return my deposit?", [], "fast"),
        (
            "What deposit can a landlord ask for?",
            [Jurisdiction.SPAIN, Jurisdiction.FLORIDA],
            "strong",
        ),
        ("Compare deposit rules in Spain and Colombia.", [], "strong"),
        ("Who pays for repairs? And can I withhold rent?", [], "strong"),
    ],
)
def test_questions_go_fast_unless_they_compare_or_chain(
    text: str, jurisdictions: list[Jurisdiction], expected: str
) -> None:
    assert route(tier=FULL, text=text, jurisdictions=jurisdictions) == expected


def test_premium_needs_the_full_tier_and_room_under_the_cap() -> None:
    meter = MemorySpendMeter()
    assert route(meter, tier=FULL, premium=True) == "premium"
    assert route(meter, tier=FREE, premium=True) == "fast"
    asyncio.run(meter.add("anthropic", 0.5))
    assert route(meter, tier=FULL, premium=True) == "fast"
    assert route(meter, tier=FULL, premium=True, text="Spain versus Florida?") == "strong"


def test_lease_checks_run_only_on_the_full_tier() -> None:
    assert route(kind=Kind.LEASE_CHECK, tier=FULL) == "lease"
    assert ROUTES["lease"].provider == "gemini"
    with pytest.raises(RouteRefused, match="do not train on what you upload"):
        route(kind=Kind.LEASE_CHECK, tier=FREE)


def test_the_static_tier_calls_no_model() -> None:
    for kind in Kind:
        with pytest.raises(RouteRefused, match="stored answers"):
            route(kind=kind, tier=STATIC)


def test_spend_is_per_provider_and_day() -> None:
    day = [date(2026, 10, 19)]
    meter = MemorySpendMeter(today=lambda: day[0])
    asyncio.run(meter.add("gemini", 0.25))
    assert asyncio.run(meter.add("gemini", 0.5)) == 0.75
    assert asyncio.run(meter.spent_today("anthropic")) == 0.0
    day[0] = date(2026, 10, 20)
    assert asyncio.run(meter.spent_today("gemini")) == 0.0


class Model:
    provider = "anthropic"

    def __init__(self, cached: bool) -> None:
        self.cached = cached

    def result(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            "ok", request.model, Usage(output_tokens=1), 0.02, 5, "end_turn", self.cached, "k"
        )

    async def complete(self, request: LLMRequest) -> LLMResult:
        return self.result(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        yield "ok"
        yield self.result(request)


def test_only_live_calls_are_counted() -> None:
    request = LLMRequest(model="claude-sonnet-5-5", messages=[Message(role="user", content="hi")])
    meter = MemorySpendMeter()

    async def calls() -> None:
        await MeteredClient(Model(cached=False), meter).complete(request)
        _ = [item async for item in MeteredClient(Model(cached=False), meter).stream(request)]
        await MeteredClient(Model(cached=True), meter).complete(request)

    asyncio.run(calls())
    assert asyncio.run(meter.spent_today("anthropic")) == pytest.approx(0.04)


def test_the_redis_meter_counts_and_expires() -> None:
    async def run() -> tuple[float, float, int]:
        redis = Redis.from_url(Settings(_env_file=None).redis_url, socket_connect_timeout=1)
        meter = RedisSpendMeter(redis, prefix=f"test-spend-{secrets.token_hex(4)}")
        try:
            await meter.add("gemini", 0.25)
            total = await meter.add("gemini", 0.5)
            ttl = await redis.ttl(meter._key("gemini", meter.today()))
            return total, await meter.spent_today("gemini"), ttl
        finally:
            await redis.delete(meter._key("gemini", meter.today()))
            await redis.aclose()

    try:
        total, spent, ttl = asyncio.run(run())
    except (RedisConnectionError, OSError):
        pytest.skip("Redis is unreachable (make up starts it)")
    assert total == spent == 0.75
    assert 86_400 < ttl <= 2 * 86_400


def test_the_stand_in_redactor_refuses_real_uploads() -> None:
    redactor = SyntheticOnlyRedactor()
    lease = "This lease is between a synthetic landlord and a synthetic tenant."
    assert redactor.redact(Upload(text=lease, language=Language.EN, synthetic=True)) == lease
    with pytest.raises(RedactionRefused):
        redactor.redact(Upload(text=lease, language=Language.EN))
