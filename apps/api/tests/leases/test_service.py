"""The lease checker as the API runs it: the stand-in's interface, the tier rule, metering."""

import asyncio
import inspect
import json
from datetime import date
from typing import Any

import pytest

from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.core.types import DemoTier, Jurisdiction, Language, Retrieved
from plumbline.generation.llm import STRONG_MODEL, LLMRequest, LLMResult, Usage
from plumbline.generation.router import (
    MemorySpendMeter,
    Router,
    RouteRefused,
    SyntheticOnlyRedactor,
    Upload,
)
from plumbline.leases import extract
from plumbline.leases.checker import LeaseDone, LeaseStage
from plumbline.leases.service import LeaseChecker

LEASE = "RESIDENTIAL LEASE\n\n1. Rent. The Tenant pays rent of $900 a month in Miami, Florida.\n"


class Search:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, question: str, *, k: int, **filters: Any) -> list[Retrieved]:
        self.calls.append(filters)
        return []  # no law found: a clause check then needs no model call


class Model:
    """A live (uncached) client: extraction finds one clause; each call costs $0.003."""

    provider = "gemini"

    async def complete(self, request: LLMRequest) -> LLMResult:
        marks = {
            "language": "en",
            "clauses": [
                {"number": "1", "heading": "Rent", "starts_with": "1. Rent. The Tenant pays"}
            ],
            "ends_before": None,
        }
        assert request.system == extract.SYSTEM
        return LLMResult(json.dumps(marks), request.model, Usage(), 0.003, 5, "STOP", False, "k")

    async def stream(self, request: LLMRequest) -> Any:
        raise NotImplementedError


def checker(meter: MemorySpendMeter, asked: list[str], search: Search) -> LeaseChecker:
    def client_for_model(model: str, **kwargs: Any) -> Model:
        asked.append(model)
        return Model()

    return LeaseChecker(
        router=Router(meter, {"gemini": 1.0}),
        meter=meter,
        redactor=SyntheticOnlyRedactor(),
        search=search,
        client_for_model=client_for_model,
    )


def test_it_has_the_stand_in_s_interface() -> None:
    for method in ("route", "stream"):
        real = inspect.signature(getattr(LeaseChecker, method)).parameters
        stand_in = inspect.signature(getattr(StubLeaseChecker, method)).parameters
        assert list(real) == list(stand_in), method


def test_lease_checks_run_only_on_the_full_tier() -> None:
    service = checker(MemorySpendMeter(), [], Search())
    route = asyncio.run(service.route(DemoTier.FULL))
    assert (route.name, route.model) == ("lease", STRONG_MODEL)
    for tier in (DemoTier.FREE, DemoTier.STATIC):
        with pytest.raises(RouteRefused):
            asyncio.run(service.route(tier))


def test_a_check_runs_on_the_route_s_model_and_counts_its_spend() -> None:
    meter, asked, search = MemorySpendMeter(), [], Search()
    service = checker(meter, asked, search)

    async def run() -> list[Any]:
        route = await service.route(DemoTier.FULL)
        upload = Upload(text=LEASE, language=Language.EN, synthetic=True)
        events = service.stream(upload, route, jurisdiction=None, as_of=date(2026, 3, 1))
        return [event async for event in events]

    events = asyncio.run(run())
    assert asked == [STRONG_MODEL]
    assert [e.stage for e in events if isinstance(e, LeaseStage)] == [
        "redacting",
        "reading",
        "checking",
        "checking",
    ]
    assert events[-1] == LeaseDone(findings=0, language=Language.EN)
    assert search.calls == [{"jurisdictions": [Jurisdiction.FLORIDA], "as_of": date(2026, 3, 1)}]
    assert asyncio.run(meter.spent_today("gemini")) == pytest.approx(0.003)  # the extraction
