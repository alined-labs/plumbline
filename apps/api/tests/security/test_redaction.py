"""The redactor on invented identifiers in English and Spanish, and on the ten synthetic
leases: personal data out, and what the lease checker reads (amounts, periods, dates, clause
headings, the planted findings) through unchanged. Every name and number here is made up;
the identity numbers are built to pass their checksums, so they exercise the real
recognizers rather than a weaker fallback.
"""

from __future__ import annotations

import re

import pytest

from plumbline.core.types import Language
from plumbline.corpus.leases import LEASES, Finding, Lawful, clauses, load_expected, squeeze
from plumbline.generation.router import RedactionRefused, Upload
from plumbline.security import redaction
from plumbline.security.redaction import PresidioRedactor, Span

pytestmark = pytest.mark.slow  # loads both spaCy models once per session

REDACTOR = PresidioRedactor()


def redact(text: str, language: Language = Language.EN) -> str:
    return REDACTOR.redact(Upload(text=text, language=language))


@pytest.mark.parametrize(
    ("text", "secret", "placeholder"),
    [
        ("The Tenant is Marguerite Okonkwo-Lindqvist.", "Okonkwo-Lindqvist", "<PERSON>"),
        ("Write to tenant.wren@example.org for repairs.", "tenant.wren@example.org", "<EMAIL"),
        ("Call the Landlord on (305) 555-0147 after 9 a.m.", "555-0147", "<PHONE_NUMBER>"),
        ("Tenant's Social Security number: 536-80-4398.", "536-80-4398", "<US_SSN>"),
        ("Rent goes to IBAN GB82 WEST 1234 5698 7654 32.", "GB82 WEST", "<IBAN_CODE>"),
        ("Card on file: 4111 1111 1111 1111.", "4111 1111", "<CREDIT_CARD>"),
        ("The flat at 4410 Gilded Ibis Lane, Miami.", "Gilded Ibis", "<ADDRESS>"),
        ("Tenant, born on 14 March 1991, declares.", "1991", "<DATE_OF_BIRTH>"),
        ("Tenant's passport number: X49271836.", "X49271836", "<PASSPORT>"),
        ("Emirates ID 784-1990-4827163-5 of the Tenant.", "4827163", "<AE_EMIRATES_ID>"),
    ],
)
def test_english_identifiers_become_typed_placeholders(
    text: str, secret: str, placeholder: str
) -> None:
    out = redact(text)
    assert secret not in out
    assert placeholder in out


@pytest.mark.parametrize(
    ("text", "secret", "placeholder"),
    [
        ("El arrendatario, Joaquín Ballester Nwosu, declara.", "Ballester", "<PERSON>"),
        ("Con NIF 12345678Z, el arrendador firma.", "12345678Z", "<ES_NIF>"),
        ("Con NIE X1234567L, la arrendataria firma.", "X1234567L", "<ES_NIE>"),
        ("Identificado con cédula de ciudadanía No. 1.020.345.678.", "345", "<CO_CEDULA>"),
        ("Identificada con C.C. 52.871.904 de Bogotá.", "871", "<CO_CEDULA>"),
        ("Domicilio en Calle del Yarumo Blanco No. 8-15, Bogotá.", "Yarumo", "<ADDRESS>"),
        ("Fecha de nacimiento: 03/07/1988.", "1988", "<DATE_OF_BIRTH>"),
        ("Teléfono de contacto +34 612 345 678.", "612 345", "<PHONE_NUMBER>"),
        ("Pago a la cuenta ES91 2100 0418 4502 0005 1332.", "0418 4502", "<IBAN_CODE>"),
    ],
)
def test_spanish_identifiers_become_typed_placeholders(
    text: str, secret: str, placeholder: str
) -> None:
    out = redact(text, Language.ES)
    assert secret not in out
    assert placeholder in out


def test_spanish_identifiers_are_found_in_an_english_lease() -> None:
    out = redact("The Landlord, NIF 12345678Z, and the Tenant, NIE X1234567L, sign.")
    assert "12345678Z" not in out
    assert "X1234567L" not in out


@pytest.mark.parametrize(
    "clause",
    [
        "The application fee is $150 per applicant, refunded within 60 days.",
        "This lease is signed on 2026-03-01 and runs from 1 April 2026 to 31 March 2027.",
        "The deposit is two months' rent, EUR 2,300, returned within one month.",
        "The rent is AED 96,000 a year, paid in four cheques of AED 24,000.",
        "La renta es de 1.800.000 pesos al mes, pagaderos dentro de los cinco primeros días.",
        "Notice must be given at least 30 days before the end of any monthly period.",
    ],
)
def test_amounts_periods_and_dates_pass_through_exactly(clause: str) -> None:
    language = Language.ES if clause.startswith("La ") else Language.EN
    assert redact(clause, language) == clause


@pytest.mark.parametrize(
    "heading",
    ["## Clause 5. Deposit (fianza)", "Cláusula quinta.", "## Clause 12. Notices", "Section 4(b)"],
)
def test_clause_headings_are_never_redacted(heading: str) -> None:
    out = redact(f"{heading}\nNotices go to Ignatius Fairweather-Mbeki.")
    assert out.startswith(heading)
    assert "Fairweather-Mbeki" not in out


def test_the_jurisdictions_and_the_parties_roles_stay() -> None:
    text = "The Landlord and the Tenant agree that Florida law governs, as Part II of Chapter 83, Florida Statutes provides."
    assert redact(text) == text


def test_a_failure_refuses_the_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(text: str, language: Language) -> list[Span]:
        raise RuntimeError("model missing")

    monkeypatch.setattr(redaction, "find", broken)
    with pytest.raises(RedactionRefused) as refused:
        redact("Anything at all.")
    # Nothing of the inner error rides along to a log line.
    assert refused.value.__cause__ is None
    assert refused.value.__suppress_context__


@pytest.mark.parametrize(
    ("heading", "identifier"),
    [
        ("## Clause 5. Ignatius Fairweather-Mbeki", "Fairweather-Mbeki"),
        ("# Lease between Priyanka Osei-Lindqvist and Rafael Mbeki", "Mbeki"),
        ("## Clause 2. Notices to ignatius.fm@example.org", "ignatius.fm@example.org"),
    ],
)
def test_a_heading_line_keeps_its_label_and_loses_what_identifies(
    heading: str, identifier: str
) -> None:
    first = redact(f"{heading}\nThe rent is paid monthly.").splitlines()[0]
    assert identifier not in first
    if "Clause" in heading:
        assert first.startswith(heading[: heading.index(".") + 1])


def test_names_in_capitals_are_redacted() -> None:
    text = (
        "Tenant: Priyanka Osei-Lindqvist, of Miami.\n\n"
        "SIGNED BY THE TENANT: PRIYANKA OSEI-LINDQVIST\n"
        "LANDLORD: RAFAEL MBEKI-HOLLOWAY"
    )
    out = redact(text)
    for name in ("OSEI-LINDQVIST", "Osei-Lindqvist", "MBEKI-HOLLOWAY"):
        assert name not in out


LEASE_IDS = [lease.lease_id for lease in load_expected().leases]


@pytest.mark.parametrize("lease_id", LEASE_IDS)
def test_a_synthetic_lease_loses_its_parties_and_keeps_its_findings(lease_id: str) -> None:
    expected = next(lease for lease in load_expected().leases if lease.lease_id == lease_id)
    original = (LEASES / f"{lease_id}.md").read_text(encoding="utf-8")
    out = REDACTOR.redact(Upload(text=original, language=Language.EN, synthetic=True))

    # Every heading line, and so every clause number, is exactly as written.
    headings = re.compile(r"^#+ .*$", re.MULTILINE)
    assert headings.findall(out) == headings.findall(original)
    # The people named as parties are gone (companies may stay: they are not personal data).
    parties = re.findall(r"^(?:Tenant|Co-signer)[^:]*: ([^,.\n]+)", original, re.MULTILINE)
    assert parties
    for name in parties:
        assert name not in out
    # Each planted finding's words survive in its clause, so the checker can still find it.
    redacted = clauses(out)
    planted: list[Finding | Lawful] = [*expected.findings, *expected.lawful]
    for finding in planted:
        assert squeeze(finding.quote) in squeeze(redacted[finding.clause]), finding.clause


def test_spans_are_cut_back_around_a_protected_range() -> None:
    text = "## Clause 5. John Smith"
    span = Span(0, len(text), "PERSON")
    assert redaction._outside(span, [(0, 12)], text) == [Span(13, 23, "PERSON")]
    assert redaction._outside(Span(3, 9, "PERSON"), [(0, 12)], text) == []


def test_overlapping_spans_merge_under_the_longer() -> None:
    spans = [Span(10, 40, "ADDRESS"), Span(30, 36, "LOCATION"), Span(50, 55, "PERSON")]
    assert redaction._merge(spans) == [Span(10, 40, "ADDRESS"), Span(50, 55, "PERSON")]
    assert redaction.apply("x" * 60, redaction._merge(spans)).count("<") == 2


@pytest.mark.parametrize(
    "reference",
    [
        "as amended by Law No. (33) of 2008",
        "under Ley 820 de 2003",
        "Decree No. (43) of 2013 on rent increases",
        "as s. 83.49(3) requires",
    ],
)
def test_references_to_the_law_are_never_redacted(reference: str) -> None:
    assert reference in redact(f"This lease is governed {reference}.")


def test_a_name_found_once_is_redacted_everywhere() -> None:
    text = (
        "Tenants: Priyanka Osei-Lindqvist and Rafael Mbeki.\n\nSigned by Priyanka Osei-Lindqvist."
    )
    out = redact(text)
    assert "Osei-Lindqvist" not in out
    assert "Mbeki" not in out


def test_the_kept_names_match_in_any_case() -> None:
    assert redact("Lease id: dubai-lease-01") == "Lease id: dubai-lease-01"


def test_a_name_taken_for_an_organisation_still_goes_and_a_company_stays() -> None:
    out = redact("Deposits are held at Coastal Fern Bank for Ignatius Fairweather-Mbeki.")
    assert "Coastal Fern Bank" in out
    assert "Fairweather-Mbeki" not in out
