"""What the API answers with (api/answering.py): the stand-ins in dev and test, never in
production; the long-context path until retrieval exists. The whole-law reader itself is
Lane C's (tests/generation/test_lawsource.py)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from plumbline.api import answering
from plumbline.api.answering import (
    LawBudget,
    PausedLeaseChecker,
    ServedPipeline,
    StubRefused,
)
from plumbline.api.app import create_app
from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.api.search import CONFIGS
from plumbline.core.config import load_config
from plumbline.core.stream import Question, StreamError, StreamEvent, TextDelta
from plumbline.core.types import CacheMode, DemoTier, Jurisdiction
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.generation.router import MemorySpendMeter, RouteRefused, SyntheticOnlyRedactor
from plumbline.generation.stub import StubPipeline
from plumbline.settings import Settings


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=0, **values)


def test_only_production_answers_for_real() -> None:
    assert not answering.wants_real(_settings())
    assert not answering.wants_real(_settings(answer_config="A2"))  # as .env.example sets it
    assert answering.wants_real(_settings(environment="prod"))
    app = create_app(_settings())
    assert isinstance(app.state.pipeline, StubPipeline)
    assert isinstance(app.state.lease_checker, StubLeaseChecker)


def test_production_refuses_to_start_on_a_stand_in() -> None:
    prod = _settings(environment="prod")
    with pytest.raises(StubRefused, match="StubPipeline"):
        create_app(prod, pipeline=StubPipeline(delay_ms=0))
    with pytest.raises(StubRefused, match="StubLeaseChecker"):
        create_app(prod, lease_checker=StubLeaseChecker(delay_ms=0))


def test_production_searches_the_index_and_checks_leases() -> None:
    assert answering.default_retrieval(_settings()) is None  # dev and test: the stand-ins
    app = create_app(_settings(environment="prod"))  # builds engines, connects to nothing
    assert app.state.retrieval is not None
    assert isinstance(app.state.pipeline, ServedPipeline)
    assert isinstance(app.state.lease_checker, answering.ClaudeLeaseChecker)


def test_a_server_without_retrieval_pauses_leases() -> None:
    checker = answering.default_lease_checker(
        _settings(environment="prod"), None, MemorySpendMeter()
    )
    assert isinstance(checker, PausedLeaseChecker)
    app = create_app(_settings(environment="prod"), lease_checker=checker)
    with TestClient(app) as client:
        response = client.post(
            "/api/check-lease", content=b"A lease.", headers={"content-type": "text/plain"}
        )
    assert response.status_code == 503
    assert response.json()["code"] == "lease_checks_paused"


def test_a_configuration_that_retrieves_falls_back_to_lc_without_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[str] = []

    def build(config, retrieval, sessions, meter):
        built.append(config.name)

    monkeypatch.setattr(answering, "_build", build)
    pipeline = answering.default_pipeline(
        _settings(environment="prod", answer_config="A2"),
        None,
        make_sync_sessionmaker(make_sync_engine()),
        MemorySpendMeter(),
    )
    assert isinstance(pipeline, ServedPipeline)
    pipeline._build()
    assert built == ["LC-claude"]


class _Fake:
    def __init__(self) -> None:
        self.questions = 0

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        self.questions += 1
        yield TextDelta(text="answered")


async def _collect(pipeline: ServedPipeline, tier: DemoTier) -> list[StreamEvent]:
    question = Question(text="Deposit?", request_id="req_1", tier=tier)
    return [event async for event in pipeline.stream(question)]


@pytest.mark.anyio
async def test_the_served_pipeline_is_built_once_and_refuses_on_the_static_tier() -> None:
    fake = _Fake()
    builds: list[int] = []

    def build() -> _Fake:
        builds.append(1)
        return fake

    meter = MemorySpendMeter()
    pipeline = ServedPipeline(build, answering.router_for(_settings(), meter))
    refused = await _collect(pipeline, DemoTier.STATIC)
    assert len(refused) == 1
    assert isinstance(refused[0], StreamError)
    assert not refused[0].retryable
    assert builds == []  # a refused question builds nothing
    assert await _collect(pipeline, DemoTier.FULL) == [TextDelta(text="answered")]
    assert await _collect(pipeline, DemoTier.FREE) == [TextDelta(text="answered")]
    assert builds == [1]
    assert fake.questions == 2


@pytest.mark.anyio
async def test_the_whole_law_path_refuses_more_law_than_one_answer_reads() -> None:
    fake = _Fake()
    limit = answering.MAX_LAW_TOKENS * answering.CHARS_PER_TOKEN
    chars = {Jurisdiction.FLORIDA: 208_467, Jurisdiction.SPAIN: limit - 100_000}
    budget = LawBudget(fake, chars, detect=lambda text: list(Jurisdiction))

    def ask(*jurisdictions: Jurisdiction) -> Question:
        return Question(text="Deposit?", request_id="req_1", jurisdictions=list(jurisdictions))

    one = [event async for event in budget.stream(ask(Jurisdiction.FLORIDA))]
    assert one == [TextDelta(text="answered")]
    for question in (ask(Jurisdiction.FLORIDA, Jurisdiction.SPAIN), ask()):  # ask(): detected
        events = [event async for event in budget.stream(question)]
        assert len(events) == 1
        assert isinstance(events[0], StreamError)
        assert not events[0].retryable
        assert "Spain, Florida" in events[0].message or "Florida, Spain" in events[0].message
    assert fake.questions == 1  # nothing over the budget reaches the model


def test_the_law_is_measured_per_jurisdiction() -> None:
    class Law:
        def articles(self, jurisdictions: object, as_of: object) -> list[SimpleNamespace]:
            assert as_of is None
            return {
                (Jurisdiction.FLORIDA,): [SimpleNamespace(text="ab"), SimpleNamespace(text="c")]
            }.get(tuple(jurisdictions), [])

    assert answering.law_chars(Law(), [Jurisdiction.FLORIDA, Jurisdiction.DUBAI]) == {
        Jurisdiction.FLORIDA: 3,
        Jurisdiction.DUBAI: 0,
    }


def test_the_lc_configuration_reads_the_whole_law() -> None:
    config = load_config(CONFIGS / "LC.yaml")
    assert not answering._retrieves(config)
    assert answering._retrieves(load_config(CONFIGS / "A2.yaml"))


def test_the_api_serves_the_evaluated_claude_configuration() -> None:
    for name in ("LC", "A2", "A0", "LC-claude"):
        served = answering.served_config(name)
        twin = load_config(CONFIGS / f"{name.removesuffix('-claude')}-claude.yaml")
        assert served.generation.route == "premium"
        # The same hash /evals reports for the row, so the trace names what was measured.
        assert served.config_hash() == twin.config_hash()


def test_a_configuration_with_no_claude_twin_refuses_to_start() -> None:
    with pytest.raises(StubRefused, match="A3 has no configuration"):
        answering.served_config("A3")


@pytest.mark.anyio
async def test_lease_checks_run_on_claude_and_keep_the_tier_rule() -> None:
    meter = MemorySpendMeter()
    checker = answering.ClaudeLeaseChecker(
        router=answering.router_for(_settings(), meter),
        meter=meter,
        redactor=SyntheticOnlyRedactor(),
        search=None,  # type: ignore[arg-type]  # route() never searches
    )
    route = await checker.route(DemoTier.FULL)
    assert (route.name, route.provider) == ("lease", "anthropic")
    assert route.model.startswith("claude-")
    with pytest.raises(RouteRefused):
        await checker.route(DemoTier.FREE)
    await meter.add("gemini", 5.0)  # another provider's spend changes nothing
    assert (await checker.route(DemoTier.FULL)).provider == "anthropic"
    await meter.add("anthropic", 1.0)  # the default cap, spent
    with pytest.raises(RouteRefused, match="budget for live answers is used up"):
        await checker.route(DemoTier.FULL)


@pytest.mark.anyio
async def test_no_live_answer_once_claude_has_spent_its_daily_cap() -> None:
    fake = _Fake()
    meter = MemorySpendMeter()
    pipeline = ServedPipeline(lambda: fake, answering.router_for(_settings(), meter))
    await meter.add("anthropic", 0.99)
    assert await _collect(pipeline, DemoTier.FULL) == [TextDelta(text="answered")]
    await meter.add("anthropic", 0.01)
    [refused] = await _collect(pipeline, DemoTier.FULL)
    assert isinstance(refused, StreamError)
    assert refused.message == answering.SPENT
    assert not refused.retryable
    assert fake.questions == 1
