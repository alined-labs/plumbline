import math

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from plumbline.retrieval.fusion import Article, Hit, merge_parents, rrf


def order(rankings: list[list[str]], k: int = 60) -> list[str]:
    return [f.id for f in rrf(rankings, k)]


def test_rrf_matches_a_hand_computation() -> None:
    # a: 1/61 + 1/62 = 0.032522; c: 1/63 + 1/61 = 0.032266; b: 1/62; d: 1/63.
    fused = rrf([["a", "b", "c"], ["c", "a", "d"]], k=60)
    assert [f.id for f in fused] == ["a", "c", "b", "d"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert fused[0].ranks == (1, 2)
    assert fused[2].ranks == (2, None)


def test_ties_go_to_the_better_best_rank_then_the_id() -> None:
    assert order([["y", "x"], ["x", "y"]]) == ["x", "y"]  # equal sums, both best at rank 1
    # With k = 1: a scores 1/2 at rank 1 alone, b 1/4 + 1/4 at rank 3 twice, y 1/2 at rank
    # 1; x and z 1/3 at rank 2. Equal sums go to the better best rank, then the id.
    assert order([["a", "x", "b"], ["y", "z", "b"]], k=1) == ["a", "y", "b", "x", "z"]


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="twice"):
        rrf([["a", "a"]], k=60)
    with pytest.raises(ValueError, match="at least 1"):
        rrf([["a"]], k=0)


IDS = [f"c{n}" for n in range(12)]
legs = st.lists(st.lists(st.sampled_from(IDS), unique=True, max_size=8), min_size=1, max_size=3)


@given(legs, st.integers(1, 200))
def test_every_item_once_in_a_total_order(rankings: list[list[str]], k: int) -> None:
    fused = rrf(rankings, k)
    assert sorted(f.id for f in fused) == sorted({i for r in rankings for i in r})
    keys = [(-f.score, f.best_rank, f.id) for f in fused]
    assert keys == sorted(keys)
    # The most an item can score is rank 1 in every leg, summed the same exact way.
    most = math.fsum([1 / (k + 1)] * len(rankings))
    assert all(0 < f.score <= most for f in fused)


@given(legs, st.integers(1, 200))
def test_the_order_of_the_legs_does_not_matter(rankings: list[list[str]], k: int) -> None:
    assert order(rankings, k) == order(rankings[::-1], k)


@given(legs, st.integers(1, 200))
def test_first_everywhere_is_first(rankings: list[list[str]], k: int) -> None:
    assume(all(rankings) and len({r[0] for r in rankings}) == 1)
    assert order(rankings, k)[0] == rankings[0][0]


@given(legs, st.integers(1, 200), st.data())
def test_moving_up_in_one_leg_never_moves_an_item_down(
    rankings: list[list[str]], k: int, data: st.DataObject
) -> None:
    leg = data.draw(st.integers(0, len(rankings) - 1))
    assume(len(rankings[leg]) >= 2)
    i = data.draw(st.integers(1, len(rankings[leg]) - 1))
    item = rankings[leg][i]
    before = order(rankings, k).index(item)
    better = [list(r) for r in rankings]
    better[leg][i - 1], better[leg][i] = better[leg][i], better[leg][i - 1]
    assert order(better, k).index(item) <= before


@given(legs)
def test_as_k_grows_an_item_in_more_legs_ranks_first(rankings: list[list[str]]) -> None:
    # With k above (legs × longest ranking), m/(k + longest) beats (m - 1)/(k + 1).
    longest = max((len(r) for r in rankings), default=1)
    fused = rrf(rankings, k=10 * len(rankings) * max(longest, 1) + 1)
    counts = [sum(r is not None for r in f.ranks) for f in fused]
    assert counts == sorted(counts, reverse=True)


def test_merge_hands_each_article_once_at_its_best_paragraph() -> None:
    hits = [
        Hit("lau-9.1", "lau-9", 0.9),
        Hit("lau-10.2", "lau-10", 0.8),
        Hit("lau-9", None, 0.7),  # the article itself, retrieved too
        Hit("lau-9.3", "lau-9", 0.6),
        Hit("lau-36", None, 0.5),  # an article without numbered paragraphs
    ]
    assert merge_parents(hits, top_k=8) == [
        Article("lau-9", 0.9, ("lau-9.1", "lau-9", "lau-9.3")),
        Article("lau-10", 0.8, ("lau-10.2",)),
        Article("lau-36", 0.5, ("lau-36",)),
    ]
    assert [a.chunk_id for a in merge_parents(hits, top_k=2)] == ["lau-9", "lau-10"]


hit_lists = st.lists(
    st.tuples(st.sampled_from(IDS), st.none() | st.sampled_from(["a1", "a2", "a3", "a4"])),
    unique_by=lambda h: h[0],
    max_size=12,
)


@given(hit_lists, st.integers(1, 10))
def test_merged_articles_are_unique_in_first_seen_order(
    pairs: list[tuple[str, str | None]], top_k: int
) -> None:
    hits = [Hit(c, p, 1 / (n + 1)) for n, (c, p) in enumerate(pairs)]
    merged = merge_parents(hits, top_k)
    first_seen = list(dict.fromkeys(h.parent_id or h.chunk_id for h in hits))
    assert [a.chunk_id for a in merged] == first_seen[:top_k]
    if len(first_seen) <= top_k:
        assert sorted(c for a in merged for c in a.matched) == sorted(h.chunk_id for h in hits)
