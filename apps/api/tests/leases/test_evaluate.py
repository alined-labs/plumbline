"""The lease evaluation: each lease checked once, scored against its answer key, pooled."""

import asyncio

from plumbline.corpus.leases import ExpectedLease, load_expected
from plumbline.leases.checker import LeaseCheck
from plumbline.leases.evaluate import evaluate, report
from plumbline.leases.schema import Severity

from .test_scoring import finding

LEASES = {lease.lease_id: lease for lease in load_expected().leases}


def test_every_lease_is_checked_once_and_scored_on_its_own_key() -> None:
    found = {
        "fl-lease-01": [finding("9", "83.47"), finding("10", "83.56"), finding("5", "83.49")],
        "fl-lease-03": [finding("8", "83.56"), finding("4", "83.49", Severity.CHECK)],
    }
    checked: list[str] = []

    async def check(lease: ExpectedLease) -> LeaseCheck:
        checked.append(lease.lease_id)
        return LeaseCheck(findings=found[lease.lease_id], invalid_citations=1, cost_usd=0.25)

    leases = [LEASES["fl-lease-01"], LEASES["fl-lease-03"]]
    result = asyncio.run(evaluate(leases, check))
    assert checked == ["fl-lease-01", "fl-lease-03"]
    first, third = result.scores
    assert (first.caught, first.on_clause, first.planted) == (2, 3, 3)
    assert (third.caught, third.lawful_flagged) == (1, 1)  # clause 4 is the lookalike
    assert (result.pooled["recall"].hits, result.pooled["recall"].total) == (3, 5)
    assert (result.invalid_citations, result.cost_usd) == (2, 0.5)

    table = report(result)
    assert "| fl-lease-01 | 2/3 | 3/3 | 2/3 | 0/1 | 0.67 | 0.67 |" in table
    assert table.splitlines()[-1].startswith("| all | 3/5 = 0.60 [")
