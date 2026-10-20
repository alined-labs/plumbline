"""Calibration: how often the judge agrees with a person's labels, with intervals.

Reviewed line by line before merge. The judge's verdicts count as evidence only once we
know how far they agree with a careful person, measured as two rates:

- TPR: of the answers the person passed, the share the judge passes too.
- TNR: of the answers the person failed, the share the judge fails too.

Accuracy alone would hide a judge that passes everything when most answers pass. Each
rate carries its 95% Wilson interval: from about 50 labels a rate is uncertain by roughly
ten points either way, and a bare percentage hides that. The bar (PLAN, Phase 6) is both
point estimates at 0.80 or above, aiming for 0.90; the intervals are reported beside them,
never dropped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from rag_eval.stats import wilson_interval

BAR: Final = 0.80


@dataclass(frozen=True)
class Rate:
    hits: int
    total: int
    low: float  # 95% Wilson interval
    high: float

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None


@dataclass(frozen=True)
class Agreement:
    criterion: str
    tpr: Rate
    tnr: Rate

    def meets(self, bar: float = BAR) -> bool:
        """Both point estimates reach the bar. A rate with no labels behind it fails: a
        judge is not calibrated on answers nobody labelled."""
        rates = (self.tpr.value, self.tnr.value)
        return all(rate is not None and rate >= bar for rate in rates)


def agreement(criterion: str, pairs: Sequence[tuple[bool, bool]]) -> Agreement:
    """Agreement over (person passed, judge passed) pairs, one per labelled answer that the
    judge also scored. Answers either side left out belong in neither count."""
    judge_on_passed = [judge for person, judge in pairs if person]
    judge_on_failed = [judge for person, judge in pairs if not person]
    return Agreement(
        criterion=criterion,
        tpr=_rate(sum(judge_on_passed), len(judge_on_passed)),
        tnr=_rate(sum(not judge for judge in judge_on_failed), len(judge_on_failed)),
    )


def _rate(hits: int, total: int) -> Rate:
    low, high = wilson_interval(hits, total)
    return Rate(hits=hits, total=total, low=low, high=high)
