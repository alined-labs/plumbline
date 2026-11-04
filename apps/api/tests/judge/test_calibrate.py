"""The calibration run: which answers reach the sheet, the blind verdicts, and the report."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from plumbline.core.stream import Question
from plumbline.core.types import (
    Answer,
    AnswerStatus,
    AnswerTrace,
    ArticleRef,
    Chunk,
    Citation,
    DemoTier,
    GoldenItem,
    Jurisdiction,
    Language,
    Retrieved,
)
from plumbline.generation.llm import LLMRequest, LLMResult, Usage
from plumbline.judge import calibrate
from plumbline.judge.calibrate import build_sheet, report, score
from plumbline.judge.judge import Judge
from plumbline.judge.labels import read_sheet, write_sheet, write_sheets
from rag_eval.schema import Category, Difficulty, SourceType, Split

FLORIDA = Jurisdiction.FLORIDA
STATUTE = (  # Verbatim from The 2026 Florida Statutes, s. 83.49(3)(a), read on 2026-10-19.
    "Upon the vacating of the premises for termination of the rental agreement, if the "
    "landlord does not intend to impose a claim on the security deposit, the landlord must "
    "return the security deposit, together with interest if otherwise required, within 15 "
    "days after the termination of the rental agreement."
)
CHUNK = Chunk(
    id="fl-83.49-3-a",
    document_id="fl-stat-83",
    jurisdiction=FLORIDA,
    law="fl-stat-83",
    language=Language.EN,
    edition="2026",
    article="83.49",
    label="Fla. Stat. § 83.49(3)(a)",
    text=STATUTE,
    text_for_search=STATUTE,
)


def item(n: int, *, split: Split = Split.DEV, abstain: bool = False) -> GoldenItem:
    common: dict[str, Any] = {
        "id": f"fl-{n:04d}",
        "source_language": Language.EN,
        "difficulty": Difficulty.EASY,
        "source_type": SourceType.SYNTHETIC,
        "split": split,
        "added_in": "v1",
    }
    if abstain:
        return GoldenItem(
            question="How do I register a company in Texas?",
            jurisdictions=[],
            category=Category.OUT_OF_SCOPE,
            expected_abstain=True,
            **common,
        )
    return GoldenItem(
        question=f"Question {n}: when must my landlord return my deposit?",
        jurisdictions=[FLORIDA],
        category=Category.SINGLE_ARTICLE,
        gold_refs=[
            ArticleRef(jurisdiction=FLORIDA, law="fl-stat-83", article="83.49", edition="2026")
        ],
        reference_answer="Within 15 days after the rental agreement ends, if no claim is made.",
        **common,
    )


class Answers:
    """A pipeline whose answer depends on the item: odd items right, even items wrong, and
    item 9 abstained."""

    config = SimpleNamespace(retrieval=SimpleNamespace(jurisdiction_filter=True))

    def __init__(self) -> None:
        self.questions: list[Question] = []

    def detect(self, question: str) -> list[Jurisdiction]:
        return [Jurisdiction.DUBAI] if "Dubai" in question else [FLORIDA]

    async def answer(
        self, question: Question, eval_run_id: str | None = None
    ) -> tuple[Answer, AnswerTrace]:
        self.questions.append(question)
        n = int(question.request_id.removeprefix("cal-fl-"))
        status = AnswerStatus.ABSTAINED if n == 9 else AnswerStatus.ANSWERED
        days = 15 if n % 2 else 30
        citation = Citation(
            n=1,
            chunk_id=CHUNK.id,
            ref=CHUNK.ref,
            label=CHUNK.label,
            quote="the landlord must return the security deposit",
            language=Language.EN,
            verified=True,
        )
        answer = Answer(
            text=f"The landlord must return it within {days} days [1].",
            status=status,
            citations=[citation],
        )
        trace = AnswerTrace(
            request_id=question.request_id,
            config_name="A2",
            config_hash="0" * 64,
            route="fast",
            model="fake",
            tier=DemoTier.FULL,
            retrieved=[Retrieved(chunk=CHUNK, rank=1, score=0.9)],
            eval_run_id=eval_run_id,
        )
        return answer, trace


class Model:
    """A judge model that passes an answer stating the 15-day rule, and counts its calls."""

    provider = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        answer = request.messages[0].content.split("<answer>")[1]
        verdict = "pass" if "15 days" in answer.split("</answer>")[0] else "fail"
        text = json.dumps({"reasoning": "Compared with the rule.", "verdict": verdict})
        return LLMResult(text, request.model, Usage(), 0.0, 0, "end_turn", True, "k")

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        raise NotImplementedError
        yield


ITEMS = [item(n) for n in range(1, 13)] + [item(13, split=Split.TEST), item(14, abstain=True)]


def test_the_sheet_holds_dev_answers_half_likely_to_pass_and_no_verdicts() -> None:
    pipeline, model = Answers(), Model()
    rows = asyncio.run(build_sheet(ITEMS, pipeline, Judge(model), config_name="A2", n=6, seed=1))  # type: ignore[arg-type]
    asked = {q.request_id for q in pipeline.questions}
    assert asked == {f"cal-fl-{n:04d}" for n in range(1, 13)}  # dev items with a reference only
    assert len(rows) == 6
    assert "fl-0009" not in {r.item_id for r in rows}  # abstained: nothing to judge
    right = [r for r in rows if "15 days" in r.answer]
    assert len(right) == 3  # half the judge passed, half it did not
    assert all(r.sources == [f"{CHUNK.label}\n{STATUTE}"] for r in rows)
    assert rows[0].citations[0].quote == "the landlord must return the security deposit"
    assert all(r.faithfulness is None and r.correctness is None for r in rows)
    assert "verdict" not in json.dumps([r.model_dump() for r in rows])


def test_scoring_asks_the_judge_again_and_reports_intervals() -> None:
    rows = asyncio.run(build_sheet(ITEMS, Answers(), Judge(Model()), config_name="A2", n=6, seed=1))  # type: ignore[arg-type]
    # The person agrees with the judge on correctness, and fails one faithful answer.
    labelled = []
    for i, r in enumerate(rows):
        passed = "15 days" in r.answer
        faithful = "fail" if (passed and i == 0) else ("pass" if passed else "fail")
        labelled.append(
            r.model_copy(
                update={"correctness": "pass" if passed else "fail", "faithfulness": faithful}
            )
        )
    agreements = {a.criterion: a for a in asyncio.run(score(labelled, Judge(Model())))}
    assert (agreements["correctness"].tpr.value, agreements["correctness"].tnr.value) == (1.0, 1.0)
    faithfulness = agreements["faithfulness"]
    assert faithfulness.tpr.total + faithfulness.tnr.total == 6
    table = report(list(agreements.values()), "claude-haiku-5-5", version="v1")
    assert (
        "| v1 | claude-haiku-5-5 | correctness | 1.00 [0.44, 1.00] (3/3) | 1.00 [0.44, 1.00] (3/3) | too few labels (under 20 a class) | neither |"
        in table
    )


def test_unlabelled_rows_are_not_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    model = Model()
    rows = asyncio.run(build_sheet(ITEMS, Answers(), Judge(model), config_name="A2", n=4, seed=2))  # type: ignore[arg-type]
    sheet = tmp_path / "labelled.jsonl"
    write_sheet([rows[0].model_copy(update={"correctness": "pass"}), *rows[1:]], sheet)
    model.calls = 0
    monkeypatch.setattr(calibrate, "Judge", lambda: Judge(model))
    calibrate.main(["score", str(sheet)])
    assert model.calls == 2  # one labelled row, two criteria
    out = capsys.readouterr().out
    assert "| v1 | claude-haiku-5-5 | correctness |" in out  # the judge's model, by name
    assert "no labels" in out  # faithfulness: nothing labelled


def test_items_that_may_read_fetch_only_law_record_apart_or_not_at_all(tmp_path: Path) -> None:
    dubai = [
        i.model_copy(update={"question": i.question.replace("landlord", "Dubai landlord")})
        for i in ITEMS[:4]
    ]
    public, fetched = Answers(), Answers()
    judge, fetched_judge = Model(), Model()
    rows = asyncio.run(
        build_sheet(
            [*dubai, *ITEMS[4:]],
            public,  # type: ignore[arg-type]
            Judge(judge),
            config_name="A2",
            fetched=(fetched, Judge(fetched_judge)),  # type: ignore[arg-type]
            n=10,
            seed=1,
        )
    )
    assert {q.request_id for q in fetched.questions} == {f"cal-{i.id}" for i in dubai}
    assert not {q.request_id for q in public.questions} & {f"cal-{i.id}" for i in dubai}
    assert fetched_judge.calls == 2 * len(dubai)
    assert {r.item_id for r in rows if r.restricted} <= {i.id for i in dubai}

    sheet, fetched_sheet = tmp_path / "to_label.jsonl", tmp_path / "fetched" / "to_label.jsonl"
    write_sheets(rows, sheet, fetched_sheet)
    assert not any(r.restricted for r in read_sheet(sheet))
    assert all(r.restricted for r in read_sheet(fetched_sheet))
    labelled = [r.model_copy(update={"correctness": "pass"}) for r in rows]
    with pytest.raises(ValueError, match="fetched cache"):
        asyncio.run(score(labelled, Judge(Model())))

    alone = asyncio.run(build_sheet(dubai, Answers(), Judge(Model()), config_name="A2", n=4))  # type: ignore[arg-type]
    assert alone == []  # no fetched pair: left out, never recorded where git would hold it
