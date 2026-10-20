"""Clause extraction: placing the model's marks in the lease, and one recorded run."""

import asyncio
from pathlib import Path
from typing import Any, Final

from hypothesis import given
from hypothesis import strategies as st

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode, Language
from plumbline.generation.llm import STRONG_MODEL as LEASE_MODEL
from plumbline.generation.llm import LLMRequest, LLMResult, Usage, client_for
from plumbline.leases.extract import ClauseMark, ClauseMarks, cut, extract_clauses
from plumbline.settings import ROOT

# An invented lease: every name, address and amount in it is fictitious.
LEASE: Final = (Path(__file__).parent / "data" / "invented_lease.txt").read_text(encoding="utf-8")
NUMBERS: Final = ["1", "2", "3", "3.1", "3.2", "4", "5", "6"]


def mark(number: str, starts_with: str) -> ClauseMark:
    return ClauseMark(number=number, heading=None, starts_with=starts_with)


def marks(*items: ClauseMark, ends_before: str | None = "SIGNATURES Landlord: ____") -> ClauseMarks:
    return ClauseMarks(language="en", clauses=list(items), ends_before=ends_before)


def test_clauses_are_cut_at_their_starts_in_the_lease_s_own_words() -> None:
    clauses, dropped = cut(
        LEASE,
        marks(
            mark("3.1", "3.1 The Tenant shall pay a security deposit"),
            mark("3.2", "3.2  the landlord WILL return the deposit"),  # case and spaces
            mark("4", "4. Repairs. The Tenant is responsible"),
        ),
    )
    assert dropped == 0
    assert [c.number for c in clauses] == ["3.1", "3.2", "4"]
    assert (
        clauses[1].text
        == "3.2 The Landlord will return the deposit within 60 days after the end of this Lease."
    )
    # Clauses 5 and 6 were not marked, so clause 4 runs on to the signatures.
    assert "5. Entry." in clauses[2].text
    assert clauses[2].text.endswith("fifth day of the month.")


def test_unfound_or_out_of_order_starts_are_dropped_and_the_end_is_kept() -> None:
    clauses, dropped = cut(
        LEASE,
        marks(
            mark("2", "2. Rent. The Tenant shall pay"),
            mark("1", "1. Term. The term of"),  # before the previous start
            mark("9", "9. Pets. No pets are allowed"),  # not in the lease
            mark("6", "6. Late Fees. A late fee"),
            mark("7", "7. Tiny"),  # too short to place
        ),
    )
    assert dropped == 3
    assert [c.number for c in clauses] == ["2", "6"]
    one_word_end, _ = cut(
        LEASE, marks(mark("6", "6. Late Fees. A late fee"), ends_before="SIGNATURES")
    )
    assert one_word_end[0].text.endswith("fifth day of the month.")
    assert clauses[1].text.endswith("fifth day of the month.")  # cut before the signatures
    assert all(c.language is Language.EN for c in clauses)


STARTS: Final = [  # three words each, as the model is asked for more
    "1. Term. The",
    "2. Rent. The",
    "3. Security Deposit.",
    "3.1 The Tenant",
    "3.2 The Landlord",
    "4. Repairs. The",
    "5. Entry. The",
    "6. Late Fees.",
]


@given(st.lists(st.sampled_from(range(len(NUMBERS))), unique=True))
def test_any_marked_clauses_are_the_lease_s_text_in_order(picked: list[int]) -> None:
    chosen = sorted(picked)
    clauses, dropped = cut(LEASE, marks(*(mark(NUMBERS[i], STARTS[i]) for i in chosen)))
    assert dropped == 0
    assert [c.number for c in clauses] == [NUMBERS[i] for i in chosen]
    assert all(c.text in LEASE for c in clauses)
    positions = [LEASE.index(c.text) for c in clauses]
    assert positions == sorted(positions)
    ends = [p + len(c.text) for p, c in zip(positions, clauses, strict=True)]
    assert all(end <= start for end, start in zip(ends, positions[1:], strict=False))


class Model:
    provider = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        return LLMResult(self.reply, request.model, Usage(), 0.001, 5, "STOP", True, "k")

    async def stream(self, request: LLMRequest) -> Any:
        raise NotImplementedError


def test_the_model_marks_and_the_code_cuts() -> None:
    reply = marks(mark("5", "5. Entry. The Landlord may enter")).model_dump_json()
    model = Model(reply)
    extraction = asyncio.run(extract_clauses(LEASE, model))
    assert [c.number for c in extraction.clauses] == ["5"]
    assert (extraction.dropped, extraction.cost_usd, extraction.cached) == (0, 0.001, True)
    request = model.requests[0]
    assert (request.model, request.json_schema is not None) == (LEASE_MODEL, True)
    assert request.messages[0].content.startswith("<lease>\nRESIDENTIAL LEASE AGREEMENT")


def recorded(mode: CacheMode) -> Any:
    """The lease route's model through cache/; recorded by running this file."""
    client = client_for(LEASE_MODEL, cache=ResponseCache(mode, ROOT / "cache"))
    return asyncio.run(extract_clauses(LEASE, client))


def test_a_recorded_extraction_finds_every_clause() -> None:
    extraction = recorded(CacheMode.REPLAY)
    assert [c.number for c in extraction.clauses] == NUMBERS
    assert extraction.dropped == 0
    assert extraction.clauses[4].text.startswith("3.2 The Landlord will return the deposit")
    assert extraction.clauses[-1].text.endswith("fifth day of the month.")


if __name__ == "__main__":
    extraction = recorded(CacheMode.RECORD)
    for clause in extraction.clauses:
        print(clause.number, "|", clause.heading, "|", clause.text[:70].replace("\n", " "))
    print("dropped", extraction.dropped, "cost", extraction.cost_usd)
