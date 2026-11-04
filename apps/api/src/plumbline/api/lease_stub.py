"""The lease check's stand-in until retrieval and the redactor are wired in: it ignores the
lease, takes as long as a short one, and finds one clause of each severity, all citing the
same invented "Stub Act" the answer stub cites. The front end builds every state of the
lease page against it, and the tier rule is the real one (Lane C's Router).

Nothing here is legal information, and the findings say so.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from typing import Final

from plumbline.core.types import ArticleRef, Citation, DemoTier, Jurisdiction, Language
from plumbline.generation.router import (
    Kind,
    MemorySpendMeter,
    Route,
    Router,
    Upload,
)
from plumbline.leases.checker import LeaseDone, LeaseEvent, LeaseStage
from plumbline.leases.schema import Finding, Severity

CITATION: Final = Citation(
    n=1,
    chunk_id="stub-act-1",
    ref=ArticleRef(jurisdiction=Jurisdiction.FLORIDA, law="stub-act", article="1", edition="seed"),
    label="Stub Act, s. 1",
    quote="This section exists only to exercise the interface.",
    gloss=None,
    language=Language.EN,
    verified=True,
)
TITLES: Final = {
    Severity.CONFLICT: "A stub clause that conflicts with the law",
    Severity.CHECK: "A stub clause worth a second look",
    Severity.NOTE: "A stub clause that leaves something out",
    Severity.MATCH: "A stub clause that follows the law",
}


class StubLeaseChecker:
    def __init__(self, delay_ms: int = 15) -> None:
        self.delay = delay_ms / 1000

    async def route(self, tier: DemoTier) -> Route:
        return await Router(MemorySpendMeter(), {}).route(Kind.LEASE_CHECK, tier=tier)

    async def stream(
        self,
        upload: Upload,
        route: Route,
        *,
        jurisdiction: Jurisdiction | None,
        as_of: date | None,
    ) -> AsyncIterator[LeaseEvent]:
        yield LeaseStage("redacting")
        await asyncio.sleep(self.delay)
        yield LeaseStage("reading")
        await asyncio.sleep(self.delay)
        total = len(Severity)
        yield LeaseStage("checking", done=0, total=total)
        for n, severity in enumerate(Severity, start=1):
            await asyncio.sleep(self.delay)
            yield Finding(
                n=n,
                clause_number=str(n),
                clause_text=f"Stub clause {n}, which stands in for a clause of your lease.",
                clause_language=Language.EN,
                severity=severity,
                title=TITLES[severity],
                why="This is a stub finding from the Plumbline seed. The lease checker is not "
                "connected yet, so nothing here is legal information.",
                citations=[CITATION],
                confidence=0.5,
            )
            yield LeaseStage("checking", done=n, total=total)
        yield LeaseDone(findings=total, language=Language.EN)

    async def clause(
        self,
        text: str,
        route: Route,
        *,
        jurisdiction: Jurisdiction,
        as_of: date | None,
    ) -> Finding | None:
        await asyncio.sleep(self.delay)
        return Finding(
            n=1,
            clause_number="1",
            clause_text=text,
            clause_language=Language.EN,
            severity=Severity.CHECK,
            title=TITLES[Severity.CHECK],
            why="This is a stub finding from the Plumbline seed. The clause checker is not "
            "connected here, so nothing here is legal information.",
            citations=[CITATION],
            confidence=0.5,
        )
