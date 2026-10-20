"""The lease checker's output: one Finding per clause worth a reader's attention.

This is the contract the lease page builds on: Lane D's /api/check-lease streams each
Finding as a `finding` event, and the front end renders it as a FindingCard. A finding
is about one clause, as the lease numbers and words it, and rests on the articles it
cites, as verified citations like an answer's. The checker never scores a whole lease:
a lease is not more or less legal, its clauses are.

It is legal information about what a clause says against what the cited law says, never
advice on what the reader should do.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints

from plumbline.core.types import Citation, Frozen, Language

NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class Severity(StrEnum):
    """The four groups the lease page shows, most pressing first."""

    CONFLICT = "conflict"  # the clause contradicts the cited law, which prevails over it
    CHECK = "check"  # it may conflict, depending on facts the lease does not state
    NOTE = "note"  # the cited law adds a right or a duty the clause leaves out
    MATCH = "match"  # the clause follows the cited law


class Finding(Frozen):
    n: int = Field(ge=1)  # the finding's number in this check, in clause order
    clause_number: NonEmpty  # as the lease numbers it: "7", "7.2", "Schedule A, 3"
    clause_text: NonEmpty  # the clause as written in the lease, after redaction
    clause_language: Language
    severity: Severity
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]  # one line
    why: NonEmpty  # two or three sentences: what the clause says, and what the law says
    citations: list[Citation] = Field(min_length=1)  # every finding rests on the law
    confidence: float = Field(ge=0, le=1)
