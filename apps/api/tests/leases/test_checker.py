"""The lease checker end to end: events in order, the failures, and one recorded lease."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Final

import pytest

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode, Chunk, Jurisdiction, Language, Retrieved
from plumbline.generation.llm import STRONG_MODEL, LLMRequest, LLMResult, Usage, client_for
from plumbline.generation.router import SyntheticOnlyRedactor, Upload
from plumbline.leases import extract
from plumbline.leases.checker import (
    LeaseCheckError,
    LeaseDone,
    LeaseStage,
    check_lease,
    stream_check,
)
from plumbline.leases.schema import Finding, Severity
from plumbline.settings import ROOT

LEASE: Final = (Path(__file__).parent / "data" / "invented_lease.txt").read_text(encoding="utf-8")
# Verbatim from The 2026 Florida Statutes, read on 2026-10-19.
RETURN: Final = (
    "Upon the vacating of the premises for termination of the rental agreement, if the "
    "landlord does not intend to impose a claim on the security deposit, the landlord must "
    "return the security deposit, together with interest if otherwise required, within 15 "
    "days after the termination of the rental agreement."
)
ENTRY: Final = (
    "The landlord may enter the dwelling unit at any time for the protection or "
    "preservation of the premises. The landlord may enter the dwelling unit upon reasonable "
    "notice to the tenant and at a reasonable time for the purpose of repair of the "
    "premises. “Reasonable notice” for the purpose of repair is notice given at least 24 "
    "hours prior to the entry, and reasonable time for the purpose of repair shall be "
    "between the hours of 7:30 a.m. and 8:00 p.m."
)


def chunk(id: str, article: str, label: str, text: str) -> Chunk:
    return Chunk(
        id=id,
        document_id="fl-stat-83",
        jurisdiction=Jurisdiction.FLORIDA,
        law="fl-stat-83",
        language=Language.EN,
        edition="2026",
        article=article,
        label=label,
        text=text,
        text_for_search=text,
    )


HITS: Final = [
    Retrieved(
        chunk=chunk("fl-83.49-3-a", "83.49", "Fla. Stat. § 83.49(3)(a)", RETURN), rank=1, score=0.9
    ),
    Retrieved(
        chunk=chunk("fl-83.53-2", "83.53", "Fla. Stat. § 83.53(2)", ENTRY), rank=2, score=0.8
    ),
]


class Search:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, question: str, *, k: int, **filters: Any) -> list[Retrieved]:
        self.calls.append({"k": k, **filters})
        return HITS[:k]


MARKS: Final = {
    "language": "en",
    "clauses": [
        {"number": "2", "heading": "Rent", "starts_with": "2. Rent. The Tenant shall pay"},
        {
            "number": "3.2",
            "heading": None,
            "starts_with": "3.2 The Landlord will return the deposit",
        },
        {"number": "5", "heading": "Entry", "starts_with": "5. Entry. The Landlord may enter"},
    ],
    "ends_before": "SIGNATURES",
}


class Model:
    """Marks three clauses, and finds a conflict only in the 60-day deposit clause."""

    provider = "fake"

    def __init__(self, marks: dict[str, Any] = MARKS, slow: float = 0.0) -> None:
        self.marks = marks
        self.slow = slow
        self.requests: list[LLMRequest] = []
        self.cancelled = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if request.system == extract.SYSTEM:
            return self.result(request, json.dumps(self.marks))
        clause = request.messages[0].content
        if "60 days" not in clause:
            try:
                await asyncio.sleep(self.slow)
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            reply = {
                "relevant": False,
                "severity": "match",
                "title": "",
                "why": "",
                "citations": [],
                "confidence": 0,
            }
        else:
            reply = {
                "relevant": True,
                "severity": "conflict",
                "title": "The deposit comes back later than the law allows",
                "why": "The clause allows 60 days; the law sets 15 when no claim is made [1].",
                "citations": [
                    {
                        "n": 1,
                        "chunk_id": "fl-83.49-3-a",
                        "quote": "the landlord must return the security deposit",
                        "gloss": None,
                    }
                ],
                "confidence": 0.9,
            }
        return self.result(request, json.dumps(reply))

    def result(self, request: LLMRequest, text: str) -> LLMResult:
        return LLMResult(text, request.model, Usage(), 0.001, 5, "STOP", True, "k")

    async def stream(self, request: LLMRequest) -> Any:
        raise NotImplementedError


def synthetic(text: str = LEASE) -> Upload:
    return Upload(text=text, language=Language.EN, synthetic=True)


def run(upload: Upload, model: Any, **kw: Any) -> list[Any]:
    async def collect() -> list[Any]:
        events = stream_check(
            upload, redactor=SyntheticOnlyRedactor(), search=Search(), client=model, **kw
        )
        return [event async for event in events]

    return asyncio.run(collect())


def test_events_follow_the_stream_and_findings_come_in_clause_order() -> None:
    events = run(synthetic(), Model())
    kinds = [
        type(e).__name__ if not isinstance(e, LeaseStage) else f"{e.stage}:{e.done}/{e.total}"
        for e in events
    ]
    assert kinds == [
        "redacting:None/None",
        "reading:None/None",
        "checking:0/3",
        "checking:1/3",  # 2. Rent: nothing to say
        "Finding",  # 3.2: the deposit clause
        "checking:2/3",
        "checking:3/3",  # 5. Entry: nothing in this fake
        "LeaseDone",
    ]
    finding = events[4]
    assert isinstance(finding, Finding)
    assert (finding.n, finding.clause_number, finding.severity) == (1, "3.2", Severity.CONFLICT)
    assert events[-1] == LeaseDone(findings=1, language=Language.EN)


def test_the_jurisdiction_is_the_one_the_lease_names_or_the_caller_s() -> None:
    search = Search()

    async def first_search() -> None:
        events = stream_check(
            synthetic(), redactor=SyntheticOnlyRedactor(), search=search, client=Model()
        )
        async for _ in events:
            pass

    asyncio.run(first_search())
    assert search.calls[0]["jurisdictions"] == [
        Jurisdiction.FLORIDA
    ]  # the lease says Miami, Florida
    unnamed = synthetic(LEASE.replace("Miami,\nFlorida", "Springfield"))
    with pytest.raises(LeaseCheckError) as raised:
        run(unnamed, Model())
    assert raised.value.code == "jurisdiction_unknown"
    assert run(unnamed, Model(), jurisdiction=Jurisdiction.FLORIDA)[-1].findings == 1


@pytest.mark.parametrize(
    ("upload", "marks", "code"),
    [
        (Upload(text=LEASE, language=Language.EN), MARKS, "redaction_refused"),  # not synthetic
        (synthetic(), MARKS | {"clauses": []}, "no_clauses"),
    ],
)
def test_failures_carry_a_stable_code(upload: Upload, marks: dict[str, Any], code: str) -> None:
    model = Model(marks)
    with pytest.raises(LeaseCheckError) as raised:
        run(upload, model)
    assert raised.value.code == code
    if code == "redaction_refused":
        assert model.requests == []  # no model saw the lease


def test_a_reader_who_leaves_stops_the_checks_still_running() -> None:
    model = Model(slow=5.0)

    async def leave_while_checking() -> int:
        events = stream_check(
            synthetic(), redactor=SyntheticOnlyRedactor(), search=Search(), client=model
        )
        async for event in events:
            if isinstance(event, LeaseStage) and event.stage == "checking":
                break
        await asyncio.sleep(0.05)  # the checks start, and two block on the slow model
        await events.aclose()
        await asyncio.sleep(0)  # the cancellations land
        return model.cancelled  # counted here, before asyncio.run cancels anything itself

    started = time.perf_counter()
    assert asyncio.run(leave_while_checking()) == 2  # the two slow clause checks
    assert time.perf_counter() - started < 1.0


def test_check_lease_collects_the_totals() -> None:
    totals = asyncio.run(
        check_lease(synthetic(), redactor=SyntheticOnlyRedactor(), search=Search(), client=Model())
    )
    assert (totals.jurisdiction, totals.clauses, totals.dropped, len(totals.findings)) == (
        Jurisdiction.FLORIDA,
        3,
        0,
        1,
    )
    assert totals.cost_usd == pytest.approx(0.004)  # one extraction and three checks


def recorded(mode: CacheMode) -> Any:
    """The lease route through cache/, over the invented lease; recorded by running this file."""
    client = client_for(STRONG_MODEL, cache=ResponseCache(mode, ROOT / "cache"))
    return asyncio.run(
        check_lease(synthetic(), redactor=SyntheticOnlyRedactor(), search=Search(), client=client)
    )


def test_a_recorded_lease_check_finds_the_two_planted_conflicts() -> None:
    totals = recorded(CacheMode.REPLAY)
    assert totals.clauses == 8
    conflicts = {f.clause_number: f for f in totals.findings if f.severity is Severity.CONFLICT}
    assert set(conflicts) == {"3.2", "5"}
    assert {c.ref.article for c in conflicts["3.2"].citations} == {"83.49"}
    assert {c.ref.article for c in conflicts["5"].citations} == {"83.53"}
    assert [f.n for f in totals.findings] == list(range(1, len(totals.findings) + 1))


if __name__ == "__main__":
    totals = recorded(CacheMode.RECORD)
    print("clauses", totals.clauses, "dropped", totals.dropped, "cost", round(totals.cost_usd, 5))
    for f in totals.findings:
        print(
            f.n,
            f.clause_number,
            f.severity.value,
            "|",
            f.title,
            "|",
            [c.label for c in f.citations],
            f.confidence,
        )
