import struct
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from plumbline.corpus.leases import LEASES
from plumbline.corpus.scans import (
    DPI,
    LINES_PER_PAGE,
    PAGE,
    SCANNED,
    SCANS,
    WIDTH,
    Scan,
    paginate,
    png,
    printed_lines,
)
from plumbline.corpus.validate import check_scans

MARKDOWN = """# Lease

- Lease id: fl-lease-99
- Signed on: 2026-08-15

## Clause 1. Premises

The Landlord leases to the Tenant Apartment 3C, with one assigned parking space,
for use as a private residence only, and for no business of any kind whatsoever.
"""


def test_a_lease_prints_as_a_typist_would() -> None:
    lines = printed_lines(MARKDOWN)
    assert lines[:5] == ["Lease", "", "- Lease id: fl-lease-99", "- Signed on: 2026-08-15", ""]
    assert lines[5] == "Clause 1. Premises"
    assert all(len(line) <= WIDTH for line in lines)
    assert " ".join(lines[7:]).startswith("The Landlord leases to the Tenant Apartment 3C, with")


def test_pages_neither_start_nor_end_blank() -> None:
    lines = [f"line {n}" if n % 5 else "" for n in range(1, 101)]
    pages = paginate(lines)
    assert all(page[0] and page[-1] for page in pages)
    assert all(len(page) <= LINES_PER_PAGE for page in pages)


def test_png_writes_an_8_bit_grayscale_image() -> None:
    data = png(3, 2, bytes([0, 128, 255, 10, 20, 30]))
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, colour) == (3, 2, 8, 0)
    start = data.index(b"IDAT") + 4
    length = struct.unpack(">I", data[start - 8 : start - 4])[0]
    assert zlib.decompress(data[start : start + length]) == b"\x00\x00\x80\xff\x00\x0a\x14\x1e"


@pytest.mark.parametrize("spec", SCANNED, ids=lambda spec: spec.lease_id)
def test_the_committed_scans_match_their_leases(spec: Scan) -> None:
    lease_id, tilts = spec.lease_id, spec.tilts
    pages = paginate(printed_lines((LEASES / f"{lease_id}.md").read_text(encoding="utf-8")))
    pdf = pdfium.PdfDocument(SCANS / f"{lease_id}.pdf")
    try:
        assert len(pdf) == len(tilts) == len(pages)
        texts = [pdf[n].get_textpage().get_text_range().strip() for n in range(len(pdf))]
    finally:
        pdf.close()
    assert texts == [""] * len(pages)  # scans: no text layer
    for number, lines in enumerate(pages, start=1):
        expected = (SCANS / f"{lease_id}-p{number}.txt").read_text(encoding="utf-8")
        assert expected == "\n".join(lines) + "\n"  # regenerate the scans when a lease changes
        image = (SCANS / f"{lease_id}-p{number}.png").read_bytes()
        width, height, depth, colour = struct.unpack(">IIBB", image[16:26])
        # PDFium rounds the pixel size its own way: within a pixel of the page at DPI.
        assert abs(width - PAGE[0] * DPI / 72) <= 1
        assert abs(height - PAGE[1] * DPI / 72) <= 1
        assert (depth, colour) == (8, 0)


def test_three_to_five_pages_in_all() -> None:
    assert 3 <= sum(len(spec.tilts) for spec in SCANNED) <= 5


def test_the_validator_wants_each_scanned_page_with_its_text_and_lease(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "leases" / "scans"
    folder.mkdir(parents=True)
    (tmp_path / "data" / "leases" / "fl-lease-03.md").write_text("# Lease\n", encoding="utf-8")
    (folder / "fl-lease-03.pdf").write_bytes(b"%PDF")
    (folder / "fl-lease-03-p1.png").write_bytes(b"png")
    assert check_scans(tmp_path) == ["fl-lease-03-p1: needs both a .png and its expected .txt"]
    (folder / "fl-lease-03-p1.txt").write_text("text\n", encoding="utf-8")
    assert check_scans(tmp_path) == []
    (folder / "co-lease-09-p1.png").write_bytes(b"png")
    (folder / "co-lease-09-p1.txt").write_text("text\n", encoding="utf-8")
    assert check_scans(tmp_path) == [
        "co-lease-09-p1: there is no lease co-lease-09.md",
        "co-lease-09: its scanned pages have no co-lease-09.pdf",
    ]


def test_the_committed_scans_pass_the_validator() -> None:
    assert check_scans() == []
