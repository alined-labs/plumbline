"""Properties of the metrics and the statistics that hold for every input, checked with
Hypothesis: ranges, monotonicity, the ideal ranking, and the paired statistics' symmetry
and coverage of their point estimates."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from rag_eval.metrics import ndcg_at_k, ranked_keys, recall_at_k, reciprocal_rank
from rag_eval.schema import RetrievedRef
from rag_eval.stats import mcnemar_exact, paired_bootstrap

KEYS = [f"florida:fl-stat-83:83.{n}" for n in range(40, 60)]
keys = st.sampled_from(KEYS)
rankings = st.lists(keys, max_size=30, unique=True)
golds = st.sets(keys, min_size=1, max_size=8)
depths = st.integers(min_value=1, max_value=30)


@given(golds, rankings, depths)
def test_recall_and_ndcg_stay_within_zero_and_one(
    gold: set[str], ranked: list[str], k: int
) -> None:
    assert 0.0 <= recall_at_k(gold, ranked, k) <= 1.0
    assert 0.0 <= ndcg_at_k(gold, ranked, k) <= 1.0 + 1e-12
    assert 0.0 <= reciprocal_rank(gold, ranked) <= 1.0


@given(golds, rankings, depths)
def test_recall_never_falls_as_k_grows(gold: set[str], ranked: list[str], k: int) -> None:
    assert recall_at_k(gold, ranked, k) <= recall_at_k(gold, ranked, k + 1)


@given(golds, rankings, depths)
def test_the_ideal_ranking_scores_one(gold: set[str], rest: list[str], k: int) -> None:
    ideal = sorted(gold) + [key for key in rest if key not in gold]
    assert math.isclose(ndcg_at_k(gold, ideal, k), 1.0)
    assert reciprocal_rank(gold, ideal) == 1.0
    assert recall_at_k(gold, ideal, max(k, len(gold))) == 1.0


@given(golds, rankings)
def test_moving_a_gold_article_up_never_lowers_ndcg_or_mrr(
    gold: set[str], ranked: list[str]
) -> None:
    for i in range(1, len(ranked)):
        if ranked[i] in gold and ranked[i - 1] not in gold:
            better = [*ranked[: i - 1], ranked[i], ranked[i - 1], *ranked[i + 1 :]]
            assert ndcg_at_k(gold, better, 10) >= ndcg_at_k(gold, ranked, 10) - 1e-12
            assert reciprocal_rank(gold, better) >= reciprocal_rank(gold, ranked)


@given(st.lists(keys, max_size=40))
def test_ranked_keys_keep_each_article_once_at_its_first_place(retrieved: list[str]) -> None:
    ranked = ranked_keys([RetrievedRef(key=key, score=0.0) for key in retrieved])
    assert ranked == list(dict.fromkeys(retrieved))


@settings(max_examples=30, deadline=None)
@given(st.lists(st.tuples(st.floats(0, 1), st.floats(0, 1)), min_size=1, max_size=40))
def test_the_paired_bootstrap_brackets_the_mean_difference(
    pairs: list[tuple[float, float]],
) -> None:
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    diff = paired_bootstrap(a, b, resamples=500)
    assert diff.low <= diff.mean + 1e-12
    assert diff.mean <= diff.high + 1e-12
    assert -1.0 <= diff.low <= diff.high <= 1.0
    swapped = paired_bootstrap(b, a, resamples=500)
    assert math.isclose(swapped.mean, -diff.mean, abs_tol=1e-12)


@given(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=60))
def test_mcnemar_is_symmetric_and_a_probability(pairs: list[tuple[bool, bool]]) -> None:
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    one, other = mcnemar_exact(a, b), mcnemar_exact(b, a)
    assert 0.0 <= one.p_value <= 1.0
    assert math.isclose(one.p_value, other.p_value)
    assert (one.only_a, one.only_b) == (other.only_b, other.only_a)
    assert mcnemar_exact(a, a).p_value == 1.0
