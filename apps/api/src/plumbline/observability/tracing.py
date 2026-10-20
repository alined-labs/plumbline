"""Tracing: one Langfuse trace per answer, a span for each stage it went through, and a
generation for the model call with its tokens and cost; the route, the status and the
evaluation run ride on the trace.

A `Tracer` observes an answer's events from outside, as they stream past: it opens a
stage's span when the stage's status event arrives and ends it when the next stage begins,
so the pipeline knows nothing about tracing, and it writes the trace's URL into the
TraceSummary the reader receives. The API serves `traced(pipeline, settings)`; an
evaluation run hands `Tracer(..., eval_run_id=...).observe` to the pipeline, so that
answers it collects without streaming are traced too. The queries row is not written
here: the API records it from the same events, trace URL included. The generation's tokens and cost are only known from that final summary,
after its stage is over, so the generation stays open until then and is ended at the time
its stage really ended.

Spans carry no question or answer text unless asked to (evaluation runs over the public
golden questions): what a reader types can be personal, and Langfuse is a third party.
Tracing never fails an answer: if Langfuse cannot give a URL, the URL is left empty.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Final, Literal

from langfuse import Langfuse

from plumbline.core.stream import (
    AnswerPipeline,
    AnswerSummary,
    Question,
    Stage,
    StatusEvent,
    StreamError,
    StreamEvent,
    TextDelta,
    TraceSummary,
)
from plumbline.settings import Settings

Kind = Literal["span", "retriever", "generation"]
SPANS: Final[dict[Stage, tuple[str, Kind]]] = {
    Stage.DETECTING: ("detect", "span"),
    Stage.RETRIEVING: ("retrieve", "retriever"),
    Stage.RERANKING: ("rerank", "retriever"),
    Stage.GENERATING: ("generate", "generation"),
    Stage.VERIFYING: ("verify", "span"),
}


def langfuse_client(settings: Settings) -> Langfuse | None:
    """The Langfuse client, or None when its keys are not configured (tracing off)."""
    if not settings.langfuse_public_key or settings.langfuse_secret_key is None:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_host,
        environment=settings.environment,
    )


class Tracer:
    def __init__(
        self,
        langfuse: Langfuse,
        *,
        eval_run_id: str | None = None,
        include_text: bool = False,  # only for the public golden questions
        trace_url: Callable[[str], str | None] | None = None,  # default: ask Langfuse
    ) -> None:
        self.langfuse = langfuse
        self.eval_run_id = eval_run_id
        self.include_text = include_text
        self._trace_url = trace_url or (lambda trace_id: langfuse.get_trace_url(trace_id=trace_id))

    async def observe(
        self, question: Question, events: AsyncIterator[StreamEvent]
    ) -> AsyncIterator[StreamEvent]:
        """The same events, traced; the TraceSummary gains the trace's URL."""
        trace_id = Langfuse.create_trace_id(seed=question.request_id)
        root = self.langfuse.start_observation(
            trace_context={"trace_id": trace_id},
            name="answer",
            input=question.text if self.include_text else None,
            metadata={
                "request_id": question.request_id,
                "tier": question.tier.value,
                "as_of": question.as_of.isoformat() if question.as_of else "",
                "eval_run_id": self.eval_run_id or "",
            },
        )
        open_span: Any = None
        generation: Any = None
        generation_end: int | None = None
        answer_text: list[str] = []
        try:
            async for event in events:
                if isinstance(event, StatusEvent):
                    if open_span is not None and open_span is generation:
                        generation_end = time.time_ns()  # ended once its usage is known
                    elif open_span is not None:
                        open_span.end()
                    name, kind = SPANS[event.stage]
                    open_span = root.start_observation(name=name, as_type=kind)
                    if kind == "generation":
                        generation = open_span
                elif isinstance(event, AnswerSummary):
                    root.update(
                        output={
                            "status": event.status.value,
                            "invalid_citations": event.invalid_citations,
                            **({"answer": "".join(answer_text)} if self.include_text else {}),
                        }
                    )
                elif isinstance(event, StreamError):
                    root.update(level="ERROR", status_message=event.message)
                elif isinstance(event, TraceSummary):
                    if generation is not None:
                        generation.update(
                            model=event.model,
                            usage_details={
                                "input": event.input_tokens,
                                "output": event.output_tokens,
                            },
                            cost_details={"total": event.cost_usd},
                        )
                    root.update(
                        metadata={
                            "route": event.route,
                            "model": event.model,
                            "config": event.config_name,
                            "config_hash": event.config_hash,
                            "cached": str(event.cached),
                        }
                    )
                    event = event.model_copy(update={"trace_url": await self._url(trace_id)})
                elif isinstance(event, TextDelta) and self.include_text:
                    answer_text.append(event.text)
                yield event
        except Exception as exc:
            root.update(level="ERROR", status_message=str(exc))
            raise
        finally:
            if generation is not None:
                generation.end(end_time=generation_end)
            if open_span is not None and open_span is not generation:
                open_span.end()
            root.end()

    async def _url(self, trace_id: str) -> str | None:
        try:
            # The first call per process asks Langfuse for the project id: a network call.
            return await asyncio.to_thread(self._trace_url, trace_id)
        except Exception:
            return None


class TracedPipeline:
    """An AnswerPipeline whose every answer a Tracer observes."""

    def __init__(self, pipeline: AnswerPipeline, tracer: Tracer) -> None:
        self.pipeline = pipeline
        self.tracer = tracer

    def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        return self.tracer.observe(question, self.pipeline.stream(question))


def tracer(
    settings: Settings, *, eval_run_id: str | None = None, include_text: bool = False
) -> Tracer | None:
    """A Tracer on the configured Langfuse project, or None when tracing is off."""
    client = langfuse_client(settings)
    if client is None:
        return None
    return Tracer(client, eval_run_id=eval_run_id, include_text=include_text)


def traced(pipeline: AnswerPipeline, settings: Settings) -> AnswerPipeline:
    """The pipeline the API serves: traced when Langfuse is configured, as it is otherwise.
    Live traffic never sends text: a reader's question can be personal."""
    observer = tracer(settings)
    return TracedPipeline(pipeline, observer) if observer else pipeline
