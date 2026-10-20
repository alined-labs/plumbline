"""Scoring the lease checker against the synthetic leases, and extraction on all ten."""

import asyncio
from typing import Any

import pytest

from plumbline.cache import ResponseCache
from plumbline.core.types import ArticleRef, CacheMode, Citation, Jurisdiction, Language
from plumbline.corpus.leases import load_expected
from plumbline.generation.llm import STRONG_MODEL, client_for
from plumbline.leases.extract import extract_clauses
from plumbline.leases.schema import Finding, Severity
from plumbline.leases.scoring import clause_key, pooled, score_lease
from plumbline.settings import ROOT

EXPECTED = load_expected()
LEASES = {lease.lease_id: lease for lease in EXPECTED.leases}


@pytest.mark.parametrize(
    ("written", "key"),
    [
        ("9", "9"),
        ("Clause 9.", "9"),
        ("clause  9", "9"),
        ("3.2", "3.2"),
        ("Cláusula 4", "4"),
        ("Schedule A, 3", "schedule a, 3"),
    ],
)
def test_a_clause_is_the_same_however_its_number_is_written(written: str, key: str) -> None:
    assert clause_key(written) == key


def finding(clause: str, article: str, severity: Severity = Severity.CONFLICT) -> Finding:
    ref = ArticleRef(
        jurisdiction=Jurisdiction.FLORIDA, law="fl-stat-83", article=article, edition="2026"
    )
    citation = Citation(
        n=1,
        chunk_id=f"fl-{article}",
        ref=ref,
        label=f"Fla. Stat. § {article}",
        quote="quoted text",
        language=Language.EN,
        verified=True,
    )
    return Finding(
        n=1,
        clause_number=clause,
        clause_text="The clause.",
        clause_language=Language.EN,
        severity=severity,
        title="A title",
        why="Why it matters.",
        citations=[citation],
        confidence=0.9,
    )


def test_catches_need_the_planted_clause_and_its_article() -> None:
    lease = LEASES["fl-lease-01"]  # planted: 9 (83.47), 10 (83.47), 5 (83.49); lawful: 13
    reported = [
        finding("9", "83.47"),  # caught
        finding("Clause 5.", "83.49"),  # caught, however the number was written
        finding("10", "83.49", Severity.CHECK),  # the right clause, the wrong article
        finding("13", "83.57"),  # a lawful lookalike, flagged
        finding("3", "83.49", Severity.NOTE),  # a note is not a flag
    ]
    score = score_lease(lease, reported)
    assert (score.planted, score.caught, score.flags, score.true_flags) == (3, 2, 4, 2)
    assert (score.lawful_flagged, score.lawful) == (1, 1)
    assert (score.precision, score.recall) == (0.5, 2 / 3)


def test_totals_pool_the_leases_with_intervals() -> None:
    perfect = score_lease(
        LEASES["fl-lease-01"],
        [finding("9", "83.47"), finding("10", "83.47"), finding("5", "83.49")],
    )
    empty = score_lease(LEASES["fl-lease-03"], [])
    totals = pooled([perfect, empty])
    assert (totals["recall"].hits, totals["recall"].total) == (3, 5)
    assert totals["precision"].value == 1.0
    assert totals["precision"].low < 0.5  # three flags prove little
    assert empty.precision is None  # nothing flagged: no precision, not a perfect one


def extracted(mode: CacheMode) -> dict[str, Any]:
    """Every synthetic lease through the lease route's extraction; recorded by running this file."""
    client = client_for(STRONG_MODEL, cache=ResponseCache(mode, ROOT / "cache"))

    async def run() -> dict[str, Any]:
        texts = {
            i: (ROOT / "data" / "leases" / f"{i}.md").read_text(encoding="utf-8") for i in LEASES
        }
        results = await asyncio.gather(*(extract_clauses(t, client) for t in texts.values()))
        return dict(zip(texts, results, strict=True))

    return asyncio.run(run())


def test_extraction_places_every_clause_the_answer_key_names() -> None:
    for lease_id, extraction in extracted(CacheMode.REPLAY).items():
        lease = LEASES[lease_id]
        named = {clause_key(f.clause) for f in lease.findings} | {
            clause_key(x.clause) for x in lease.lawful
        }
        found = {clause_key(c.number) for c in extraction.clauses}
        assert named <= found, (lease_id, sorted(named - found))
        assert extraction.dropped == 0, lease_id


if __name__ == "__main__":
    for lease_id, extraction in extracted(CacheMode.RECORD).items():
        numbers = [c.number for c in extraction.clauses]
        print(lease_id, "dropped", extraction.dropped, round(extraction.cost_usd, 5), numbers)
