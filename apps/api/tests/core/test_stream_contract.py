import pytest
from pydantic import ValidationError

from plumbline.core.stream import (
    DATA_PARTS,
    MAX_QUESTION_CHARS,
    AnswerSummary,
    Question,
    StatusEvent,
    StreamError,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import AnswerStatus, Citation
from plumbline.generation.stub import StubPipeline


def test_every_payload_has_a_data_part_and_text_and_errors_do_not() -> None:
    assert set(DATA_PARTS) == {StatusEvent, Citation, AnswerSummary, TraceSummary}
    assert set(DATA_PARTS.values()) == {"status", "citation", "answer", "trace"}
    assert TextDelta not in DATA_PARTS
    assert StreamError not in DATA_PARTS


def test_questions_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Question(text="   ", request_id="r")
    with pytest.raises(ValidationError):
        Question(text="x" * (MAX_QUESTION_CHARS + 1), request_id="r")


async def collect(text: str) -> list[object]:
    pipeline = StubPipeline(delay_ms=0)
    return [e async for e in pipeline.stream(Question(text=text, request_id="r1"))]


@pytest.mark.anyio
async def test_the_stub_yields_the_documented_order() -> None:
    events = await collect("Can my landlord keep the deposit?")
    kinds = [type(e).__name__ for e in events]
    first_text = kinds.index("TextDelta")
    assert all(k == "StatusEvent" for k in kinds[:first_text])
    assert kinds[-2:] == ["AnswerSummary", "TraceSummary"]
    assert "Citation" in kinds
    summary = events[-2]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ANSWERED
    assert "not legal advice" in summary.disclaimer


@pytest.mark.anyio
async def test_the_stub_abstains_without_citations() -> None:
    events = await collect("Please abstain")
    assert not any(isinstance(e, Citation) for e in events)
    summary = events[-2]
    assert isinstance(summary, AnswerSummary)
    assert summary.status is AnswerStatus.ABSTAINED
