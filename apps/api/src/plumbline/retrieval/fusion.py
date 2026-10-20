"""Reciprocal Rank Fusion and the parent-article merge, as plain functions: the reference
the retrieval SQL must reproduce, and the step that hands generation whole articles.

Reciprocal Rank Fusion (Cormack, Clarke and Büttcher, SIGIR 2009) scores an item by the
sum, over the rankings it appears in, of 1 / (k + rank), ranks counted from 1. It reads
only the order of each leg, so the dense leg's cosine and the keyword leg's BM25 never
need calibrating against each other; k damps the weight of the very top ranks (60 in the
paper and in configuration A2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Fused:
    id: str
    score: float
    ranks: tuple[int | None, ...]  # its rank in each input ranking, None where absent

    @property
    def best_rank(self) -> int:
        return min(r for r in self.ranks if r is not None)


def rrf(rankings: Sequence[Sequence[str]], k: int) -> list[Fused]:
    """Every item of the rankings, best first.

    Equal sums are frequent (rank 3 in one leg against rank 3 in the other), so ties are
    broken by the better best rank, then by id: the order is a function of the rankings
    alone, and the SQL orders by the same three keys. The sum is exactly rounded
    (math.fsum), so equal real sums are equal floats whatever the legs' order; with two
    legs it is the SQL's single float8 addition bit for bit, and with three (A6) an exact
    tie can differ there by one unit in the last place. A ranking lists each id once, as
    a leg of the SQL does; a repeat is an error.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    positions: dict[str, list[int | None]] = {}
    for leg, ranking in enumerate(rankings):
        for rank, item in enumerate(ranking, start=1):
            slots = positions.setdefault(item, [None] * len(rankings))
            if slots[leg] is not None:
                raise ValueError(f"{item} appears twice in ranking {leg}")
            slots[leg] = rank
    fused = [
        Fused(item, math.fsum(1 / (k + r) for r in ranks if r is not None), tuple(ranks))
        for item, ranks in positions.items()
    ]
    return sorted(fused, key=lambda f: (-f.score, f.best_rank, f.id))


@dataclass(frozen=True)
class Hit:
    """A retrieved chunk, in rank order: a numbered paragraph or a whole article."""

    chunk_id: str
    parent_id: str | None  # the article it belongs to; None when it is the article
    score: float


@dataclass(frozen=True)
class Article:
    """An article to hand generation, and which of its chunks matched, best first."""

    chunk_id: str
    score: float  # its best chunk's
    matched: tuple[str, ...]


def merge_parents(hits: Sequence[Hit], top_k: int) -> list[Article]:
    """Each hit stands for its article, which takes the place of its best-ranked chunk.

    An article is scored by its best chunk, not by the sum of them: a sum would favour
    long articles with many paragraphs over a short one that answers exactly. At most
    `top_k` articles, in rank order; the hits must already be in rank order.
    """
    order: list[str] = []
    best: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for hit in hits:
        article = hit.parent_id or hit.chunk_id
        if article not in matched:
            order.append(article)
            best[article] = hit.score
            matched[article] = []
        matched[article].append(hit.chunk_id)
    return [Article(a, best[a], tuple(matched[a])) for a in order[:top_k]]
