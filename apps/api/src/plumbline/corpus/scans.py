"""Scanned-looking pages for the OCR path: synthetic leases printed onto US Letter pages,
tilted slightly, rasterized in grayscale with paper grain and specks, and saved as PNG
images and as image-only PDFs (no text layer, as a scanner makes them), each page with the
text it shows.

    uv run python -m plumbline.corpus.scans

Writes data/leases/scans/: <lease_id>.pdf (every page of the lease), and per page
<lease_id>-p<n>.png and <lease_id>-p<n>.txt (the expected text, one printed line per line).
The tilt and the noise come from a seeded generator, so a run reproduces the same pages
with the same PDFium build. Only pypdfium2 and the standard library are used.
"""

from __future__ import annotations

import ctypes
import math
import random
import re
import struct
import textwrap
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from plumbline.corpus.leases import LEASES

SCANS: Final = LEASES / "scans"
PAGE: Final = (612.0, 792.0)  # US Letter, in points
MARGIN: Final = 72.0
FONT: Final = "Times-Roman"
SIZE: Final = 11.0
LEADING: Final = 14.0
WIDTH: Final = 86  # characters per printed line, which fits Times-Roman 11 pt within the margins
LINES_PER_PAGE: Final = 44
DPI: Final = 150


@dataclass(frozen=True)
class Scan:
    """One lease to print: which file, and how each of its pages is tilted, in degrees."""

    lease_id: str
    tilts: tuple[float, ...]
    seed: int


# Three to five pages in all, in two languages' worth of accents, tilted both ways.
SCANNED: Final = (
    Scan("fl-lease-03", tilts=(0.8, -1.1), seed=8303),
    Scan("co-lease-01", tilts=(-0.6, 1.3), seed=8201),
)


def printed_lines(markdown: str) -> list[str]:
    """The lease as a typist would print it: Markdown markers dropped, paragraphs wrapped,
    one blank line between them."""
    lines: list[str] = []
    for block in re.split(r"\n\s*\n", markdown.strip()):
        rows = block.splitlines()
        # A list keeps one item per line; any other block is one wrapped paragraph.
        items = rows if all(row.startswith("- ") for row in rows) else [" ".join(rows)]
        if lines:
            lines.append("")
        for item in items:
            text = re.sub(r"^#+ ", "", " ".join(item.split())).replace("`", "")
            lines.extend(textwrap.wrap(text, WIDTH) or [""])
    return lines


def paginate(lines: list[str]) -> list[list[str]]:
    """Pages of at most LINES_PER_PAGE lines, none starting or ending with a blank line."""
    pages = []
    for start in range(0, len(lines), LINES_PER_PAGE):
        page = lines[start : start + LINES_PER_PAGE]
        while page and not page[0]:
            page = page[1:]
        while page and not page[-1]:
            page = page[:-1]
        if page:
            pages.append(page)
    return pages


def render(lines: list[str], tilt: float, rng: random.Random) -> tuple[int, int, bytearray]:
    """One page, printed and rasterized: width, height and 8-bit grayscale pixels, rows
    packed without padding."""
    pdf = pdfium.PdfDocument.new()
    width, height = PAGE
    page = pdf.new_page(width, height)
    font = pdfium.PdfFont.load_standard(pdf, FONT)
    angle = math.radians(tilt)
    cos, sin = math.cos(angle), math.sin(angle)
    for number, line in enumerate(lines):
        if not line:
            continue
        text = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font.raw, ctypes.c_float(SIZE))
        wide = ctypes.create_string_buffer((line + "\x00").encode("utf-16-le"))
        if not pdfium_c.FPDFText_SetText(text, ctypes.cast(wide, pdfium_c.FPDF_WIDESTRING)):
            raise RuntimeError(f"PDFium could not set the text {line!r}")
        # Rotate each line's origin about the page's centre, and its glyphs with it.
        dx, dy = MARGIN - width / 2, height - MARGIN - number * LEADING - height / 2
        x = width / 2 + dx * cos - dy * sin
        y = height / 2 + dx * sin + dy * cos
        pdfium_c.FPDFPageObj_Transform(text, cos, sin, -sin, cos, x, y)
        pdfium_c.FPDFPage_InsertObject(page.raw, text)
    page.gen_content()
    bitmap = page.render(
        scale=DPI / 72, grayscale=True, force_bitmap_format=pdfium_c.FPDFBitmap_Gray
    )
    w, h, stride = bitmap.width, bitmap.height, bitmap.stride
    raw = bytes(bitmap.buffer)
    pixels = bytearray(b"".join(raw[row * stride : row * stride + w] for row in range(h)))
    pdf.close()
    return w, h, age(pixels, w, h, rng)


def age(pixels: bytearray, width: int, height: int, rng: random.Random) -> bytearray:
    """Make a clean render look scanned: ink that is not quite black, paper that is not
    quite white, the scanner's banding, a few specks, and a shadow along one edge. The
    banding varies from row to row, not pixel to pixel, so the pages still compress."""
    tone = bytes(28 + value * 211 // 255 for value in range(256))
    offset = 0
    for y in range(height):
        if y % 3 == 0:
            offset = rng.choice((0, 0, 0, 2, 4, 7))
        row = pixels[y * width : (y + 1) * width].translate(tone)
        pixels[y * width : (y + 1) * width] = bytes(max(0, v - offset) for v in row)
    for _ in range(width * height // 2500):
        x, y = rng.randrange(width), rng.randrange(height)
        for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1))[: rng.randrange(1, 5)]:
            if x + ox < width and y + oy < height:
                pixels[(y + oy) * width + x + ox] = rng.randrange(40, 120)
    shadow = rng.randrange(6, 14)
    for y in range(height):
        for x in range(shadow):
            pixels[y * width + x] = pixels[y * width + x] * (6 + x) // (6 + shadow)
    return pixels


def png(width: int, height: int, pixels: bytes) -> bytes:
    """An 8-bit grayscale PNG, unfiltered, written with the standard library."""
    rows = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def image_pdf(pages: list[tuple[int, int, bytearray]]) -> bytes:
    """A PDF whose pages are images only, so it has no text layer to read."""
    pdf = pdfium.PdfDocument.new()
    width, height = PAGE
    for w, h, pixels in pages:
        page = pdf.new_page(width, height)
        buffer = (ctypes.c_ubyte * len(pixels)).from_buffer(pixels)
        bitmap = pdfium.PdfBitmap.new_native(w, h, pdfium_c.FPDFBitmap_Gray, buffer=buffer)
        image = pdfium.PdfImage.new(pdf)
        image.set_bitmap(bitmap)
        image.set_matrix(pdfium.PdfMatrix().scale(width, height))
        page.insert_obj(image)
        page.gen_content()
    target = _Bytes()
    pdf.save(target)
    pdf.close()
    return bytes(target.data)


class _Bytes:
    """A writable sink for PdfDocument.save."""

    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, chunk: bytes) -> int:
        self.data.extend(chunk)
        return len(chunk)


def scan(spec: Scan, folder: Path = SCANS) -> list[Path]:
    markdown = (LEASES / f"{spec.lease_id}.md").read_text(encoding="utf-8")
    pages = paginate(printed_lines(markdown))
    if len(pages) != len(spec.tilts):
        raise ValueError(f"{spec.lease_id} prints on {len(pages)} pages, not {len(spec.tilts)}")
    rng = random.Random(spec.seed)  # noqa: S311 (noise in a picture, not a secret)
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rendered = []
    for number, (lines, tilt) in enumerate(zip(pages, spec.tilts, strict=True), start=1):
        page = render(lines, tilt, rng)
        rendered.append(page)
        stem = folder / f"{spec.lease_id}-p{number}"
        stem.with_suffix(".png").write_bytes(png(page[0], page[1], bytes(page[2])))
        stem.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += [stem.with_suffix(".png"), stem.with_suffix(".txt")]
    pdf_path = folder / f"{spec.lease_id}.pdf"
    pdf_path.write_bytes(image_pdf(rendered))
    return [pdf_path, *written]


def main() -> int:
    for spec in SCANNED:
        for path in scan(spec):
            print(path.relative_to(LEASES.parent.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
