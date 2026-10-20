"""Tracing: the seed's stub pipeline traced into an in-memory exporter, offline."""

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from datetime import date
from typing import Any

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from plumbline.core.stream import Question, Stage, StatusEvent, StreamEvent, TraceSummary
from plumbline.generation.stub import StubPipeline
from plumbline.observability.tracing import TracedPipeline, Tracer, langfuse_client, traced
from plumbline.settings import Settings

QUESTION = Question(
    text="Can my landlord keep my deposit?", as_of=date(2026, 1, 15), request_id="req-42"
)
TRACE_ID = Langfuse.create_trace_id(seed="req-42")
OBS = "langfuse.observation."


@pytest.fixture
def langfuse() -> Iterator[tuple[Langfuse, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key=f"pk-lf-test-{secrets.token_hex(4)}",  # one client per key: a fresh one
        secret_key="sk-lf-test",
        base_url="http://127.0.0.1:9",  # nothing listens: no export may leave the machine
        span_exporter=exporter,
    )
    yield client, exporter
    client.shutdown()


def run(pipeline: TracedPipeline, question: Question = QUESTION) -> list[StreamEvent]:
    async def collect() -> list[StreamEvent]:
        return [event async for event in pipeline.stream(question)]

    return asyncio.run(collect())


def spans(client: Langfuse, exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    client.flush()
    return {span.name: span for span in exporter.get_finished_spans()}


def stub_traced(client: Langfuse, **kw: Any) -> TracedPipeline:
    tracer = Tracer(client, trace_url=lambda t: f"https://lf.test/{t}", **kw)
    return TracedPipeline(StubPipeline(delay_ms=0), tracer)


def test_each_stage_is_a_span_of_one_trace(langfuse: tuple[Langfuse, InMemorySpanExporter]) -> None:
    client, exporter = langfuse
    events = run(stub_traced(client, eval_run_id="run-7"))
    found = spans(client, exporter)
    assert set(found) == {"answer", "detect", "retrieve", "generate", "verify"}
    root = found["answer"]
    for name, span in found.items():
        assert format(span.context.trace_id, "032x") == TRACE_ID
        if name != "answer":
            assert span.parent is not None
            assert span.parent.span_id == root.context.span_id
    generation = found["generate"].attributes or {}
    assert (generation[OBS + "type"], generation[OBS + "model.name"]) == ("generation", "stub")
    # The generation ends when its stage did, though it is updated afterwards.
    assert (found["generate"].end_time or 0) <= (found["verify"].start_time or 0)
    meta = root.attributes or {}
    assert (meta[OBS + "metadata.eval_run_id"], meta[OBS + "metadata.route"]) == ("run-7", "stub")
    assert OBS + "input" not in meta
    trace = events[-1]
    assert isinstance(trace, TraceSummary)
    assert trace.trace_url == f"https://lf.test/{TRACE_ID}"


def test_text_is_traced_only_when_asked(langfuse: tuple[Langfuse, InMemorySpanExporter]) -> None:
    client, exporter = langfuse
    run(stub_traced(client, include_text=True))
    root = spans(client, exporter)["answer"].attributes or {}
    assert QUESTION.text in str(root[OBS + "input"])
    assert "stub answer" in str(root[OBS + "output"])


class Failing:
    async def stream(self, question: Question) -> AsyncIterator[StreamEvent]:
        yield StatusEvent(stage=Stage.GENERATING)
        raise RuntimeError("provider down")


def test_a_failure_is_traced_and_raised(langfuse: tuple[Langfuse, InMemorySpanExporter]) -> None:
    client, exporter = langfuse
    with pytest.raises(RuntimeError, match="provider down"):
        run(TracedPipeline(Failing(), Tracer(client, trace_url=lambda t: None)))
    found = spans(client, exporter)
    assert set(found) == {"answer", "generate"}  # both ended
    assert (found["answer"].attributes or {})[OBS + "level"] == "ERROR"


def test_a_url_lookup_failure_leaves_the_url_empty(
    langfuse: tuple[Langfuse, InMemorySpanExporter],
) -> None:
    client, _ = langfuse

    def unreachable(trace_id: str) -> str:
        raise ConnectionError("no route to Langfuse")

    trace = run(TracedPipeline(StubPipeline(delay_ms=0), Tracer(client, trace_url=unreachable)))[-1]
    assert isinstance(trace, TraceSummary)
    assert trace.trace_url is None


def test_tracing_is_off_without_keys() -> None:
    # Explicit, so a key in the process environment cannot turn tracing on here.
    unset = Settings(_env_file=None, langfuse_public_key=None, langfuse_secret_key=None)
    assert langfuse_client(unset) is None


def test_the_api_serves_the_pipeline_traced_only_when_langfuse_is_configured() -> None:
    stub = StubPipeline(delay_ms=0)
    off = Settings(_env_file=None, langfuse_public_key=None, langfuse_secret_key=None)
    assert traced(stub, off) is stub
    on = Settings(
        _env_file=None,
        langfuse_public_key=f"pk-lf-test-{secrets.token_hex(4)}",
        langfuse_secret_key="sk-lf-test",
        langfuse_host="http://127.0.0.1:9",  # nothing listens: nothing leaves the machine
    )
    served = traced(stub, on)
    assert isinstance(served, TracedPipeline)
    assert served.pipeline is stub
    assert served.tracer.include_text is False  # live traffic never sends a reader's text
    served.tracer.langfuse.shutdown()
