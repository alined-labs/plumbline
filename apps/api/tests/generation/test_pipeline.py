"""The answer pipeline over fakes for Lane A's seams and the model: the event order, early
and late abstention, verification, errors, and the collected answer and trace."""

import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Sequence
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from plumbline.cache import ResponseCache
from plumbline.core.config import ChunkerConfig, EvalConfig, GenerationConfig, RetrievalConfig
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
    AnswerStatus,
    CacheMode,
    Chunk,
    Citation,
    Jurisdiction,
    Language,
    Retrieved,
)
from plumbline.generation.llm import (
    FAST_MODEL,
    STRONG_MODEL,
    GeminiClient,
    LLMRequest,
    LLMResult,
    Usage,
)
from plumbline.generation.pipeline import (
    THINKING_ROOM,
    UNREADABLE,
    Pipeline,
    marked_sources,
    reorder,
)
from plumbline.observability.tracing import Tracer
from plumbline.settings import ROOT

FLORIDA, SPAIN, DUBAI = Jurisdiction.FLORIDA, Jurisdiction.SPAIN, Jurisdiction.DUBAI
# Verbatim from The 2026 Florida Statutes, s. 83.49(3)(a), read on 2026-10-19.
RETURN = (
    "Upon the vacating of the premises for termination of the rental agreement, if the "
    "landlord does not intend to impose a claim on the security deposit, the landlord must "
    "return the security deposit, together with interest if otherwise required, within 15 "
    "days after the termination of the rental agreement."
)
FORFEIT = (
    "If the landlord fails to give the required written notice within the 30-day period, he "
    "or she forfeits the right to impose a claim upon the security deposit and may not seek a "
    "setoff against the deposit but may file an action for damages after returning the "
    "security deposit to the tenant."
)
QUOTE = "the landlord must return the security deposit, together with interest"


def chunk(id: str, text: str) -> Chunk:
    return Chunk(
        id=id,
        document_id="fl-stat-83",
        jurisdiction=FLORIDA,
        law="fl-stat-83",
        language=Language.EN,
        edition="2026",
        article="83.49",
        label=f"Fla. Stat. § 83.49(3)(a) ({id})",
        text=text,
        text_for_search=text,
    )


HITS = [
    Retrieved(chunk=chunk(id, text), rank=i, score=0.02)
    for i, (id, text) in enumerate([("return", RETURN), ("forfeit", FORFEIT), ("x", RETURN)], 1)
]


def reply(**change: Any) -> str:
    base = {
        "answer": "If the landlord makes no claim, the deposit comes back within 15 days [1].",
        "citations": [{"n": 1, "chunk_id": "return", "quote": QUOTE, "gloss": None}],
        "status": "answered",
        "jurisdictions": ["florida"],
        "confidence": 0.9,
        "abstain_reason": None,
    }
    return json.dumps(base | change)


class Search:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, question: str, *, k: int, **filters: Any) -> list[Retrieved]:
        self.calls.append({"k": k, **filters})
        return HITS[:k]


def florida(question: str) -> list[Jurisdiction]:
    return [FLORIDA]


class Reranker:
    """Lane A's interface: one score per text; texts past the given scores score 0."""

    model = "fake-reranker"

    def __init__(self, given: Sequence[float]) -> None:
        self.given = given

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        return [self.given[i] if i < len(self.given) else 0.0 for i in range(len(texts))]


class Model:
    provider = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        raise NotImplementedError

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        self.requests.append(request)
        for i in range(0, len(self.text), 7):
            yield self.text[i : i + 7]
        usage = Usage(input_tokens=900, output_tokens=120)
        yield LLMResult(self.text, request.model, usage, 0.0006, 50, "STOP", True, "key")


def config(rerank: str = "local", threshold: float | None = 0.3) -> EvalConfig:
    return EvalConfig(
        name="T",
        description="test",
        chunker=ChunkerConfig(kind="article"),
        retrieval=RetrievalConfig(mode="hybrid", top_k=2, rerank=rerank, rerank_candidates=3),
        generation=GenerationConfig(route="fast", abstain_threshold=threshold),
    )


def pipeline(text: str = "", scores: Sequence[float] = (0.9, 0.4, 0.1), **kw: Any) -> Pipeline:
    reranker = Reranker(scores) if kw.get("rerank", "local") != "none" else None
    return Pipeline(
        config(**kw),
        search=Search(),
        detect=florida,
        reranker=reranker,
        indexed={FLORIDA, SPAIN},
        client=Model(text or reply()),
    )


QUESTION = Question(
    text="When must my deposit come back?", as_of=date(2026, 1, 15), request_id="r1"
)


def events(p: Pipeline, question: Question = QUESTION) -> list[StreamEvent]:
    async def collect() -> list[StreamEvent]:
        return [event async for event in p.stream(question)]

    return asyncio.run(collect())


def stages(evs: list[StreamEvent]) -> list[Stage]:
    return [e.stage for e in evs if isinstance(e, StatusEvent)]


def test_an_answer_streams_in_the_documented_order() -> None:
    p = pipeline()
    evs = events(p)
    kinds = [type(e).__name__ for e in evs]
    first_text, last_text = (
        kinds.index("TextDelta"),
        len(kinds) - 1 - kinds[::-1].index("TextDelta"),
    )
    assert kinds[:first_text] == ["StatusEvent"] * 4
    assert set(kinds[first_text : last_text + 1]) == {"TextDelta"}
    assert kinds[last_text + 1 :] == ["StatusEvent", "Citation", "AnswerSummary", "TraceSummary"]
    assert stages(evs) == [
        Stage.DETECTING,
        Stage.RETRIEVING,
        Stage.RERANKING,
        Stage.GENERATING,
        Stage.VERIFYING,
    ]
    assert "".join(e.text for e in evs if isinstance(e, TextDelta)) == json.loads(reply())["answer"]
    citation, summary, trace = evs[-3:]
    assert isinstance(citation, Citation)
    assert citation.verified
    assert summary == AnswerSummary(
        status=AnswerStatus.ANSWERED,
        jurisdictions=[FLORIDA],
        as_of=date(2026, 1, 15),
        confidence=0.9,
    )
    assert isinstance(trace, TraceSummary)
    assert (trace.model, trace.input_tokens, trace.output_tokens, trace.cached) == (
        FAST_MODEL,
        900,
        120,
        True,
    )
    assert set(trace.timings_ms) == {"detect", "retrieve", "rerank", "generate", "verify"}
    assert p.search.calls == [{"k": 3, "jurisdictions": [FLORIDA], "as_of": date(2026, 1, 15)}]  # type: ignore[attr-defined]
    request = p.client.requests[0]  # type: ignore[attr-defined]
    assert request.json_schema is not None
    assert "<sources>" in request.messages[0].content


def test_a_weak_best_match_abstains_without_a_model_call() -> None:
    p = pipeline(scores=(0.2, 0.1))
    evs = events(p)
    assert stages(evs) == [Stage.DETECTING, Stage.RETRIEVING, Stage.RERANKING]
    summary, trace = evs[-2:]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ABSTAINED
    assert isinstance(evs[-3], TextDelta)
    assert evs[-3].text == summary.abstain_reason
    assert isinstance(trace, TraceSummary)
    assert (trace.input_tokens, trace.cached) == (0, True)
    assert p.client.requests == []  # type: ignore[attr-defined]


def test_an_answer_whose_quotes_fail_is_withdrawn() -> None:
    bad = [
        {"n": 1, "chunk_id": "return", "quote": "the landlord may keep the deposit", "gloss": None}
    ]
    evs = events(pipeline(reply(citations=bad)))
    citation, summary = evs[-3], evs[-2]
    assert isinstance(citation, Citation)
    assert not citation.verified
    assert isinstance(summary, AnswerSummary)
    assert (
        summary.status,
        summary.invalid_citations,
        summary.jurisdictions,
        summary.confidence,
    ) == (AnswerStatus.ABSTAINED, 1, [], None)


def test_the_model_can_abstain_and_partial_answers_name_what_is_missing() -> None:
    abstained = events(
        pipeline(reply(status="abstained", citations=[], abstain_reason="Pets are not covered."))
    )
    assert abstained[-2] == AnswerSummary(
        status=AnswerStatus.ABSTAINED,
        as_of=date(2026, 1, 15),
        abstain_reason="Pets are not covered.",
    )
    both = QUESTION.model_copy(update={"jurisdictions": [FLORIDA, DUBAI]})
    partial = events(pipeline(), both)[-2]
    assert isinstance(partial, AnswerSummary)
    assert partial.status is AnswerStatus.PARTIAL
    assert partial.abstain_reason == "Plumbline does not hold the tenancy law of Dubai."


def test_an_unreadable_reply_ends_the_stream_with_an_error() -> None:
    evs = events(pipeline("this is not JSON"))
    assert evs[-1] == StreamError(message=UNREADABLE, retryable=True)
    assert not any(isinstance(e, AnswerSummary) for e in evs)


def test_without_a_reranker_generation_gets_the_top_k() -> None:
    p = pipeline(rerank="none", threshold=None)
    evs = events(p)
    assert Stage.RERANKING not in stages(evs)
    assert p.search.calls[0]["k"] == 2  # type: ignore[attr-defined]


def test_answer_collects_the_answer_and_its_trace() -> None:
    answer, trace = asyncio.run(pipeline().answer(QUESTION, eval_run_id="run-1"))
    assert answer.status is AnswerStatus.ANSWERED
    assert [c.chunk_id for c in answer.citations] == ["return"]
    assert answer.text.endswith("[1].")
    assert [r.scores.rerank for r in trace.retrieved] == [0.9, 0.4]
    assert (trace.eval_run_id, trace.cost_usd) == ("run-1", 0.0006)


def test_a_config_must_match_its_reranker() -> None:
    with pytest.raises(ValueError, match="reranks with 'local'"):
        Pipeline(
            config(),
            search=Search(),
            detect=florida,
            reranker=None,
            indexed={FLORIDA},
            client=Model(""),
        )


def test_an_observer_sees_every_event_streamed_or_collected() -> None:
    seen: list[str] = []

    async def observe(
        question: Question, stream: AsyncIterator[StreamEvent]
    ) -> AsyncIterator[StreamEvent]:
        async for event in stream:
            seen.append(type(event).__name__)
            if isinstance(event, TraceSummary):  # what the tracer does with its URL
                event = event.model_copy(update={"trace_url": "https://lf.test/t"})
            yield event

    p = Pipeline(
        config(),
        search=Search(),
        detect=florida,
        reranker=Reranker((0.9, 0.4, 0.1)),
        indexed={FLORIDA, SPAIN},
        client=Model(reply()),
        observe=observe,
    )
    streamed = events(p)
    assert seen == [type(e).__name__ for e in streamed]
    assert isinstance(streamed[-1], TraceSummary)
    assert streamed[-1].trace_url == "https://lf.test/t"
    _, trace = asyncio.run(p.answer(QUESTION, eval_run_id="run-1"))
    assert (trace.trace_url, trace.eval_run_id) == ("https://lf.test/t", "run-1")


def recorded_pipeline(mode: CacheMode) -> Pipeline:
    """The fast route on Gemini through cache/. Its one recording was made with
    `uv run python apps/api/tests/generation/test_pipeline.py`; a change to the prompt, schema or model needs a
    new one (a changed request is a new key, and replay then fails loudly)."""
    return Pipeline(
        config(),
        search=Search(),
        detect=florida,
        reranker=Reranker((0.9, 0.4, 0.1)),
        indexed={FLORIDA, SPAIN},
        client=GeminiClient(cache=ResponseCache(mode, ROOT / "cache")),
    )


def test_a_recorded_gemini_answer_replays_and_verifies() -> None:
    answer, trace = asyncio.run(recorded_pipeline(CacheMode.REPLAY).answer(QUESTION))
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.citations
    assert all(c.verified for c in answer.citations)
    assert "15 days" in answer.text
    assert trace.cached
    assert trace.cost_usd > 0


if __name__ == "__main__":
    # Records the one generation the test above replays: CACHE_MODE has no effect here.
    answer, trace = asyncio.run(recorded_pipeline(CacheMode.RECORD).answer(QUESTION))
    print(answer.status, f"${trace.cost_usd:.5f}", answer.text)


def test_with_lane_a_detector_a_vague_question_is_unknown_not_partial() -> None:
    def build() -> Pipeline:  # A6's detector, the default
        return Pipeline(
            config(),
            search=Search(),
            reranker=Reranker((0.9, 0.4, 0.1)),
            indexed={FLORIDA, SPAIN},
            client=Model(reply()),
        )

    vague = build()
    summary = events(vague)[-2]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ANSWERED  # not partial for Dubai and Colombia
    assert set(vague.search.calls[0]["jurisdictions"]) == set(Jurisdiction)  # type: ignore[attr-defined]
    named = build()
    events(
        named, QUESTION.model_copy(update={"text": "In Florida, when must my deposit come back?"})
    )
    assert named.search.calls[0]["jurisdictions"] == [FLORIDA]  # type: ignore[attr-defined]


def test_rerank_scores_reorder_the_candidates_and_ties_keep_retrieval_order() -> None:
    ranked = reorder(HITS, [0.2, 0.9, 0.2], top_k=2)
    assert [(r.chunk.id, r.rank, r.score) for r in ranked] == [
        ("forfeit", 1, 0.9),
        ("return", 2, 0.2),
    ]
    assert ranked[0].scores.rerank == 0.9
    with pytest.raises(ValueError, match="2 rerank scores for 3 candidates"):
        reorder(HITS, [0.1, 0.2], top_k=2)


def test_an_evaluation_run_is_traced_through_the_observer() -> None:
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(
        public_key=f"pk-lf-test-{secrets.token_hex(4)}",
        secret_key="sk-lf-test",
        base_url="http://127.0.0.1:9",  # nothing listens: nothing leaves the machine
        span_exporter=exporter,
    )
    tracer = Tracer(langfuse, eval_run_id="run-9", trace_url=lambda t: f"https://lf.test/{t}")
    p = Pipeline(
        config(),
        search=Search(),
        detect=florida,
        reranker=Reranker((0.9, 0.4, 0.1)),
        indexed={FLORIDA, SPAIN},
        client=Model(reply()),
        observe=tracer.observe,
    )
    _, trace = asyncio.run(p.answer(QUESTION, eval_run_id="run-9"))
    langfuse.flush()
    spans = {s.name: dict(s.attributes or {}) for s in exporter.get_finished_spans()}
    langfuse.shutdown()
    assert set(spans) == {"answer", "detect", "retrieve", "rerank", "generate", "verify"}
    assert spans["answer"]["langfuse.observation.metadata.eval_run_id"] == "run-9"
    assert spans["generate"]["langfuse.observation.model.name"] == FAST_MODEL
    assert trace.trace_url is not None
    assert trace.trace_url.startswith("https://lf.test/")


class Law:
    """The long-context baseline's source: every article it holds, whatever the question."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def articles(self, jurisdictions: Any, as_of: Any) -> list[Chunk]:
        self.calls.append((jurisdictions, as_of))
        return [hit.chunk for hit in HITS]


def lc_config() -> EvalConfig:
    return EvalConfig(
        name="LC",
        description="test",
        chunker=ChunkerConfig(kind="article"),
        retrieval=RetrievalConfig(mode="none"),
        generation=GenerationConfig(route="strong", long_context=True),
    )


def test_the_long_context_baseline_reads_the_whole_law() -> None:
    law, model = Law(), Model(reply())
    p = Pipeline(
        lc_config(), law=law, detect=florida, reranker=None, indexed={FLORIDA, SPAIN}, client=model
    )
    evs = events(p)
    assert stages(evs) == [Stage.DETECTING, Stage.RETRIEVING, Stage.GENERATING, Stage.VERIFYING]
    assert law.calls == [([FLORIDA], date(2026, 1, 15))]
    request = model.requests[0]
    assert request.model == STRONG_MODEL
    # All of the law, first, as the cacheable prefix; the question after it, outside it.
    assert request.prefix.count("<source n=") == len(HITS)
    assert "<question>" not in request.prefix
    assert request.messages[0].content.startswith("<question>")
    # The strong model thinks: low, with room beside the answer's own budget.
    assert request.thinking == "low"
    assert request.max_output_tokens == 1024 + THINKING_ROOM
    summary = evs[-2]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ANSWERED


def test_the_fast_route_sends_no_thinking_and_the_configured_budget() -> None:
    model = Model(reply())
    p = Pipeline(
        config(rerank="none", threshold=None),
        search=Search(),
        detect=florida,
        reranker=None,
        indexed={FLORIDA},
        client=model,
    )
    events(p)
    (request,) = model.requests
    assert request.thinking is None
    assert request.max_output_tokens == 1024


def test_a_pipeline_needs_the_source_its_configuration_reads() -> None:
    with pytest.raises(ValueError, match="reads the whole law"):
        Pipeline(lc_config(), search=Search(), reranker=None, indexed={FLORIDA}, client=Model(""))
    with pytest.raises(ValueError, match="retrieves"):
        Pipeline(
            config(rerank="none", threshold=None),
            law=Law(),
            reranker=None,
            indexed={FLORIDA},
            client=Model(""),
        )


FORFEIT_QUOTE = "forfeits the right to impose a claim upon the security deposit"


def test_markers_counted_as_footnotes_find_their_sources_by_chunk_id() -> None:
    # Claude, given many sources, numbers its markers [1], [2] in the order it cites them:
    # here [1] is source 2 ("forfeit") and [2] is source 1 ("return").
    footnoted = reply(
        answer="The landlord forfeits the claim [1] and must return the deposit [2].",
        citations=[
            {"n": 1, "chunk_id": "forfeit", "quote": FORFEIT_QUOTE, "gloss": None},
            {"n": 2, "chunk_id": "return", "quote": QUOTE, "gloss": None},
        ],
    )
    p = Pipeline(
        lc_config(),
        law=Law(),
        detect=florida,
        reranker=None,
        indexed={FLORIDA},
        client=Model(footnoted),
    )
    evs = events(p)
    cited = [e for e in evs if isinstance(e, Citation)]
    assert [(c.n, c.chunk_id, c.verified) for c in cited] == [
        (1, "forfeit", True),
        (2, "return", True),
    ]
    summary = evs[-2]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ANSWERED


def test_marked_sources_keep_a_markers_first_chunk() -> None:
    numbered = {i: hit.chunk for i, hit in enumerate(HITS, 1)}
    cited = [
        SimpleNamespace(n=1, chunk_id="forfeit"),
        SimpleNamespace(n=1, chunk_id="return"),  # [1] reused for another chunk
        SimpleNamespace(n=2, chunk_id="nowhere"),  # an id no source has
    ]
    marked = marked_sources(cited, numbered)  # type: ignore[arg-type]
    assert {n: c.id for n, c in marked.items()} == {1: "forfeit"}
