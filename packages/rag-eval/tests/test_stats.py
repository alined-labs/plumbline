import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rag_eval.stats import (
    binom_cdf,
    clopper_pearson_upper,
    mcnemar_exact,
    paired_bootstrap,
    percentile,
    wilson_interval,
)


def test_binom_cdf_matches_known_values() -> None:
    assert binom_cdf(0, 10, 0.5) == pytest.approx(1 / 1024)
    assert binom_cdf(5, 10, 0.5) == pytest.approx(638 / 1024)
    assert binom_cdf(10, 10, 0.3) == 1.0
    assert binom_cdf(-1, 10, 0.3) == 0.0


def test_clopper_pearson_zero_events_is_the_rule_of_three() -> None:
    # With no events in n, the one-sided 95% bound is 1 - 0.05 ** (1 / n).
    assert clopper_pearson_upper(0, 30) == pytest.approx(1 - 0.05 ** (1 / 30), abs=1e-6)
    assert clopper_pearson_upper(3, 3) == 1.0


def test_wilson_interval_matches_a_reference() -> None:
    low, high = wilson_interval(5, 10)
    assert (low, high) == (pytest.approx(0.2366, abs=1e-4), pytest.approx(0.7634, abs=1e-4))
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_percentile_is_nearest_rank() -> None:
    values = [15.0, 20.0, 35.0, 40.0, 50.0]
    assert percentile(values, 50) == 35.0
    assert percentile(values, 95) == 50.0
    assert percentile([], 50) is None
    with pytest.raises(ValueError, match="q must be"):
        percentile(values, 101)


def test_paired_bootstrap_is_deterministic_and_detects_a_clear_gain() -> None:
    a = [0.0] * 40 + [1.0] * 60
    b = [1.0] * 90 + [0.0] * 10
    first = paired_bootstrap(a, b, resamples=2000, seed=7)
    assert first == paired_bootstrap(a, b, resamples=2000, seed=7)
    assert first.mean == pytest.approx(0.3)
    assert first.significant


def test_paired_bootstrap_on_identical_systems_is_not_significant() -> None:
    a = [1.0, 0.0] * 50
    assert not paired_bootstrap(a, a, resamples=500).significant


def test_paired_samples_must_align() -> None:
    with pytest.raises(ValueError, match="same length"):
        paired_bootstrap([1.0], [1.0, 0.0])
    with pytest.raises(ValueError, match="same length"):
        mcnemar_exact([True], [True, False])


def test_mcnemar_exact_counts_discordant_pairs() -> None:
    a = [False] * 10 + [True] * 20
    b = [True] * 10 + [True] * 20
    result = mcnemar_exact(a, b)
    assert (result.only_a, result.only_b) == (0, 10)
    assert result.p_value == pytest.approx(2 * 0.5**10)
    assert mcnemar_exact(a, a).p_value == 1.0


@given(st.lists(st.floats(min_value=0, max_value=1), min_size=2, max_size=60), st.integers(0, 99))
def test_the_interval_brackets_the_mean(values: list[float], seed: int) -> None:
    shifted = [min(1.0, v + 0.1) for v in values]
    result = paired_bootstrap(values, shifted, resamples=300, seed=seed)
    assert result.low <= result.mean + 1e-9
    assert result.mean <= result.high + 1e-9
    assert not math.isnan(result.mean)


@pytest.mark.parametrize("n", [1, 2, 3, 7, 10, 49, 50, 100, 120, 1000, 99991])
def test_wilson_interval_is_exactly_closed_at_zero_and_n(n: int) -> None:
    low, high = wilson_interval(0, n)
    assert low == 0.0
    assert 0.0 < high < 1.0
    low, high = wilson_interval(n, n)
    assert high == 1.0
    assert 0.0 < low < 1.0
    # The two ends mirror each other.
    assert wilson_interval(0, n)[1] == pytest.approx(1 - wilson_interval(n, n)[0])


@pytest.mark.parametrize(("k", "n"), [(-1, 5), (6, 5)])
def test_wilson_interval_refuses_impossible_counts(k: int, n: int) -> None:
    with pytest.raises(ValueError, match="0 <= k <= n"):
        wilson_interval(k, n)


@given(
    st.integers(min_value=0, max_value=500).flatmap(
        lambda n: st.tuples(st.integers(0, n), st.just(n))
    )
)
def test_the_wilson_interval_holds_its_estimate(counts: tuple[int, int]) -> None:
    k, n = counts
    low, high = wilson_interval(k, n)
    assert 0.0 <= low <= high <= 1.0
    if n:
        assert low <= k / n <= high
        assert (low == 0.0) == (k == 0)
        assert (high == 1.0) == (k == n)
