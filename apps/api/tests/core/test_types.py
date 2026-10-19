from datetime import date

import pytest
from pydantic import ValidationError

import rag_eval.schema as bench
from plumbline.core import types
from plumbline.core.types import Chunk, Jurisdiction, Language, ProvisionStatus


def chunk(**overrides: object) -> Chunk:
    fields: dict[str, object] = {
        "id": "fl-83-49-3",
        "document_id": "fl-stat-83-2026",
        "jurisdiction": Jurisdiction.FLORIDA,
        "law": "fl-stat-83",
        "language": Language.EN,
        "edition": "2026",
        "article": "83.49",
        "path": ["83.49", "(3)"],
        "label": "Fla. Stat. § 83.49(3)",
        "text": "Upon the vacating of the premises for termination of the lease...",
        "text_for_search": "[Florida | ch. 83 | s. 83.49] Upon the vacating of the premises...",
    }
    fields.update(overrides)
    return Chunk.model_validate(fields)


def test_shared_enums_are_the_benchmarks_own() -> None:
    assert types.Jurisdiction is bench.Jurisdiction
    assert types.Language is bench.Language
    assert types.AnswerStatus is bench.AnswerStatus


def test_chunk_ref_matches_the_golden_key() -> None:
    assert chunk().ref.key == "florida:fl-stat-83:83.49"


def test_in_force_on_respects_dates_and_status() -> None:
    c = chunk(effective_from=date(2024, 1, 1), effective_to=date(2026, 7, 1))
    assert not c.in_force_on(date(2023, 12, 31))
    assert c.in_force_on(date(2024, 1, 1))
    assert not c.in_force_on(date(2026, 7, 1))
    assert not chunk(status=ProvisionStatus.STRUCK_DOWN).in_force_on(date(2025, 1, 1))


def test_effective_to_must_follow_effective_from() -> None:
    with pytest.raises(ValidationError):
        chunk(effective_from=date(2025, 1, 1), effective_to=date(2025, 1, 1))


def test_contract_models_are_frozen_and_strict() -> None:
    c = chunk()
    with pytest.raises(ValidationError):
        c.article = "83.48"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        chunk(unexpected="field")


def test_a_parsed_document_joins_its_pages() -> None:
    from plumbline.core.types import ParsedDocument, ParseMethod

    doc = ParsedDocument.model_validate(
        {
            "source_id": "fl-stat-83-2026",
            "law": "fl-stat-83",
            "jurisdiction": "florida",
            "language": "en",
            "edition": "2026",
            "sha256": "a" * 64,
            "parser": "html 1",
            "pages": [
                {"number": 1, "method": ParseMethod.HTML, "markdown": "## 83.49"},
                {"number": 2, "method": ParseMethod.OCR, "markdown": "(3) ..."},
            ],
        }
    )
    assert doc.markdown == "## 83.49\n\n(3) ..."
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate({**doc.model_dump(), "pages": []})
