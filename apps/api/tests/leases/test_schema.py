"""The Finding contract: what the lease page can rely on."""

from typing import Any

import pytest
from pydantic import ValidationError

from plumbline.core.types import ArticleRef, Citation, Jurisdiction, Language
from plumbline.leases.schema import Finding, Severity

CITATION = Citation(
    n=1,
    chunk_id="fl-83.49-3-a",
    ref=ArticleRef(
        jurisdiction=Jurisdiction.FLORIDA, law="fl-stat-83", article="83.49", edition="2026"
    ),
    label="Fla. Stat. § 83.49(3)(a)",
    quote="the landlord must return the security deposit, together with interest if otherwise required, within 15 days",
    language=Language.EN,
    verified=True,
)
FINDING: dict[str, Any] = {
    "n": 1,
    "clause_number": "7.2",
    "clause_text": "The Landlord will return the deposit within 60 days of the end of the lease.",
    "clause_language": "en",
    "severity": "conflict",
    "title": "The deposit comes back later than the law allows",
    "why": (
        "The clause gives the landlord 60 days to return the deposit. Florida law sets 15 "
        "days when the landlord makes no claim on it, and the statute prevails over the lease."
    ),
    "citations": [CITATION.model_dump(mode="json")],
    "confidence": 0.9,
}


def test_a_finding_carries_the_clause_the_law_and_a_confidence() -> None:
    finding = Finding.model_validate(FINDING)
    assert finding.severity is Severity.CONFLICT
    assert finding.citations[0].verified
    # The lease page's four groups, in its order.
    assert [s.value for s in Severity] == ["conflict", "check", "note", "match"]
    assert "score" not in Finding.model_json_schema()["properties"]  # never a whole-lease score


@pytest.mark.parametrize(
    "change",
    [
        {"citations": []},  # a finding rests on the law
        {"severity": "illegal"},
        {"confidence": 1.2},
        {"title": "x" * 121},  # one line
        {"clause_number": "  "},
        {"advice": "Refuse to sign."},  # nothing beyond the contract
    ],
)
def test_a_finding_outside_the_contract_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(FINDING | change)
