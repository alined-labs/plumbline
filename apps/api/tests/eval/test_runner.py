from pathlib import Path

import pytest

from plumbline.core.types import Answer, AnswerTrace, Chunk, Citation, DemoTier, Language, Retrieved
from plumbline.eval.runner import RunError, answer_result, select_items
from rag_eval.schema import (
    AnswerStatus,
    ArticleRef,
    Category,
    GoldenItem,
    Jurisdiction,
    Split,
    load_golden,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden_fixture.jsonl"
REF = ArticleRef(jurisdiction=Jurisdiction.FLORIDA, law="fl-stat-83", article="83.49", edition="x")


@pytest.fixture
def items() -> list[GoldenItem]:
    return load_golden(GOLDEN)


def citation(n: int, *, verified: bool) -> Citation:
    return Citation(
        n=n,
        chunk_id=f"c{n}",
        ref=REF,
        label="Fla. Stat. § 83.49",
        quote="fifteen days",
        language=Language.EN,
        verified=verified,
    )


def test_dev_selects_only_dev_items(items: list[GoldenItem]) -> None:
    assert [i.id for i in select_items(items, "dev", final_test_run=False)] == [
        "fl-0001",
        "es-0001",
        "du-0001",
    ]


def test_the_test_split_needs_the_final_flag(items: list[GoldenItem]) -> None:
    with pytest.raises(RunError, match="once, in Phase 13"):
        select_items(items, "test", final_test_run=False)
    assert [i.id for i in select_items(items, "test", final_test_run=True)] == ["co-0001"]


def test_all_is_refused_once_a_file_has_a_test_split(items: list[GoldenItem]) -> None:
    with pytest.raises(RunError, match="has a test split"):
        select_items(items, "all", final_test_run=False)
    unsplit = [i for i in items if i.split.value == "dev"]
    assert len(select_items(unsplit, "all", final_test_run=False)) == 3


def test_the_final_flag_is_only_for_the_test_split(items: list[GoldenItem]) -> None:
    with pytest.raises(RunError, match="only to --split test"):
        select_items(items, "dev", final_test_run=True)


def test_an_empty_split_names_the_splits_present(items: list[GoldenItem]) -> None:
    unsplit = [i.model_copy(update={"split": Split.UNASSIGNED}) for i in items]
    with pytest.raises(RunError, match="'unassigned': 4"):
        select_items(unsplit, "dev", final_test_run=False)


def test_lease_checks_are_not_questions(items: list[GoldenItem]) -> None:
    lease = items[0].model_copy(update={"id": "fl-0100", "category": Category.LEASE_CHECK})
    chosen = select_items([*items, lease], "dev", final_test_run=False)
    assert "fl-0100" not in [i.id for i in chosen]


def test_an_item_another_file_puts_in_test_is_refused(items: list[GoldenItem]) -> None:
    with pytest.raises(RunError, match="test items elsewhere"):
        select_items(items, "dev", final_test_run=False, test_ids={"es-0001"})
    unsplit = [i.model_copy(update={"split": Split.UNASSIGNED}) for i in items]
    with pytest.raises(RunError, match="test items elsewhere"):
        select_items(unsplit, "all", final_test_run=False, test_ids={"co-0001"})


def hit(article: str, score: float) -> Retrieved:
    chunk = Chunk(
        id=f"c-{article}-{score}",
        document_id="fl",
        jurisdiction=Jurisdiction.FLORIDA,
        law="fl-stat-83",
        language=Language.EN,
        edition="x",
        article=article,
        label=f"s. {article}",
        text="t",
        text_for_search="t",
    )
    return Retrieved(chunk=chunk, rank=1, score=score)


def test_an_answer_is_scored_with_the_passages_its_generator_read() -> None:
    answer = Answer(
        text=" Fifteen days [1]. ",
        status=AnswerStatus.ANSWERED,
        citations=[citation(1, verified=True), citation(2, verified=False)],
        invalid_citations=1,
    )
    trace = AnswerTrace(
        request_id="eval-fl-0001",
        config_name="A2",
        config_hash="0" * 64,
        route="fast",
        model="m",
        tier=DemoTier.FULL,
        cost_usd=0.002,
        retrieved=[hit("83.49", 0.9), hit("83.60", 0.5), hit("83.49", 0.4)],
    )
    result = answer_result("fl-0001", answer, trace, 12.5)
    assert result.answer == "Fifteen days [1]."
    assert result.cited == [REF.key]  # the rejected citation counts only as invalid
    assert result.invalid_citations == 1
    assert result.status is AnswerStatus.ANSWERED
    assert (result.cost_usd, result.trace_id, result.latency_ms) == (0.002, "eval-fl-0001", 12.5)
    # Each article once, at its best place: what the generator was given.
    assert [(r.key, r.score) for r in result.retrieved] == [
        ("florida:fl-stat-83:83.49", 0.9),
        ("florida:fl-stat-83:83.60", 0.5),
    ]
