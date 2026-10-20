import math
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rag_eval.metrics import (
    ABSTENTION,
    CITATION_PRECISION,
    CITATION_VALIDITY,
    FALSE_ABSTENTION,
    JURISDICTION,
    MRR,
    NDCG_10,
    PARTIAL,
    RECALL_5,
    RECALL_20,
    ndcg_at_k,
    ranked_keys,
    recall_at_k,
    reciprocal_rank,
    score,
    score_item,
    summarize,
)
from rag_eval.schema import AnswerStatus, EvalResult, GoldenItem, RetrievedRef
from rag_eval.stats import wilson_interval

A = "florida:fl-stat-83:83.49"
B = "florida:fl-stat-83:83.56"
X = "florida:fl-stat-83:83.60"
S = "spain:es-lau:9"


def ref(key: str) -> dict[str, str]:
    jurisdiction, law, article = key.split(":")
    return {"jurisdiction": jurisdiction, "law": law, "article": article, "edition": "2026"}


def golden(**overrides: Any) -> GoldenItem:
    row: dict[str, Any] = {
        "id": "fl-0001",
        "question": "How long does a Florida landlord have to return a security deposit?",
        "source_language": "en",
        "jurisdictions": ["florida"],
        "category": "multi_article",
        "difficulty": "easy",
        "gold_refs": [ref(A), ref(B)],
        "reference_answer": "Fifteen days if no claim is made, under s. 83.49(3)(a).",
        "source_type": "official_faq",
        "added_in": "v0",
    }
    row.update(overrides)
    return GoldenItem.model_validate(row)


OUT_OF_SCOPE: dict[str, Any] = {
    "category": "out_of_scope",
    "expected_abstain": True,
    "gold_refs": [],
    "reference_answer": None,
}


def retrieved(*keys: str) -> list[RetrievedRef]:
    return [RetrievedRef(key=k, score=1 / n) for n, k in enumerate(keys, start=1)]


def result(*keys: str, **overrides: Any) -> EvalResult:
    return EvalResult.model_validate(
        {"item_id": "fl-0001", "retrieved": retrieved(*keys)} | overrides
    )


def test_recall_counts_gold_articles_within_k() -> None:
    ranked = [X, A, S, "florida:fl-stat-83:83.51", "florida:fl-stat-83:83.52", B]
    assert recall_at_k({A, B}, ranked, 5) == 0.5
    assert recall_at_k({A, B}, ranked, 20) == 1.0


def test_paragraphs_of_one_article_count_once() -> None:
    # Two paragraphs of A, then X, then B: as articles the list is A, X, B.
    keys = ranked_keys(retrieved(A, A, X, B))
    assert keys == [A, X, B]
    assert recall_at_k({A, B}, keys, 2) == 0.5


def test_reciprocal_rank_is_one_over_the_first_hit() -> None:
    assert reciprocal_rank({A}, [X, S, A]) == pytest.approx(1 / 3)
    assert reciprocal_rank({A}, [X, S]) == 0.0


def test_ndcg_matches_a_hand_computation() -> None:
    # Gold at ranks 2 and 4: (1/log2 3 + 1/log2 5) / (1 + 1/log2 3) = 1.06161 / 1.63093.
    assert ndcg_at_k({A, B}, [X, A, S, B], 10) == pytest.approx(0.650921, abs=1e-6)
    assert ndcg_at_k({A, B}, [A, B], 10) == 1.0
    # More gold articles than k: the ideal list is cut at k too.
    assert ndcg_at_k({A, B, X}, [A, B], 2) == 1.0


def test_retrieval_metrics_on_one_item() -> None:
    metrics = score_item(golden(), result(X, A, S, B))
    assert metrics[RECALL_5] == 1.0
    assert metrics[RECALL_20] == 1.0
    assert metrics[MRR] == 0.5
    assert metrics[NDCG_10] == pytest.approx(0.650921, abs=1e-6)
    assert metrics[JURISDICTION] == 0.75  # S is Spain; three of four are Florida


def test_retrieval_only_runs_leave_generation_metrics_empty() -> None:
    metrics = score_item(golden(), result(A))
    for name in (CITATION_VALIDITY, CITATION_PRECISION, ABSTENTION, FALSE_ABSTENTION, PARTIAL):
        assert metrics[name] is None


def test_citation_validity_and_precision() -> None:
    # Three verified citations (A twice, X once) and one dropped: validity 3/4. The
    # distinct cited articles are A and X, one of them gold: precision 1/2.
    answered = result(A, status="answered", cited=[A, A, X], invalid_citations=1)
    metrics = score_item(golden(), answered)
    assert metrics[CITATION_VALIDITY] == 0.75
    assert metrics[CITATION_PRECISION] == 0.5
    assert metrics[FALSE_ABSTENTION] == 0.0
    assert metrics[ABSTENTION] is None


def test_an_answer_without_citations_has_no_citation_metrics() -> None:
    metrics = score_item(golden(), result(A, status="answered"))
    assert metrics[CITATION_VALIDITY] is None
    assert metrics[CITATION_PRECISION] is None


def test_abstention_on_out_of_scope_items() -> None:
    item = golden(**OUT_OF_SCOPE)
    assert score_item(item, result(X, status="abstained"))[ABSTENTION] == 1.0
    answered = score_item(item, result(X, status="answered"))
    assert answered[ABSTENTION] == 0.0
    assert answered[FALSE_ABSTENTION] is None
    assert answered[RECALL_5] is None  # no gold article to find


def test_abstaining_on_an_answerable_item_is_a_false_abstention() -> None:
    assert score_item(golden(), result(A, status="abstained"))[FALSE_ABSTENTION] == 1.0


def test_partial_items_need_a_partial_answer() -> None:
    item = golden(category="partial", partial=True)
    assert score_item(item, result(A, status="partial"))[PARTIAL] == 1.0
    assert score_item(item, result(A, status="answered"))[PARTIAL] == 0.0
    assert score_item(golden(), result(A, status="partial"))[PARTIAL] is None


def test_nothing_retrieved_scores_zero_not_none() -> None:
    metrics = score_item(golden(), result())
    assert metrics[RECALL_5] == metrics[MRR] == metrics[NDCG_10] == 0.0
    assert metrics[JURISDICTION] is None


def test_score_refuses_a_mismatched_item() -> None:
    with pytest.raises(ValueError, match="scored against"):
        score(golden(id="fl-0002"), result(A))
    assert score(golden(), result(A)).metrics[RECALL_5] == 0.5


def test_summary_uses_wilson_for_proportions_and_skips_none() -> None:
    item = golden(**OUT_OF_SCOPE)
    statuses = ["abstained"] * 7 + ["answered"] * 3
    results = [score(item, result(X, status=s)) for s in statuses]
    summary = summarize(results)
    assert summary[ABSTENTION] == 0.7
    assert (summary[f"{ABSTENTION}.low"], summary[f"{ABSTENTION}.high"]) == wilson_interval(7, 10)
    assert summary[f"{ABSTENTION}.n"] == 10.0
    assert summary[FALSE_ABSTENTION] is None
    assert summary[f"{FALSE_ABSTENTION}.n"] == 0.0


def test_summary_bootstraps_means_reproducibly() -> None:
    results = [score(golden(), result(*keys)) for keys in ([A, B], [A], [X], [B, X, A])]
    first = summarize(results, resamples=2000)
    assert first == summarize(results, resamples=2000)
    # recall@5 per item: 1, 0.5, 0, 1.
    assert first[RECALL_5] == pytest.approx(0.625)
    low, high = first[f"{RECALL_5}.low"], first[f"{RECALL_5}.high"]
    assert low is not None
    assert high is not None
    assert 0.0 <= low <= 0.625 <= high <= 1.0


KEYS = [f"florida:fl-stat-83:83.{n}" for n in range(40, 52)] + [S, "dubai:dubai-26-2007:25"]
gold_sets = st.sets(st.sampled_from(KEYS), min_size=1, max_size=5)
rankings = st.lists(st.sampled_from(KEYS), max_size=len(KEYS) + 4)


@given(gold_sets, rankings, st.integers(1, 20), st.integers(0, 20))
def test_recall_is_monotone_in_k(gold: set[str], keys: list[str], k: int, more: int) -> None:
    ranked = ranked_keys(retrieved(*keys))
    assert recall_at_k(gold, ranked, k) <= recall_at_k(gold, ranked, k + more)


@given(
    gold_sets,
    rankings,
    st.none() | st.sampled_from(list(AnswerStatus)),
    st.lists(st.sampled_from(KEYS), max_size=6),
    st.integers(0, 5),
    st.sampled_from(["multi_article", "out_of_scope", "partial"]),
)
def test_every_metric_stays_within_zero_and_one(
    gold: set[str],
    keys: list[str],
    status: AnswerStatus | None,
    cited: list[str],
    invalid: int,
    category: str,
) -> None:
    jurisdictions = sorted({k.split(":")[0] for k in gold})
    if category == "out_of_scope":
        item = golden(jurisdictions=jurisdictions, **OUT_OF_SCOPE)
    else:
        refs = [ref(k) for k in sorted(gold)]
        item = golden(
            category=category,
            partial=category == "partial",
            gold_refs=refs,
            jurisdictions=jurisdictions,
        )
    scored = score(item, result(*keys, status=status, cited=cited, invalid_citations=invalid))
    for name, value in scored.metrics.items():
        assert value is None or 0.0 <= value <= 1.0, name
        assert value is None or not math.isnan(value), name
