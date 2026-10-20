"""Scoring the lease checker on the synthetic leases (data/leases): their planted findings
are the answer key, and their lawful lookalikes are traps.

A flag is a finding of severity conflict or check: what the page puts first. A planted
finding is caught when a flag lands on its clause and cites the article it violates
(ArticleRef.key, jurisdiction:law:article, so a paragraph finer than the article does not
matter, as in the retrieval metrics). Precision is the share of flags that catch a planted
finding; recall the share of planted findings caught. A flag on a lawful lookalike is a
false positive counted apart as well, since it is the error the leases were built to
provoke. A planted finding flagged on its clause but citing another article is counted in
`on_clause`, which separates a missed article (often retrieval's) from a missed clause.
Notes and matches are not flags. Totals are pooled over the leases and carry their
95% Wilson intervals: ten leases are a small test.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from plumbline.corpus.leases import ExpectedLease
from plumbline.leases.schema import Finding, Severity
from rag_eval.stats import wilson_interval

FLAGS: Final = frozenset({Severity.CONFLICT, Severity.CHECK})
_LABEL: Final = re.compile(r"^(clause|cl[aá]usula|article|art[ií]culo|section)\s+", re.IGNORECASE)


def clause_key(number: str) -> str:
    """A clause number however it was written: "Clause 9." and "9" are the same clause."""
    return _LABEL.sub("", " ".join(number.split())).rstrip(".:) ").casefold()


@dataclass(frozen=True)
class LeaseScore:
    lease_id: str
    planted: int
    caught: int
    on_clause: int  # planted findings with a flag on their clause, whatever it cites
    flags: int
    true_flags: int
    lawful_flagged: int  # lookalikes flagged: false positives the lease was built to provoke
    lawful: int

    @property
    def precision(self) -> float | None:
        return self.true_flags / self.flags if self.flags else None

    @property
    def recall(self) -> float | None:
        return self.caught / self.planted if self.planted else None


def score_lease(expected: ExpectedLease, findings: Sequence[Finding]) -> LeaseScore:
    flags = [
        (clause_key(f.clause_number), {c.ref.key for c in f.citations})
        for f in findings
        if f.severity in FLAGS
    ]
    planted = [(clause_key(p.clause), p.violates.key) for p in expected.findings]
    caught = sum(any(c == clause and key in keys for c, keys in flags) for clause, key in planted)
    flagged = {c for c, _ in flags}
    on_clause = sum(clause in flagged for clause, _ in planted)
    true_flags = sum(
        any(c == clause and key in keys for clause, key in planted) for c, keys in flags
    )
    lawful_clauses = {clause_key(lawful.clause) for lawful in expected.lawful}
    lawful_flagged = len(lawful_clauses & flagged)
    return LeaseScore(
        lease_id=expected.lease_id,
        planted=len(planted),
        caught=caught,
        on_clause=on_clause,
        flags=len(flags),
        true_flags=true_flags,
        lawful_flagged=lawful_flagged,
        lawful=len(lawful_clauses),
    )


@dataclass(frozen=True)
class Pooled:
    value: float | None
    low: float
    high: float
    hits: int
    total: int


def pooled(scores: Sequence[LeaseScore]) -> dict[str, Pooled]:
    """Precision, recall and the lookalike false-positive rate over all leases together."""

    def rate(hits: int, total: int) -> Pooled:
        low, high = wilson_interval(hits, total)
        return Pooled(hits / total if total else None, low, high, hits, total)

    return {
        "precision": rate(sum(s.true_flags for s in scores), sum(s.flags for s in scores)),
        "recall": rate(sum(s.caught for s in scores), sum(s.planted for s in scores)),
        "lookalikes_flagged": rate(
            sum(s.lawful_flagged for s in scores), sum(s.lawful for s in scores)
        ),
    }
