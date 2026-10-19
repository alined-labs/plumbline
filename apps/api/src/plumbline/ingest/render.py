"""PDF pages as PNG images, with pypdfium2 (Apache-2.0 or BSD; PyMuPDF is AGPL). The
project has no imaging library, and a PNG needs none: it is a header, the pixel rows
compressed with zlib, and an end marker, each chunk with its CRC."""

from __future__ import annotations

import struct
import zlib

import pypdfium2 as pdfium

POINTS_PER_INCH = 72  # PDF user space
COLOR_TYPES = {"L": 0, "RGB": 2}  # PNG colour types for the bitmap modes rendered here


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
