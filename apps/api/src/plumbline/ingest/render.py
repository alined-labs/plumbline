"""PDF pages as PNG images, and where a quote sits on a page, with pypdfium2 (Apache-2.0 or
BSD; PyMuPDF is AGPL). The project has no imaging library, and a PNG needs none: it is a
header, the pixel rows compressed with zlib, and an end marker, each chunk with its CRC.

PDFium is not thread-safe: a caller that renders from several threads (the API) holds
PDFIUM_LOCK around these functions.
"""

from __future__ import annotations

import struct
import threading
import zlib
from typing import NamedTuple

import pypdfium2 as pdfium

POINTS_PER_INCH = 72  # PDF user space
COLOR_TYPES = {"L": 0, "RGB": 2}  # PNG colour types for the bitmap modes rendered here
PDFIUM_LOCK = threading.Lock()


class Box(NamedTuple):
    """A rectangle on a page as fractions of its width and height, from the top left, so
    it can be drawn over a render at any scale."""

    x0: float
    y0: float
    x1: float
    y1: float


def page_count(data: bytes) -> int:
    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


def quote_boxes(data: bytes, page: int, quote: str) -> list[Box]:
    """The boxes of the first place `quote` appears on page `page` (1-based); none when it
    does not. Case and whitespace are ignored on both sides, so a quote that runs over a
    line break, where the page's text has a newline, is still found."""
    wanted = _normalize(quote)
    if not wanted:
        return []
    pdf = pdfium.PdfDocument(data)
    try:
        if not 1 <= page <= len(pdf):
            raise IndexError(f"page {page} is outside 1..{len(pdf)}")
        pdf_page = pdf[page - 1]
        width, height = pdf_page.get_size()
        text = pdf_page.get_textpage()
        # The page's characters, normalized, each with the index of the character it came
        # from, so a match in the normalized text maps back to the page's characters.
        normalized: list[str] = []
        origin: list[int] = []
        for index in range(text.count_chars()):
            char = text.get_text_range(index, 1).casefold()
            if not char or char.isspace():
                if normalized and normalized[-1] != " ":
                    normalized.append(" ")
                    origin.append(index)
                continue
            normalized.extend(char)
            origin.extend([index] * len(char))
        start = "".join(normalized).find(wanted)
        if start < 0:
            return []
        first, last = origin[start], origin[start + len(wanted) - 1]
        boxes = []
        for i in range(text.count_rects(first, last - first + 1)):
            left, bottom, right, top = text.get_rect(i)
            boxes.append(Box(left / width, 1 - top / height, right / width, 1 - bottom / height))
        return boxes
    finally:
        pdf.close()


def placeholder_png(message: str, dpi: int) -> bytes:
    """A US-letter page that says `message`, for a source this machine does not have."""
    # A PDF string ends at an unbalanced parenthesis and escapes with a backslash, so
    # neither reaches it.
    text = message.encode("cp1252", "replace").translate(None, b"\\").replace(b"(", b"[")
    text = text.replace(b")", b"]")
    stream = b"BT /F1 16 Tf 72 400 Td (" + text + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return render_png(bytes(out), 1, dpi, grayscale=True)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def render_png(data: bytes, page: int, dpi: int, *, grayscale: bool = False) -> bytes:
    """Page `page` (1-based) of the PDF `data`, rendered at `dpi`."""
    pdf = pdfium.PdfDocument(data)
    try:
        if not 1 <= page <= len(pdf):
            raise IndexError(f"page {page} is outside 1..{len(pdf)}")
        bitmap = pdf[page - 1].render(
            scale=dpi / POINTS_PER_INCH, grayscale=grayscale, rev_byteorder=True
        )
        return encode_png(
            bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.stride, bitmap.mode
        )
    finally:
        pdf.close()


def encode_png(pixels: bytes, width: int, height: int, stride: int, mode: str) -> bytes:
    """8-bit greyscale ("L") or RGB pixels, `stride` bytes per row, as a PNG file."""
    channels = {"L": 1, "RGB": 3}[mode]
    row = width * channels
    # Each row starts with its filter type; 0 leaves the row as is and lets zlib work.
    raw = b"".join(b"\x00" + pixels[y * stride : y * stride + row] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, COLOR_TYPES[mode], 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
