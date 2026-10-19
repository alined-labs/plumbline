"""The seed's stub pipeline: a deterministic answer that exercises every part of the stream
(status, text, a citation, the answer summary and the trace) before retrieval or
generation exist. It quotes nothing real: its one citation is to an invented "Stub Act".

A question containing "abstain" gets the abstained shape, one containing "partial" the
partial shape, and anything else the answered shape, so the front end can build each state.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from plumbline.core.stream import (
    AnswerSummary,
    Question,
    Stage,
    StatusEvent,
    StreamEvent,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import AnswerStatus, ArticleRef, Citation, Jurisdiction, Language

STUB_HASH = "0" * 64
_CITATION = Citation(
    n=1,
    chunk_id="stub-act-1",
    ref=ArticleRef(jurisdiction=Jurisdiction.FLORIDA, law="stub-act", article="1", edition="seed"),
    label="Stub Act, s. 1",
    quote="This section exists only to exercise the interface.",
    gloss=None,
    language=Language.EN,
    verified=True,
)


class StubPipeline:
    def __init__(self, delay_ms: int = 15) -> None:
        self.delay = delay_ms / 1000

    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        text = question.text.lower()
        status = (
            AnswerStatus.ABSTAINED
            if "abstain" in text
            else AnswerStatus.PARTIAL
            if "partial" in text
            else AnswerStatus.ANSWERED
        )
        for stage in (Stage.DETECTING, Stage.RETRIEVING, Stage.GENERATING):
            yield StatusEvent(stage=stage)
            await asyncio.sleep(self.delay)
        if status is AnswerStatus.ABSTAINED:
            words = "The seed has no corpus yet, so this stub declines to answer."
        elif status is AnswerStatus.PARTIAL:
            words = (
                "This stub answers the first half of the question from the Stub Act [1] "
                "and declines the rest, which the corpus does not cover."
            )
        else:
            words = (
                "This is a stub answer from the Plumbline seed [1]. Retrieval and generation "
                "are not connected yet, so nothing here is legal information."
            )
        for word in words.split(" "):
            yield TextDelta(text=f"{word} ")
            await asyncio.sleep(self.delay)
        if status is not AnswerStatus.ABSTAINED:
            yield StatusEvent(stage=Stage.VERIFYING)
            yield _CITATION
        yield AnswerSummary(
            status=status,
            jurisdictions=[Jurisdiction.FLORIDA] if status is not AnswerStatus.ABSTAINED else [],
            as_of=question.as_of,
            abstain_reason="The stub has no corpus." if status is AnswerStatus.ABSTAINED else None,
        )
        yield TraceSummary(
            request_id=question.request_id,
            config_name="stub",
            config_hash=STUB_HASH,
            route="stub",
            model="stub",
            tier=question.tier,
            timings_ms={"generate": 0.0},
            cached=True,
        )
