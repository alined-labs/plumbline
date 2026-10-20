"""The stand-in lease checker: the events it yields, that it ignores the lease, and the tier
rule it applies (Lane C's Router)."""

from __future__ import annotations

import pytest

from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.core.types import DemoTier, Language
from plumbline.generation.router import Route, RouteRefused, Upload
from plumbline.leases.checker import LeaseDone, LeaseEvent, LeaseStage
from plumbline.leases.schema import Finding, Severity

pytestmark = pytest.mark.anyio


async def _events(text: str, route: Route) -> list[LeaseEvent]:
    upload = Upload(text=text, language=Language.EN)
    stub = StubLeaseChecker(delay_ms=0)
    return [e async for e in stub.stream(upload, route, jurisdiction=None, as_of=None)]


async def test_it_yields_the_stages_a_finding_of_each_severity_and_the_end() -> None:
    route = await StubLeaseChecker(delay_ms=0).route(DemoTier.FULL)
    events = await _events("Clause 1. The tenant pays the rent.", route)
    stages = [e for e in events if isinstance(e, LeaseStage)]
    findings = [e for e in events if isinstance(e, Finding)]
    assert [s.stage for s in stages[:2]] == ["redacting", "reading"]
    assert stages[2:] == [LeaseStage("checking", done=n, total=4) for n in range(5)]
    assert [f.n for f in findings] == [1, 2, 3, 4]
    assert {f.severity for f in findings} == set(Severity)
    assert events[-1] == LeaseDone(findings=4, language=Language.EN)
    # A finding arrives before the count that includes it.
    assert events.index(findings[0]) < events.index(LeaseStage("checking", done=1, total=4))


async def test_it_does_not_read_the_lease() -> None:
    route = await StubLeaseChecker(delay_ms=0).route(DemoTier.FULL)
    assert await _events("one lease", route) == await _events("another lease entirely", route)


async def test_its_findings_say_that_nothing_in_them_is_legal_information() -> None:
    route = await StubLeaseChecker(delay_ms=0).route(DemoTier.FULL)
    findings = [e for e in await _events("x", route) if isinstance(e, Finding)]
    assert all("nothing here is legal information" in f.why for f in findings)
    assert all(c.label == "Stub Act, s. 1" for f in findings for c in f.citations)


@pytest.mark.parametrize("tier", [DemoTier.FREE, DemoTier.STATIC])
async def test_only_the_full_tier_runs_lease_checks(tier: DemoTier) -> None:
    with pytest.raises(RouteRefused):
        await StubLeaseChecker(delay_ms=0).route(tier)
