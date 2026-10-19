"""Abstention and partial answers: before and after generation, and the threshold's tuning."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plumbline.core.types import (
    AnswerStatus,
    ArticleRef,
    Chunk,
    GoldenItem,
    Jurisdiction,
    Language,
    RetrievalScores,
    Retrieved,
)
from plumbline.generation.abstain import (
    Decision,
    after_generation,
    before_generation,
    missing_jurisdictions,
    names,
    tune_threshold,
)
from rag_eval.schema import Category, Difficulty, SourceType, Split

ABSTAINED, PARTIAL, ANSWERED = AnswerStatus.ABSTAINED, AnswerStatus.PARTIAL, AnswerStatus.ANSWERED
DUBAI, SPAIN, FLORIDA = Jurisdiction.DUBAI, Jurisdiction.SPAIN, Jurisdiction.FLORIDA
CHUNK = Chunk(
    id="fl-83.49",
    document_id="fl-stat-83",
    jurisdiction=FLORIDA,
    law="fl-stat-83",
    language=Language.EN,
    edition="2026",
    article="83.49",
    label="Fla. Stat. § 83.49",
    text="Deposit money or advance rent.",
    text_for_search="Deposit money or advance rent.",
)
NO_NEARBY_LAW = (
    "No provision of the law Plumbline holds is close enough to this question to answer it."
)


def retrieved(*rerank: float | None) -> list[Retrieved]:
    return [
        Retrieved(chunk=CHUNK, rank=i, score=0.01, scores=RetrievalScores(rerank=r))
        for i, r in enumerate(rerank, start=1)
    ]


def test_an_unindexed_jurisdiction_abstains_before_any_model_call() -> None:
    decision = before_generation([DUBAI], [FLORIDA, SPAIN], retrieved(0.9), None)
    assert decision == Decision(ABSTAINED, "Plumbline does not hold the tenancy law of Dubai.")
    # Partly indexed: generate, and the answer becomes partial afterwards.
    assert before_generation([DUBAI, FLORIDA], [FLORIDA], retrieved(0.9), None) is None
    # Nothing asked or detected: retrieval and the threshold decide.
    assert before_generation([], [FLORIDA], retrieved(0.9), None) is None


def test_nothing_retrieved_abstains() -> None:
    decision = before_generation([FLORIDA], [FLORIDA], [], 0.5)
    assert decision == Decision(
        ABSTAINED, "No provision of the law Plumbline holds matches this question."
    )


@pytest.mark.parametrize(
    ("threshold", "scores", "abstains"),
    [
        (0.5, (0.49, 0.2), True),
        (0.5, (0.2, 0.5), False),  # the best score counts, wherever it ranks
        (None, (0.01,), False),
        (0.5, (None, None), False),  # no reranker: nothing on the threshold's scale
    ],
)
def test_the_threshold_applies_to_the_best_rerank_score(
    threshold: float | None, scores: tuple[float | None, ...], abstains: bool
) -> None:
    decision = before_generation([FLORIDA], [FLORIDA], retrieved(*scores), threshold)
    assert decision == (Decision(ABSTAINED, NO_NEARBY_LAW) if abstains else None)


@pytest.mark.parametrize(
    ("status", "reason", "verified", "missing", "expected"),
    [
        (ABSTAINED, "Pets are not covered.", 2, [], (ABSTAINED, "Pets are not covered.")),
        (
            ABSTAINED,
            None,
            0,
            [],
            (ABSTAINED, "The law Plumbline holds does not answer this question."),
        ),
        (
            ANSWERED,
            None,
            0,
            [],
            (
                ABSTAINED,
                "None of the answer's quotations could be found in the law it cites, so it "
                "cannot be relied on.",
            ),
        ),
        # The preemption pattern: the statute is cited and verified, the ordinance is not
        # indexed, so the answer is partial with the model's reason.
        (
            PARTIAL,
            "The sources do not include the county ordinance's text.",
            1,
            [],
            (PARTIAL, "The sources do not include the county ordinance's text."),
        ),
        (
            ANSWERED,
            None,
            2,
            [DUBAI],
            (PARTIAL, "Plumbline does not hold the tenancy law of Dubai."),
        ),
        (
            PARTIAL,
            "Rent caps are not covered.",
            1,
            [DUBAI],
            (
                PARTIAL,
                "Rent caps are not covered. Plumbline does not hold the tenancy law of Dubai.",
            ),
        ),
        (ANSWERED, None, 1, [], (ANSWERED, None)),
    ],
)
def test_after_generation(
    status: AnswerStatus,
    reason: str | None,
    verified: int,
    missing: list[Jurisdiction],
    expected: tuple[AnswerStatus, str | None],
) -> None:
    decision = after_generation(status, reason, verified, missing)
    assert (decision.status, decision.reason) == expected


def test_names_and_missing_jurisdictions() -> None:
    assert names([DUBAI, SPAIN, DUBAI]) == "Dubai or Spain"
    assert names([DUBAI, SPAIN, Jurisdiction.COLOMBIA]) == "Dubai, Spain or Colombia"
    assert missing_jurisdictions([DUBAI, FLORIDA, DUBAI], [FLORIDA]) == [DUBAI]


def item(n: int, abstain: bool, split: Split = Split.DEV) -> GoldenItem:
    common = {
        "id": f"t-{n:04d}",
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
        question="How long does my landlord have to return my deposit?",
        jurisdictions=[FLORIDA],
        category=Category.SINGLE_ARTICLE,
        gold_refs=[
            ArticleRef(jurisdiction=FLORIDA, law="fl-stat-83", article="83.49", edition="2026")
        ],
        reference_answer="Within 15 days if the landlord makes no claim on it.",
        **common,
    )


def scored(
    abstain: list[float | None], answer: list[float | None]
) -> list[tuple[GoldenItem, float | None]]:
    pairs = [(True, s) for s in abstain] + [(False, s) for s in answer]
    return [(item(i, a), s) for i, (a, s) in enumerate(pairs)]


def test_the_threshold_maximizes_balanced_accuracy() -> None:
    # At 0.6 all three that should abstain do, and three of the four others answer.
    assert tune_threshold(scored([0.05, 0.1, 0.3], [0.2, 0.6, 0.8, 0.9, None])) == 0.6


def test_ties_go_to_the_threshold_that_declines_least() -> None:
    # 0.3 and 0.5 both reach a balanced accuracy of 0.75.
    assert tune_threshold(scored([0.1, 0.4], [0.3, 0.5])) == 0.3


def test_tuning_refuses_anything_but_dev_and_one_sided_data() -> None:
    for split in (Split.TEST, Split.UNASSIGNED):
        pairs = [*scored([0.1], [0.9]), (item(99, False, split), 0.5)]
        with pytest.raises(ValueError, match="tune on dev only"):
            tune_threshold(pairs)
    with pytest.raises(ValueError, match="should and should not"):
        tune_threshold(scored([], [0.2, 0.9]))
    with pytest.raises(ValueError, match="should and should not"):
        tune_threshold(scored([None], [0.2, 0.9]))


@given(
    st.lists(st.floats(0, 0.49), min_size=1, max_size=10),
    st.lists(st.floats(0.5, 1), min_size=1, max_size=10),
)
def test_separable_scores_are_separated_perfectly(low: list[float], high: list[float]) -> None:
    threshold = tune_threshold(scored(list(low), list(high)))
    assert max(low) < threshold <= min(high)
