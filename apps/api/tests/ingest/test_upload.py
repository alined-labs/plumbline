"""Reading an uploaded lease: what is accepted from its bytes alone, and the stable codes of
everything that is not."""

from __future__ import annotations

import io
import zipfile

import pytest

from plumbline.ingest import upload
from plumbline.ingest.upload import UploadError, read_upload

from .pdfs import make_pdf

CLAUSES = [
    "Clause 1. The Landlord lets the dwelling at 12 Example Street to the Tenant for a term",
    "of twelve months, and the Tenant shall pay the rent on the first day of each month.",
    "Clause 2. The deposit equals two months' rent and is held by the Landlord until the end.",
    "Clause 3. The Tenant keeps the dwelling clean and reports any damage without delay.",
]
LEASE = "\n".join(CLAUSES)
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(*paragraphs: str, document: str | None = None, extra: bool = True) -> bytes:
    body = document or "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{WORD}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        if extra:
            archive.writestr("word/document.xml", xml)
    return out.getvalue()


def _refused(data: bytes, code: str) -> UploadError:
    with pytest.raises(UploadError) as raised:
        read_upload(data)
    assert raised.value.code == code
    return raised.value


def test_plain_text_is_read_whatever_its_encoding() -> None:
    spanish = "Cláusula 1. El arrendador entrega la vivienda de la calle Ejemplo. " * 6
    assert read_upload(LEASE.encode()).text == LEASE
    assert read_upload(LEASE.replace("\n", "\r\n").encode()).text == LEASE  # CRLF
    assert read_upload(b"\xef\xbb\xbf" + LEASE.encode()).text == LEASE  # a UTF-8 BOM
    assert read_upload(LEASE.encode("utf-16")).text == LEASE
    assert read_upload(spanish.encode("cp1252")).text == spanish.strip()
    assert read_upload(spanish.encode()).kind == "text"


def test_a_pdf_with_a_text_layer_is_read_page_by_page() -> None:
    data = make_pdf([CLAUSES[:2], CLAUSES[2:]])
    result = read_upload(data)
    assert (result.kind, result.pages) == ("pdf", 2)
    assert "Clause 1. The Landlord lets the dwelling" in result.text
    assert result.text.index("Clause 2.") > result.text.index("Clause 1.")


def test_a_scanned_pdf_has_its_own_error() -> None:
    scan = make_pdf([None, None])  # pages that only draw something
    error = _refused(scan, "unreadable")
    assert "scan" in error.message
    assert error.status == 422


def test_a_scan_whose_pages_only_carry_page_numbers_is_still_a_scan() -> None:
    # 60 pages of "Page 12": 360 characters of text in all, but not one page of text.
    numbered = make_pdf([[f"Page {number}"] for number in range(1, 61)])
    assert len("".join(f"Page {n}" for n in range(1, 61))) > upload.MIN_CHARS
    assert "scan" in _refused(numbered, "unreadable").message


@pytest.mark.parametrize("data", [b"%PDF-1.4 truncated", b"%PDF-"])
def test_a_broken_pdf_is_unreadable_not_a_crash(data: bytes) -> None:
    assert _refused(data, "unreadable").status == 422


def test_a_pdf_of_too_many_pages_is_too_long() -> None:
    data = make_pdf([[CLAUSES[0]]] * (upload.MAX_PAGES + 1))
    assert _refused(data, "too_large").status == 413


def test_a_word_document_is_read_paragraph_by_paragraph() -> None:
    table = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Rent</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>EUR 900</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    tabbed = "<w:p><w:r><w:t>Term</w:t><w:tab/><w:t>12 months</w:t><w:br/><w:t>renewable</w:t></w:r></w:p>"
    data = _docx(
        document="".join(f"<w:p><w:r><w:t>{c}</w:t></w:r></w:p>" for c in CLAUSES) + table + tabbed
    )
    result = read_upload(data)
    assert result.kind == "docx"
    assert result.text.splitlines()[0] == CLAUSES[0]
    assert "Rent\nEUR 900" in result.text
    assert "Term\t12 months\nrenewable" in result.text


def test_a_zip_that_is_not_a_word_document_is_the_wrong_type() -> None:
    assert _refused(_docx(*CLAUSES, extra=False), "unsupported_type").status == 415


def test_a_malformed_word_document_is_unreadable() -> None:
    data = _docx(document="<w:p><w:r><w:t>never closed")
    assert _refused(data, "unreadable").status == 422


def test_a_zip_built_to_inflate_is_refused_unread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "MAX_XML_BYTES", 50_000)
    body = "<w:p><w:r><w:t>" + "a" * 200_000 + "</w:t></w:r></w:p>"
    data = _docx(document=body)
    assert len(data) < 5_000  # it deflates to almost nothing, and inflates to 200 kB
    _refused(data, "too_large")


@pytest.mark.parametrize(
    "data",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + bytes(200),  # an image
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(600),  # an old binary Word file
        bytes(range(256)) * 4,  # anything else
    ],
)
def test_other_files_are_the_wrong_type_whatever_they_are_called(data: bytes) -> None:
    error = _refused(data, "unsupported_type")
    assert "PDF" in error.message
    assert error.status == 415


def test_the_limits_are_413_and_a_near_empty_file_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "MAX_BYTES", 1000)
    assert _refused(b"x" * 1001, "too_large").status == 413
    monkeypatch.setattr(upload, "MAX_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(upload, "MAX_CHARS", 500)
    assert _refused(("A clause of the lease. " * 40).encode(), "too_large").status == 413
    assert _refused(b"Too short.", "unreadable").status == 422
