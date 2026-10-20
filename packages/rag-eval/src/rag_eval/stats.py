"""Exact and resampling statistics for paired system comparisons, in the standard library.

Every comparison in the results table is paired: two configurations answer the same
items, so the tests below work on per-item outcomes, never on two independent means.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return math.fsum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided exact upper bound on a rate after k events in n trials."""
    if n == 0 or k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a proportion; well behaved near 0 and 1.

    Wilson, "Probable inference, the law of succession, and statistical inference",
    JASA 22 (1927). At k = 0 the lower bound is exactly 0, and at k = n the upper bound
    exactly 1. The formula gives both algebraically, but in floating point centre - half
    lands a rounding error away for many n (for 587 and 933 of n = 1..2999), and a
    perfect score whose interval stops at 0.9999999999999999 is wrong on its face.
    """
    if not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return (0.0, 1.0)
    z = _z(confidence)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    low = 0.0 if k == 0 else max(0.0, centre - half)
    high = 1.0 if k == n else min(1.0, centre + half)
    return (low, high)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile, q in 0..100; None for no values."""
    if not values:
        return None
    if not 0 <= q <= 100:
        raise ValueError("q must be within 0..100")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class PairedDifference:
    """Mean of b minus a over paired items, with a bootstrap confidence interval."""

    mean: float
    low: float
    high: float
    n: int
    resamples: int

    @property
    def significant(self) -> bool:
        """The interval excludes zero."""
        return self.low > 0 or self.high < 0


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    *,
    resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> PairedDifference:
    """Percentile bootstrap of mean(b - a), resampling items, deterministic for a seed."""
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    if not a:
        raise ValueError("need at least one pair")
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    rng = random.Random(seed)  # noqa: S311 - statistics, not security
    means = sorted(math.fsum(rng.choices(diffs, k=n)) / n for _ in range(resamples))
    tail = (1 - confidence) / 2
    low = means[max(0, math.floor(tail * resamples))]
    high = means[min(resamples - 1, math.ceil((1 - tail) * resamples) - 1)]
    return PairedDifference(math.fsum(diffs) / n, low, high, n, resamples)


@dataclass(frozen=True)
class McNemar:
    """Exact McNemar test on paired binary outcomes."""

    only_a: int  # items a got right and b got wrong
    only_b: int  # items b got right and a got wrong
    p_value: float


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> McNemar:
    """Two-sided exact test: under no difference, discordant pairs split 50/50."""
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    discordant = only_a + only_b
    if discordant == 0:
        return McNemar(only_a, only_b, 1.0)
    p = min(1.0, 2 * binom_cdf(min(only_a, only_b), discordant, 0.5))
    return McNemar(only_a, only_b, p)


def _z(confidence: float) -> float:
    """Two-sided standard normal quantile, by bisection on erf (no SciPy)."""
    if not 0 < confidence < 1:
        raise ValueError("confidence must be within (0, 1)")
    target = confidence
    lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if math.erf(mid / math.sqrt(2)) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
