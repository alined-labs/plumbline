"""The lease checker: an uploaded lease in, findings out, as a stream of events.

    redact -> which law governs it -> extract the clauses -> check each clause -> done

Redaction comes first and runs once: no model sees any of the lease before it. The
governing jurisdiction is the caller's, or the one the lease names (Lane A's detector, run
locally on the original text, since redaction may hide place names); a lease that names
none, or several, is not guessed at. Clauses are checked several at a
time, but findings are yielded in clause order and numbered as they go, so a reader sees
the first clauses' findings while the last are still being checked.

The events are the ones /api/check-lease streams: a stage (with clause counts while
checking), each Finding, and done; a failure raises LeaseCheckError with a stable code.
It is legal information about clauses, never advice, and there is no whole-lease score.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

from plumbline.core.types import Jurisdiction, Language
from plumbline.generation.llm import STRONG_MODEL, LLMClient
from plumbline.generation.pipeline import ChunkSearch
from plumbline.generation.router import RedactionRefused, Redactor, Upload
from plumbline.leases.check import ClauseCheck, check_clause
from plumbline.leases.extract import extract_clauses
from plumbline.leases.schema import Finding
from plumbline.retrieval.jurisdiction import detect

FailureCode = Literal["redaction_refused", "jurisdiction_unknown", "no_clauses"]
MESSAGES: Final[dict[FailureCode, str]] = {
    "redaction_refused": "This lease can't be checked until uploads can be redacted.",
    "jurisdiction_unknown": "We couldn't tell which jurisdiction's law governs this lease.",
    "no_clauses": "We couldn't find numbered clauses in this lease.",
}


class LeaseCheckError(Exception):
    def __init__(self, code: FailureCode) -> None:
        super().__init__(MESSAGES[code])
        self.code = code


@dataclass(frozen=True)
class LeaseStage:
    stage: Literal["redacting", "reading", "checking"]
    done: int | None = None  # clauses checked so far, while checking
    total: int | None = None


@dataclass(frozen=True)
class LeaseDone:
    findings: int
    language: Language


LeaseEvent = LeaseStage | Finding | LeaseDone


@dataclass
class LeaseCheck:
    """A whole check, collected: what the evaluation scores."""

    jurisdiction: Jurisdiction | None = None  # known once the lease is read
    language: Language = Language.EN
    findings: list[Finding] = field(default_factory=list)
    clauses: int = 0
    dropped: int = 0  # clause starts the extraction could not place
    invalid_citations: int = 0
    cost_usd: float = 0.0


async def stream_check(
    upload: Upload,
    *,
    redactor: Redactor,
    search: ChunkSearch,
    client: LLMClient,
    jurisdiction: Jurisdiction | None = None,  # None: the one the lease names
    as_of: date | None = None,  # the law in force on this date (a lease's signing date)
    model: str = STRONG_MODEL,
    concurrency: int = 4,
    totals: LeaseCheck | None = None,  # filled in as the check runs, when given
) -> AsyncIterator[LeaseEvent]:
    yield LeaseStage("redacting")
    try:
        text = redactor.redact(upload)
    except RedactionRefused as exc:
        raise LeaseCheckError("redaction_refused") from exc
    # Read on the original text: redaction may replace place names ("Miami, Florida") with
    # placeholders, and this is local pattern matching, not a model call, so nothing of
    # the lease leaves the machine before redaction either way.
    governing = jurisdiction or _named(upload.text)
    yield LeaseStage("reading")
    extraction = await extract_clauses(text, client, model)
    clauses = extraction.clauses
    if not clauses:
        raise LeaseCheckError("no_clauses")
    language = clauses[0].language
    if totals is not None:
        totals.jurisdiction, totals.language = governing, language
        totals.clauses, totals.dropped = len(clauses), extraction.dropped
        totals.cost_usd += extraction.cost_usd
    limit = asyncio.Semaphore(concurrency)

    async def check(number: str, clause_text: str) -> ClauseCheck:
        async with limit:
            return await check_clause(
                number,
                clause_text,
                language,
                jurisdiction=governing,
                search=search,
                client=client,
                as_of=as_of,
                model=model,
            )

    tasks = [asyncio.create_task(check(c.number, c.text)) for c in clauses]
    found = 0
    try:
        yield LeaseStage("checking", done=0, total=len(clauses))
        for done, task in enumerate(tasks, start=1):
            result = await task
            if totals is not None:
                totals.invalid_citations += result.invalid_citations
                totals.cost_usd += result.cost_usd
            if result.finding is not None:
                found += 1
                finding = result.finding.model_copy(update={"n": found})
                if totals is not None:
                    totals.findings.append(finding)
                yield finding
            yield LeaseStage("checking", done=done, total=len(clauses))
    finally:
        for task in tasks:  # a reader who leaves early stops the checks still running
            task.cancel()
    yield LeaseDone(findings=found, language=language)


async def check_lease(
    upload: Upload,
    *,
    redactor: Redactor,
    search: ChunkSearch,
    client: LLMClient,
    jurisdiction: Jurisdiction | None = None,
    as_of: date | None = None,
    model: str = STRONG_MODEL,
    concurrency: int = 4,
) -> LeaseCheck:
    """The whole check at once, for the evaluation."""
    totals = LeaseCheck()
    events = stream_check(
        upload,
        redactor=redactor,
        search=search,
        client=client,
        jurisdiction=jurisdiction,
        as_of=as_of,
        model=model,
        concurrency=concurrency,
        totals=totals,
    )
    async for _ in events:
        pass
    return totals


def _named(text: str) -> Jurisdiction:
    named = detect(text)
    if len(named) != 1:  # none named (the detector then answers all four), or several
        raise LeaseCheckError("jurisdiction_unknown")
    return named[0]
