"""The answer pipeline: one question in, the events core/stream.py documents out.

    detect -> search -> rerank -> abstain early? -> generate, streaming the answer's text
    -> verify the citations -> final status -> AnswerSummary -> TraceSummary

Retrieval belongs to Lane A. This module names what it needs from search and reranking
as two small protocols (and, for the long-context baseline, which reads the whole law
instead of searching it, a third), so the pipeline runs on fakes today and on Lane A's classes when
they land; they may be synchronous, so they run in a worker thread and never block the
event loop. Jurisdiction detection is Lane A's keyword detector, called directly. Generation streams structured output, and the answer field's text is
shown as it is written; the complete object is validated and its citations verified before
the answer's status is decided. A recorded generation replays the same way, re-streamed in
small chunks by the LLM client.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal, Protocol

from pydantic import ValidationError

from plumbline.core.config import EvalConfig
from plumbline.core.stream import (
    AnswerSummary,
    Question,
    Stage,
    StatusEvent,
    StreamError,
    StreamEvent,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import (
    Answer,
    AnswerStatus,
    AnswerTrace,
    Chunk,
    Citation,
    Jurisdiction,
    Retrieved,
)
from plumbline.generation.abstain import (
    after_generation,
    before_generation,
    missing_jurisdictions,
)
from plumbline.generation.jsonstream import FieldStream
from plumbline.generation.llm import (
    FAST_MODEL,
    PREMIUM_MODEL,
    STRONG_MODEL,
    LLMClient,
    LLMRequest,
    LLMResult,
    Message,
    client_for,
)
from plumbline.generation.prompt import build_prompt
from plumbline.generation.schema import GeneratedAnswer, answer_json_schema
from plumbline.generation.verifier import CitedSpan, verify
from plumbline.retrieval.jurisdiction import detect as detect_jurisdictions

MODELS: Final = {"fast": FAST_MODEL, "strong": STRONG_MODEL, "premium": PREMIUM_MODEL}
# Gemini 3.8 Flash thinks by default, and its thoughts count against the same output limit
# as the answer: a long-context answer measured on 2026-10-20 spent 640 of its 1,024 tokens
# thinking and was cut off mid-JSON. The strong route asks for low thinking, and a route
# that thinks gets room for it on top of the configuration's max_output_tokens, which
# bounds the answer itself.
THINKING: Final[dict[str, Literal["low"]]] = {"strong": "low"}
THINKING_ROOM: Final = 2048
UNREADABLE: Final = "The answer could not be read. Please try again."


class ChunkSearch(Protocol):
    def search(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: Sequence[Jurisdiction] | None,
        as_of: date | None,
    ) -> list[Retrieved]: ...


class LawSource(Protocol):
    """The whole law, for the long-context baseline (LC): every article in force on the
    date, of the jurisdictions given (all, for None), in the law's own order."""

    def articles(
        self, jurisdictions: Sequence[Jurisdiction] | None, as_of: date | None
    ) -> list[Chunk]: ...


class Reranker(Protocol):
    """Lane A's reranker (retrieval/rerank.py): one relevance score per text."""

    @property
    def model(self) -> str: ...

    def scores(self, query: str, texts: Sequence[str]) -> list[float]: ...


# Something that watches an answer's events as they pass and may amend them: the tracer
# (observability.tracing.Tracer.observe) during an evaluation run.
Observer = Callable[[Question, AsyncIterator[StreamEvent]], AsyncIterator[StreamEvent]]


class PipelineError(RuntimeError):
    """The stream ended with an error; `answer()` raises it."""


@dataclass
class _Run:
    """What one answer leaves behind beyond its events, for AnswerTrace."""

    retrieved: list[Retrieved] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    result: LLMResult | None = None


class Pipeline:
    def __init__(
        self,
        config: EvalConfig,
        *,
        search: ChunkSearch | None = None,  # every configuration that retrieves
        law: LawSource | None = None,  # the long-context baseline instead, which does not
        detect: Callable[[str], list[Jurisdiction]] = detect_jurisdictions,
        reranker: Reranker | None,
        indexed: Collection[Jurisdiction],  # the jurisdictions the index holds
        client: LLMClient | None = None,
        observe: Observer | None = None,
    ) -> None:
        whole_law = config.generation.long_context or config.retrieval.mode == "none"
        if whole_law and (law is None or search is not None):
            raise ValueError(f"{config.name} reads the whole law: give it a law, not a search")
        if not whole_law and (search is None or law is not None):
            raise ValueError(f"{config.name} retrieves: give it a search, not a law")
        if (config.retrieval.rerank != "none") != (reranker is not None):
            raise ValueError(f"{config.name} reranks with {config.retrieval.rerank!r}")
        self.config = config
        self.search = search
        self.law = law
        self.detect = detect
        self.reranker = reranker
        self.indexed = frozenset(indexed)
        self.route = config.generation.route
        self.model = MODELS[self.route]
        self.client = client or client_for(self.model)
        self.observe = observe

    def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        return self._observed(question, _Run())

    async def answer(
        self, question: Question, eval_run_id: str | None = None
    ) -> tuple[Answer, AnswerTrace]:
        """The whole answer at once, with what the stream leaves out (the retrieved chunks):
        what the evaluation runner records."""
        run = _Run()
        text: list[str] = []
        citations: list[Citation] = []
        summary: AnswerSummary | None = None
        trace: TraceSummary | None = None
        async for event in self._observed(question, run):
            if isinstance(event, StreamError):
                raise PipelineError(event.message)
            if isinstance(event, TextDelta):
                text.append(event.text)
            elif isinstance(event, Citation):
                citations.append(event)
            elif isinstance(event, AnswerSummary):
                summary = event
            elif isinstance(event, TraceSummary):
                trace = event
        if summary is None or trace is None:
            raise PipelineError("the stream ended without its summary and trace")
        answer = Answer(
            text="".join(text),
            status=summary.status,
            citations=[c for c in citations if c.verified],
            jurisdictions=summary.jurisdictions,
            as_of=summary.as_of,
            confidence=summary.confidence,
            abstain_reason=summary.abstain_reason,
            invalid_citations=summary.invalid_citations,
        )
        fields = trace.model_dump(exclude={"timings_ms"})
        full = AnswerTrace(
            **fields, timings_ms=run.timings, retrieved=run.retrieved, eval_run_id=eval_run_id
        )
        return answer, full

    def _observed(self, question: Question, run: _Run) -> AsyncIterator[StreamEvent]:
        events = self._events(question, run)
        return self.observe(question, events) if self.observe else events

    async def _events(self, question: Question, run: _Run) -> AsyncIterator[StreamEvent]:
        retrieval = self.config.retrieval
        yield StatusEvent(stage=Stage.DETECTING)
        with _timer(run, "detect"):  # keyword matching: no I/O, no thread needed
            found = question.jurisdictions or self.detect(question.text)
        # The detector answers all four when a question names none. That means "unknown",
        # not a question about all four, so it filters nothing out of the search and never
        # makes an answer partial; a reader who picks all four still gets that check.
        unknown = not question.jurisdictions and set(found) == set(Jurisdiction)
        asked = [] if unknown else found
        yield StatusEvent(stage=Stage.RETRIEVING)
        with _timer(run, "retrieve"):
            jurisdictions = found if retrieval.jurisdiction_filter else None
            as_of = question.as_of if retrieval.as_of_filter else None
            if self.law is not None:
                articles = await asyncio.to_thread(self.law.articles, jurisdictions, as_of)
                run.retrieved = [
                    Retrieved(chunk=chunk, rank=rank, score=0.0)
                    for rank, chunk in enumerate(articles, start=1)
                ]
            elif self.search is not None:
                run.retrieved = await asyncio.to_thread(
                    self.search.search,
                    question.text,
                    k=retrieval.rerank_candidates if self.reranker else retrieval.top_k,
                    jurisdictions=jurisdictions,
                    as_of=as_of,
                )
        if self.reranker is not None and run.retrieved:
            yield StatusEvent(stage=Stage.RERANKING)
            with _timer(run, "rerank"):
                texts = [r.chunk.text_for_search for r in run.retrieved]
                scores = await asyncio.to_thread(self.reranker.scores, question.text, texts)
                run.retrieved = reorder(run.retrieved, scores, retrieval.top_k)

        early = before_generation(
            asked, self.indexed, run.retrieved, self.config.generation.abstain_threshold
        )
        if early is not None:
            yield TextDelta(text=early.reason or "")
            yield AnswerSummary(
                status=early.status, as_of=question.as_of, abstain_reason=early.reason
            )
            yield self._trace(question, run)
            return

        yield StatusEvent(stage=Stage.GENERATING)
        # The whole law goes first, as the prefix Claude caches: a second question on the
        # same law pays cache reads, a tenth of the input price.
        prompt = build_prompt(question, run.retrieved, asked, sources_first=self.law is not None)
        thinking = THINKING.get(self.route)
        room = THINKING_ROOM if thinking else 0
        request = LLMRequest(
            model=self.model,
            system=prompt.system,
            messages=[Message(role="user", content=prompt.user)],
            prefix=prompt.prefix,
            max_output_tokens=self.config.generation.max_output_tokens + room,
            temperature=self.config.generation.temperature,
            json_schema=answer_json_schema(),
            thinking=thinking,
        )
        preview = FieldStream("answer")
        with _timer(run, "generate"):
            async for item in self.client.stream(request):
                if isinstance(item, LLMResult):
                    run.result = item
                elif text := preview.feed(item):
                    yield TextDelta(text=text)
        if run.result is None:
            raise PipelineError(f"the {self.client.provider} stream ended without its result")
        try:
            generated = GeneratedAnswer.model_validate_json(run.result.text)
        except ValidationError:
            yield StreamError(message=UNREADABLE, retryable=True)
            return

        yield StatusEvent(stage=Stage.VERIFYING)
        with _timer(run, "verify"):
            numbered = {n: r.chunk for n, r in enumerate(run.retrieved, start=1)}
            checked = verify(generated.citations, marked_sources(generated.citations, numbered))
            missing = missing_jurisdictions(asked, self.indexed)
            decision = after_generation(
                generated.status, generated.abstain_reason, len(checked.verified), missing
            )
        for citation in checked.citations:
            yield citation
        answered = decision.status is not AnswerStatus.ABSTAINED
        yield AnswerSummary(
            status=decision.status,
            # Computed from what verified, not taken from the model's own claim.
            jurisdictions=list(dict.fromkeys(c.ref.jurisdiction for c in checked.verified))
            if answered
            else [],
            as_of=question.as_of,
            confidence=generated.confidence if answered else None,
            abstain_reason=decision.reason,
            invalid_citations=checked.invalid,
        )
        yield self._trace(question, run)

    def _trace(self, question: Question, run: _Run) -> TraceSummary:
        result = run.result
        return TraceSummary(
            request_id=question.request_id,
            config_name=self.config.name,
            config_hash=self.config.config_hash(),
            route=self.route,
            model=self.model,
            tier=question.tier,
            timings_ms=dict(run.timings),
            input_tokens=result.usage.prompt_tokens if result else 0,
            output_tokens=result.usage.output_tokens if result else 0,
            cost_usd=result.cost_usd if result else 0.0,
            cached=result.cached if result else True,  # no model call: nothing went live
        )


def marked_sources(
    citations: Sequence[CitedSpan], numbered: Mapping[int, Chunk]
) -> dict[int, Chunk]:
    """The source each of the answer's [n] markers names, found by the chunk id its
    citation copies from the source's id attribute, not by the number.

    The number is the answer's marker. Gemini numbers its markers by the sources' order;
    Claude, given a whole law (43 numbered articles), counts them as its own footnotes, [1]
    and [2] for sources 14 and 2, and looking those up by number dropped every correct
    quote (measured on 2026-10-20). The chunk id cannot be guessed, only copied, and the
    quote is still checked against that chunk's own text. A marker keeps the chunk its first
    citation names, so a later citation reusing the marker for another chunk still fails
    the verifier's check that the chunk is the marker's.
    """
    by_id = {chunk.id: chunk for chunk in numbered.values()}
    marked: dict[int, Chunk] = {}
    for cited in citations:
        if cited.n not in marked and cited.chunk_id in by_id:
            marked[cited.n] = by_id[cited.chunk_id]
    return marked


@contextmanager
def _timer(run: _Run, stage: str) -> Iterator[None]:
    """Records the block's wall time, in milliseconds, as run.timings[stage]."""
    start = time.perf_counter()
    try:
        yield
    finally:
        run.timings[stage] = round((time.perf_counter() - start) * 1000, 1)


def reorder(
    candidates: Sequence[Retrieved], scores: Sequence[float], top_k: int
) -> list[Retrieved]:
    """The candidates by rerank score, best first, cut to top_k and ranked again from 1.
    A tie keeps the retrieval order, so the same scores always give the same sources."""
    if len(scores) != len(candidates):
        raise ValueError(f"{len(scores)} rerank scores for {len(candidates)} candidates")
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i].rank))
    return [
        candidates[i].model_copy(
            update={
                "rank": rank,
                "score": scores[i],
                "scores": candidates[i].scores.model_copy(update={"rerank": scores[i]}),
            }
        )
        for rank, i in enumerate(order[:top_k], start=1)
    ]
