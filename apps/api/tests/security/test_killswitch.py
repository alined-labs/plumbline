"""The kill switch on fake counters, tiers and days: down the ladder as spend grows, never
up during a day, back up the next UTC day, and a tier set by hand always wins."""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import date, timedelta
from typing import Any

import pytest

from plumbline.api.querylog import recorded
from plumbline.core.stream import Question, StreamEvent
from plumbline.core.types import DemoTier
from plumbline.db import make_engine, make_sessionmaker
from plumbline.generation.llm import LLMRequest, LLMResult, Message, Usage
from plumbline.generation.router import MemorySpendMeter, MeteredClient
from plumbline.security.killswitch import (
    FAILING,
    FREE_AT,
    KillSwitch,
    Lowered,
    SqlAnswerHealth,
    ceiling,
    failing,
)

CAPS = {"gemini": 0.30, "anthropic": 1.00}
DAY = date(2026, 10, 22)


class Tiers:
    def __init__(self, tier: DemoTier = DemoTier.FULL) -> None:
        self.tier = tier
        self.sets: list[DemoTier] = []

    async def current(self) -> DemoTier:
        return self.tier

    async def set(self, tier: DemoTier) -> object:
        self.tier = tier
        self.sets.append(tier)
        return tier


class Marks:
    def __init__(self) -> None:
        self.value: str | None = None

    async def get(self) -> str | None:
        return self.value

    async def put(self, value: str) -> None:
        self.value = value

    async def clear(self) -> None:
        self.value = None


class Clock:
    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self) -> date:
        return self.day


def sync(test: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., None]:
    """Runs an async test body, fixtures and all: the suite has no async plugin."""

    @functools.wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


def rig(tier: DemoTier = DemoTier.FULL) -> tuple[KillSwitch, MemorySpendMeter, Tiers, Clock]:
    clock = Clock(DAY)
    meter = MemorySpendMeter(today=clock)
    tiers = Tiers(tier)
    return KillSwitch(meter, CAPS, tiers, Marks(), today=clock), meter, tiers, clock


@pytest.mark.parametrize(
    ("gemini", "anthropic", "expected"),
    [
        (0.0, 0.0, DemoTier.FULL),
        (FREE_AT * 0.30 - 0.001, FREE_AT * 1.00 - 0.001, DemoTier.FULL),
        (FREE_AT * 0.30, 0.0, DemoTier.FREE),
        (0.0, FREE_AT * 1.00, DemoTier.FREE),
        (0.30, 0.0, DemoTier.STATIC),
        (0.0, 1.00, DemoTier.STATIC),  # the site answers on Claude: its cap stops everything
        (5.0, 5.0, DemoTier.STATIC),
    ],
)
def test_the_ceiling_follows_the_caps(gemini: float, anthropic: float, expected: DemoTier) -> None:
    assert ceiling({"gemini": gemini, "anthropic": anthropic}, CAPS) == expected


def test_a_provider_without_a_cap_is_not_looked_at() -> None:
    assert ceiling({"gemini": 9.0, "anthropic": 9.0}, {"anthropic": 0.0}) == DemoTier.FULL


@sync
async def test_spend_takes_the_tier_down_one_step_then_the_next() -> None:
    switch, meter, tiers, _ = rig()
    assert await switch.check() == DemoTier.FULL
    await meter.add("gemini", 0.25)
    assert await switch.check() == DemoTier.FREE
    await meter.add("gemini", 0.06)
    assert await switch.check() == DemoTier.STATIC
    assert tiers.sets == [DemoTier.FREE, DemoTier.STATIC]


@sync
async def test_the_tier_never_rises_during_the_day() -> None:
    switch, _, tiers, _ = rig(DemoTier.FREE)  # set by hand, under the caps
    assert await switch.check() == DemoTier.FREE
    assert tiers.sets == []


@sync
async def test_a_new_utc_day_restores_the_tier_it_replaced() -> None:
    switch, meter, _, clock = rig()
    await meter.add("gemini", 0.40)
    assert await switch.check() == DemoTier.STATIC
    clock.day += timedelta(days=1)  # the counters start again at zero
    assert await switch.check() == DemoTier.FULL
    assert await switch.marks.get() is None


@sync
async def test_restoring_stops_at_what_todays_spend_allows() -> None:
    switch, meter, _, clock = rig()
    await meter.add("gemini", 0.40)
    await switch.check()
    clock.day += timedelta(days=1)
    await meter.add("anthropic", 0.85)  # past FREE_AT of Anthropic's cap on the new day
    assert await switch.check() == DemoTier.FREE
    raw = await switch.marks.get()
    assert raw is not None
    assert Lowered.load(raw).previous == DemoTier.FULL  # full comes back once it can


@sync
async def test_a_tier_set_by_hand_after_a_lowering_wins() -> None:
    switch, meter, tiers, clock = rig()
    await meter.add("gemini", 0.40)
    await switch.check()  # static
    tiers.tier = DemoTier.FREE  # the human, through the admin route
    clock.day += timedelta(days=1)
    assert await switch.check() == DemoTier.FREE
    assert tiers.sets == [DemoTier.STATIC]


@sync
async def test_a_hand_set_tier_over_the_cap_is_lowered_again() -> None:
    switch, meter, tiers, _ = rig()
    await meter.add("gemini", 0.40)
    await switch.check()
    tiers.tier = DemoTier.FULL  # raised by hand while the cap is spent
    assert await switch.check() == DemoTier.STATIC


class Claude:
    """A live Claude answer that costs what Florida's whole law costs in one call."""

    provider = "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            "Answer.", request.model, Usage(input_tokens=69_257), 0.144, 900, "end_turn", False, "k"
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        yield await self.complete(request)


@sync
async def test_claudes_spend_on_answers_reaches_the_switch() -> None:
    switch, meter, tiers, _ = rig()
    client = MeteredClient(Claude(), meter)  # as api/answering.py wraps the served model
    request = LLMRequest(model="claude", messages=[Message(role="user", content="Q?")])
    for _ in range(6):  # US$0.864: past FREE_AT of the US$1.00 cap
        await client.complete(request)
    assert await switch.check() == DemoTier.FREE
    await client.complete(request)  # US$1.008: the whole cap
    assert await switch.check() == DemoTier.STATIC
    assert tiers.sets == [DemoTier.FREE, DemoTier.STATIC]


ERROR = "BadRequestError in the pipeline"


class Answers:
    def __init__(self, broken: bool = False) -> None:
        self.broken = broken

    async def failing(self) -> bool:
        return self.broken


@pytest.mark.parametrize(
    ("recent", "expected"),
    [
        ([ERROR, ERROR, ERROR], True),
        ([ERROR, ERROR, ERROR, None], True),  # only the latest three count
        ([ERROR, None, ERROR], False),  # one answered: the provider works
        ([ERROR, ERROR], False),  # too few to say
        (["Today's live answers are spent.", ERROR, ERROR], False),  # the API's own refusal
    ],
)
def test_the_live_answers_are_failing_only_after_three_exceptions_in_a_row(
    recent: list[str | None], expected: bool
) -> None:
    assert failing(recent) is expected


@sync
async def test_a_provider_refusing_every_call_takes_the_tier_to_static() -> None:
    clock = Clock(DAY)
    answers = Answers(broken=True)
    tiers = Tiers()
    switch = KillSwitch(MemorySpendMeter(today=clock), CAPS, tiers, Marks(), clock, answers)
    assert await switch.check() == DemoTier.STATIC  # under every cap: the counters see nothing
    answers.broken = False  # no live answers on the static tier, so nothing fails any more
    assert await switch.check() == DemoTier.STATIC  # and it never rises during the day
    clock.day += timedelta(days=1)
    assert await switch.check() == DemoTier.FULL  # the next day tries the live chat again
    assert tiers.sets == [DemoTier.STATIC, DemoTier.FULL]


class Refused(Exception):
    """Stands in for anthropic.BadRequestError: the provider refuses the call."""


async def _refused_answer() -> AsyncIterator[StreamEvent]:
    raise Refused("your API usage limit is reached")
    yield  # an async generator that raises before its first event


@pytest.mark.db
@sync
async def test_the_switch_reads_the_failures_the_query_log_writes(database_url: str) -> None:
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    health = SqlAnswerHealth(sessions)
    try:
        for n in range(FAILING):
            question = Question(text="Deposit?", request_id=f"ks-{uuid.uuid4().hex}-{n}")
            with pytest.raises(Refused):
                async for _ in recorded(_refused_answer(), question, sessions):
                    pass
        assert await health.failing()
        answered = Question(text="Deposit?", request_id=f"ks-{uuid.uuid4().hex}")
        async for _ in recorded(_no_events(), answered, sessions):
            pass
        assert not await health.failing()  # the newest answer did not fail
    finally:
        await engine.dispose()


async def _no_events() -> AsyncIterator[StreamEvent]:
    return
    yield
