"""Per-item metrics and their aggregation with confidence intervals.

Relevance is binary and judged at the article: a retrieved or cited text is relevant when
its ``ArticleRef.key`` (jurisdiction, law, article) is one of the item's gold keys, so
paragraphs and editions are ignored. Ranking metrics read the retrieved list in the order
the system returned it, after keeping only the first text of each article: three
paragraphs of one article are one hit, not three. That makes a fixed-size chunker and an
article-aware one comparable at the same k, and keeps nDCG within 0..1.

A metric that does not apply to an item is None, never 0: retrieval metrics on an item
with no gold article, generation metrics on a retrieval-only run, abstention accuracy on
an answerable item. Aggregates count only the items where the metric applies.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from rag_eval.schema import AnswerStatus, EvalResult, GoldenItem, RetrievedRef
from rag_eval.stats import paired_bootstrap, wilson_interval

RECALL_5: Final = "recall@5"
RECALL_20: Final = "recall@20"
MRR: Final = "mrr"
NDCG_10: Final = "ndcg@10"
JURISDICTION: Final = "jurisdiction@5"
CITATION_VALIDITY: Final = "citation_validity"
CITATION_PRECISION: Final = "citation_precision"
ABSTENTION: Final = "abstention_accuracy"
FALSE_ABSTENTION: Final = "false_abstention"
PARTIAL: Final = "partial_accuracy"

# Metrics that are 0 or 1 per item: their mean is a proportion, so they get a Wilson
# interval. The others are means of fractions and get a bootstrap interval.
PROPORTIONS: Final = frozenset({ABSTENTION, FALSE_ABSTENTION, PARTIAL})

JURISDICTION_DEPTH: Final = 5


def ranked_keys(retrieved: Sequence[RetrievedRef]) -> list[str]:
    """Article keys in the order returned, each kept at its first (best) position."""
    seen: set[str] = set()
    keys: list[str] = []
    for ref in retrieved:
        if ref.key not in seen:
            seen.add(ref.key)
            keys.append(ref.key)
    return keys


def recall_at_k(gold: set[str], ranked: Sequence[str], k: int) -> float:
    """Share of the gold articles found among the first k retrieved articles."""
    if not gold:
        raise ValueError("recall needs at least one gold article")
    return len(gold.intersection(ranked[:k])) / len(gold)


def reciprocal_rank(gold: set[str], ranked: Sequence[str]) -> float:
    """1 / rank of the first gold article in the whole list, 0 if none is there.

    Averaged over items this is MRR (Voorhees, TREC-8 QA track, 1999). The runner asks
    for 20 articles, so in practice it is MRR@20.
    """
    for rank, key in enumerate(ranked, start=1):
        if key in gold:
            return 1 / rank
    return 0.0


def ndcg_at_k(gold: set[str], ranked: Sequence[str], k: int) -> float:
    """Normalized discounted cumulative gain at k with binary gains (Järvelin and
    Kekäläinen, 2002): sum of 1 / log2(rank + 1) over gold articles in the first k,
    divided by the same sum for an ideal list that puts every gold article first."""
    if not gold:
        raise ValueError("nDCG needs at least one gold article")
    dcg = math.fsum(
        1 / math.log2(rank + 1) for rank, key in enumerate(ranked[:k], 1) if key in gold
    )
    ideal = math.fsum(1 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return dcg / ideal


def jurisdiction_share(jurisdictions: set[str], ranked: Sequence[str], k: int) -> float | None:
    """Share of the first k retrieved articles that belong to one of the question's
    jurisdictions; None when nothing was retrieved. A key starts with its jurisdiction."""
    top = ranked[:k]
    if not top:
        return None
    return sum(1 for key in top if key.split(":", 1)[0] in jurisdictions) / len(top)


def score_item(item: GoldenItem, result: EvalResult) -> dict[str, float | None]:
    """Every metric for one item. Definitions:

    - recall@5, recall@20, mrr, ndcg@10: the ranking metrics above, on items with gold
      articles.
    - jurisdiction@5: ``jurisdiction_share`` at depth 5, on items that name jurisdictions.
    - citation_validity: share of the answer's citations the verifier kept
      (verified / (verified + dropped)); None when the answer cites nothing.
    - citation_precision: share of the distinct verified cited articles that are gold;
      None when no citation survived verification or the item has no gold article.
    - abstention_accuracy: on items that expect an abstention, 1 if the system abstained.
    - false_abstention: on answerable items, 1 if the system abstained anyway (lower is
      better; abstention_accuracy alone would reward a system that always abstains).
    - partial_accuracy: on partial items, 1 if the answer was marked partial.

    Generation metrics are None when the run was retrieval-only (``status`` is None).
    """
    gold = {ref.key for ref in item.gold_refs}
    ranked = ranked_keys(result.retrieved)
    metrics: dict[str, float | None] = {}

    has_gold = bool(gold)
    metrics[RECALL_5] = recall_at_k(gold, ranked, 5) if has_gold else None
    metrics[RECALL_20] = recall_at_k(gold, ranked, 20) if has_gold else None
    metrics[MRR] = reciprocal_rank(gold, ranked) if has_gold else None
    metrics[NDCG_10] = ndcg_at_k(gold, ranked, 10) if has_gold else None
    names = {j.value for j in item.jurisdictions}
    metrics[JURISDICTION] = jurisdiction_share(names, ranked, JURISDICTION_DEPTH) if names else None

    status = result.status
    generated = status is not None
    total_citations = len(result.cited) + result.invalid_citations
    metrics[CITATION_VALIDITY] = (
        len(result.cited) / total_citations if generated and total_citations else None
    )
    cited = set(result.cited)
    metrics[CITATION_PRECISION] = (
        len(cited & gold) / len(cited) if generated and cited and has_gold else None
    )
    abstained = status is AnswerStatus.ABSTAINED
    metrics[ABSTENTION] = float(abstained) if generated and item.expected_abstain else None
    metrics[FALSE_ABSTENTION] = (
        float(abstained) if generated and not item.expected_abstain else None
    )
    metrics[PARTIAL] = float(status is AnswerStatus.PARTIAL) if generated and item.partial else None
    return metrics


def score(item: GoldenItem, result: EvalResult) -> EvalResult:
    """The result with its metrics filled in."""
    if item.id != result.item_id:
        raise ValueError(f"result {result.item_id} scored against item {item.id}")
    return result.model_copy(update={"metrics": score_item(item, result)})


def summarize(
    results: Sequence[EvalResult],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> dict[str, float | None]:
    """Mean of every metric over the items where it applies, with an interval.

    For each metric ``m`` the summary holds ``m`` (the mean), ``m.low`` and ``m.high``
    (the interval) and ``m.n`` (how many items it was computed on). Proportions get a
    Wilson score interval; means of fractions get a percentile bootstrap over items,
    seeded so a results file is reproducible.
    """
    names = sorted({name for result in results for name in result.metrics})
    summary: dict[str, float | None] = {}
    for name in names:
        values = [v for r in results if (v := r.metrics.get(name)) is not None]
        summary[f"{name}.n"] = float(len(values))
        if not values:
            summary[name] = summary[f"{name}.low"] = summary[f"{name}.high"] = None
            continue
        if name in PROPORTIONS:
            if any(v not in (0.0, 1.0) for v in values):
                raise ValueError(f"{name} must be 0 or 1 per item")
            low, high = wilson_interval(round(math.fsum(values)), len(values), confidence)
            mean = math.fsum(values) / len(values)
        else:
            # The bootstrap of mean(values - 0) is the bootstrap of the mean: this reuses
            # the tested paired resampler rather than writing a second one.
            boot = paired_bootstrap(
                [0.0] * len(values), values, resamples=resamples, confidence=confidence, seed=seed
            )
            mean, low, high = boot.mean, boot.low, boot.high
        summary[name], summary[f"{name}.low"], summary[f"{name}.high"] = mean, low, high
    return summary
