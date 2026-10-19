"""Tiny PDFs for the parser's tests, built in code so every fixture is readable here.

Each page is either lines of text (Helvetica, WinAnsi, so Spanish accents work) or None:
a page that only draws a grey box, which has no text layer, like a scanned page.
"""

from __future__ import annotations


def _escape(line: str) -> bytes:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252")


def _content(lines: list[str] | None) -> bytes:
    if lines is None:
        return b"0.5 g 72 72 451 698 re f"
    body = b"".join(b"(" + _escape(line) + b") Tj T* " for line in lines)
    return b"BT /F1 11 Tf 14 TL 72 760 Td " + body + b"ET"


def make_pdf(pages: list[list[str] | None]) -> bytes:
    """A US-letter PDF with one page per entry of `pages`."""
    count = len(pages)
    page_ids = [4 + 2 * i for i in range(count)]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % i for i in page_ids) + b"]"
        b" /Count %d >>" % count,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for page_id, lines in zip(page_ids, pages, strict=True):
        stream = _content(lines)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            b" /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (page_id + 1)
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


# A two-article statute with a blank page between the articles: the PDF whose docling
# conversions are recorded under cache/parse/.
STATUTE = make_pdf(
    [
        [
            "Artículo 1. Objeto.",
            "1. La presente ley regula el arrendamiento de fincas urbanas.",
            "2. Se aplica en todo el territorio del Estado.",
        ],
        [],
        [
            "Artículo 2. Plazo mínimo.",
            "La duración del arrendamiento será libremente pactada por las partes.",
        ],
    ]
)
