"""The synthetic leases in data/leases/ and what a lease checker must find in them: the lease
checker's test, and the leases the golden set's lease-check items read.

Each lease is a Markdown file, `<lease_id>.md`, whose clauses are its `## Clause <n>. <title>`
sections. `expected_findings.json` lists, per lease, every planted clause that conflicts
with a statute (a finding the checker must report) and the clauses that look suspect but
are lawful (which it must not report), each with the article that decides it and the
date the lease was signed, because the law that applies is the law in force on that date.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from plumbline.core.types import ArticleRef, Jurisdiction
from plumbline.settings import ROOT

LEASES = ROOT / "data" / "leases"
EXPECTED = LEASES / "expected_findings.json"
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=80)]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
CLAUSE = re.compile(r"^## Clause (\d+)\. ", re.MULTILINE)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Finding(Frozen):
    """A planted clause that conflicts with a statute: the checker must report it."""

    clause: NonEmpty  # the clause's number, as the lease writes it: "7"
    quote: NonEmpty  # the offending words, verbatim from that clause
    issue: NonEmpty  # what is wrong with it, in one plain-English sentence
    violates: ArticleRef  # the article it conflicts with, pinned to a manifest edition


class Lawful(Frozen):
    """A clause that looks suspect but is lawful: the checker must not report it."""

    clause: NonEmpty
    quote: NonEmpty
    why: NonEmpty
    allowed_by: ArticleRef


class ExpectedLease(Frozen):
    lease_id: Slug  # the file data/leases/<lease_id>.md
    jurisdiction: Jurisdiction
    signed_on: date  # the law that applies is the law in force on this date
    findings: list[Finding] = Field(min_length=1)
    lawful: list[Lawful] = Field(default_factory=list)


class ExpectedFindings(Frozen):
    version: Literal[1] = 1
    leases: list[ExpectedLease]


def load_expected(path: Path = EXPECTED) -> ExpectedFindings:
    return ExpectedFindings.model_validate(json.loads(path.read_text(encoding="utf-8")))


def clauses(markdown: str) -> dict[str, str]:
    """A lease's clauses by number: each `## Clause <n>.` section, through the line before
    the next `## ` heading."""
    sections = re.split(r"^(?=## )", markdown, flags=re.MULTILINE)
    found = {}
    for section in sections:
        heading = CLAUSE.match(section)
        if heading:
            found[heading.group(1)] = section
    return found


def squeeze(text: str) -> str:
    """Whitespace collapsed, so a quote matches a clause however its lines are wrapped."""
    return " ".join(text.split())
