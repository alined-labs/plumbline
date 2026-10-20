import json
from pathlib import Path
from typing import Any

import pytest

from plumbline.corpus.leases import EXPECTED, clauses, lease_disclaimer, load_expected
from plumbline.corpus.manifest import Manifest, load_manifest
from plumbline.corpus.validate import check_leases

LEASE = """# Lease

- Signed on: 2026-08-15

## Parties

Landlord: Example Rentals LLC.

## Clause 1. Premises

Apartment 1A.

## Clause 2. Waiver

The Tenant waives all rights given to tenants
by Part II of Chapter 83.

## Signatures

Signed on 2026-08-15.
"""


def ref(**overrides: Any) -> dict[str, Any]:
    row = {"jurisdiction": "florida", "law": "fl-stat-83", "article": "83.47", "edition": "2026"}
    return {**row, **overrides}


def write(root: Path, findings: list[dict[str, Any]], lease_id: str = "fl-lease-01") -> None:
    folder = root / "data" / "leases"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fl-lease-01.md").write_text(LEASE, encoding="utf-8")
    entry = {"lease_id": lease_id, "jurisdiction": "florida", "signed_on": "2026-08-15"}
    document = {"version": 1, "leases": [{**entry, "findings": findings}]}
    (folder / "expected_findings.json").write_text(json.dumps(document), encoding="utf-8")


def finding(**overrides: Any) -> dict[str, Any]:
    row = {
        "clause": "2",
        "quote": "waives all rights given to tenants by Part II",
        "issue": "A waiver of Part II rights is void.",
        "violates": ref(),
    }
    return {**row, **overrides}


def manifest() -> Manifest:
    return Manifest.model_validate(
        {
            "sources": [
                {
                    "id": "fl-stat-83-2026",
                    "law": "fl-stat-83",
                    "title": "Florida Statutes 2026, chapter 83, part II",
                    "jurisdiction": "florida",
                    "language": "en",
                    "url": "https://www.leg.state.fl.us/statutes/ch83",
                    "edition": "2026",
                    "retrieved_on": "2026-10-19",
                    "sha256": "0" * 64,
                    "format": "html",
                    "license_basis": "Public domain (government edicts doctrine)",
                    "committed": True,
                    "path": "data/corpus/raw/fl-stat-83-2026.html",
                }
            ]
        }
    )


def test_clauses_are_the_numbered_sections() -> None:
    found = clauses(LEASE)
    assert list(found) == ["1", "2"]
    assert found["2"].startswith("## Clause 2. Waiver")
    assert "Signatures" not in found["2"]


def test_a_finding_that_quotes_its_clause_and_cites_the_manifest_passes(tmp_path: Path) -> None:
    write(tmp_path, [finding()])  # the quote spans a line break in the lease
    assert check_leases(manifest(), tmp_path) == []


@pytest.mark.parametrize(
    ("bad", "problem"),
    [
        (finding(quote="waives every right"), "the quote is not in the clause"),
        (finding(clause="7"), "no such clause"),
        (finding(violates=ref(law="fl-stat-718")), "is not in the manifest"),
        (finding(violates=ref(edition="2025")), "is not in the manifest"),
        (finding(violates=ref(jurisdiction="spain")), "is not florida law"),
    ],
)
def test_a_finding_must_be_checkable(tmp_path: Path, bad: dict[str, Any], problem: str) -> None:
    write(tmp_path, [bad])
    [found] = check_leases(manifest(), tmp_path)
    assert problem in found


def test_every_lease_needs_its_entry(tmp_path: Path) -> None:
    write(tmp_path, [finding()], lease_id="fl-lease-09")
    problems = check_leases(manifest(), tmp_path)
    assert "fl-lease-01.md: no entry in expected_findings.json" in problems
    assert "fl-lease-09: expected_findings.json lists a lease with no file" in problems


def test_the_committed_leases_are_checkable() -> None:
    assert check_leases(load_manifest()) == []


def test_the_planted_violations_cover_the_plan() -> None:
    expected = load_expected(EXPECTED)
    leases = {lease.lease_id: lease for lease in expected.leases}
    assert len(leases) == 10
    assert {lease.jurisdiction.value for lease in expected.leases} == {
        "dubai",
        "spain",
        "colombia",
        "florida",
    }
    cited = {
        (f.violates.law, f.violates.article) for lease in expected.leases for f in lease.findings
    }
    planned = {
        ("dubai-dld-tenancy-guide", "Decree 43/2013 art. 1"),  # a rent increase over the cap
        ("es-lau", "36"),  # a fianza above the legal amount
        ("co-ley-820", "16"),  # a deposit Ley 820 forbids
        ("fl-stat-83", "83.47"),  # a waiver of tenant rights
        ("fl-stat-718", "718.112"),  # the association's fee and deposit
    }
    assert planned <= cited
    # The flood disclosure depends on facts a lease does not show: it is never planted.
    assert all(f.violates.article != "83.512" for lease in expected.leases for f in lease.findings)


def test_the_lease_disclaimer_says_information_and_not_advice() -> None:
    text = lease_disclaimer()
    assert text.startswith("Legal information, not legal advice.")
    assert "No lawyer has reviewed" in text
    assert "ai lawyer" not in text.lower()
    assert "\n" not in text
