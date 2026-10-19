"""Parsing (Lane D): one ParsedDocument per corpus source. The ingest job writes each to
data/processed/<source_id>.json, committed, so every lane rebuilds the index without
running the parser.

- An HTML source is read in code (plumbline.ingest.html) as one page.
- A PDF is read page by page, so ParsedPage.number is always the page in the file. A page
  with a text layer goes to docling-serve, one page per request: docling's page-break
  marker skips empty pages, so splitting a whole-document conversion on it would misnumber
  every page after a blank one. A blank page (nothing drawn on it) is kept as an empty page.
  A page with content but no text layer, a scan, is transcribed by a vision model
  (plumbline.ingest.vision); without one, such a page is an error, never an empty page.
- docling labels some lines as page furniture (running headers and footers) and leaves
  them out of its Markdown. On a statute page a misjudged line is lost law, so each page's
  Markdown is checked against the words of its text layer; below MIN_COVERAGE the page
  keeps the raw text layer instead, and the swap is logged. Lines that repeat on most
  pages ("Law No. (26) of 2007 ... Page 2 of 10") are furniture docling is right to drop,
  so they are left out of that check: on a short last page they alone are over a tenth.

Every docling and vision call goes through the cache (kind "parse"), keyed by the file's
sha256, the page and the options, so tests and other lanes replay them without either.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Final

import httpx
import pypdfium2 as pdfium

from plumbline.cache import Fresh, ResponseCache
from plumbline.core.types import ParsedDocument, ParsedPage, ParseMethod
from plumbline.corpus.manifest import Source
from plumbline.ingest import html
from plumbline.ingest.vision import VisionReader

log = logging.getLogger(__name__)

DOCLING_VERSION: Final = "1.37.0"  # the docling image in compose.yaml; a test keeps them equal
DOCLING: Final = f"docling-serve {DOCLING_VERSION}"
DOCLING_OPTIONS: Final = {
    "from_formats": ["pdf"],
    "to_formats": ["md"],
    "do_ocr": False,  # only pages with a text layer reach docling
    "do_table_structure": True,
    "table_mode": "accurate",
    "image_export_mode": "placeholder",
    "include_images": False,
    "abort_on_error": True,
}
IMAGE_PLACEHOLDER: Final = "<!-- image -->"
MIN_TEXT_CHARS: Final = 20  # fewer non-space characters than this: no text layer
MIN_COVERAGE: Final = 0.9  # share of the text layer's words docling must keep
FURNITURE_SHARE: Final = 0.5  # a line on at least this share of the pages is furniture


class ParseError(RuntimeError):
    """A source could not be parsed into a complete document."""


@dataclass(frozen=True)
class PdfPage:
    number: int  # 1-based
    text: str  # the text layer; "" when the page has none
    blank: bool  # nothing at all is drawn on the page


def read_pdf(data: bytes) -> list[PdfPage]:
    pdf = pdfium.PdfDocument(data)
    try:
        pages = []
        for index in range(len(pdf)):
            page = pdf[index]
            text = _normalize_newlines(page.get_textpage().get_text_bounded())
            blank = not has_text_layer(text) and next(page.get_objects(), None) is None
            pages.append(PdfPage(index + 1, text, blank))
        return pages
    finally:
        pdf.close()


def has_text_layer(text: str) -> bool:
    return len("".join(text.split())) >= MIN_TEXT_CHARS


def furniture(pages: list[PdfPage]) -> frozenset[str]:
    """The text-layer lines that repeat on most pages of a document of three or more: its
    running headers and footers. Digits are masked, so "Page 2 of 10" and "Page 3 of 10"
    count as one line."""
    if len(pages) < 3:
        return frozenset()
    seen: Counter[str] = Counter()
    for page in pages:
        seen.update({_mask(line) for line in page.text.splitlines() if line.strip()})
    return frozenset(line for line, n in seen.items() if n >= FURNITURE_SHARE * len(pages))


def coverage(reference: str, candidate: str) -> float:
    """The share of `reference`'s words, counted with repeats, that `candidate` also has."""
    wanted = Counter(_words(reference))
    if not wanted:
        return 1.0
    missing = wanted - Counter(_words(candidate))
    return 1 - sum(missing.values()) / sum(wanted.values())


class DoclingClient:
    """POST /v1/convert/source on docling-serve, one PDF page per call, through the cache."""

    def __init__(
        self,
        url: str,
        cache: ResponseCache,
        http: httpx.Client | None = None,
        timeout_s: float = 600,
    ) -> None:
        self.url = url.rstrip("/")
        self.cache = cache
        self.http = http or httpx.Client(timeout=timeout_s)

    def page_markdown(self, data: bytes, sha256: str, page: int) -> str:
        request = {"model": DOCLING, "sha256": sha256, "page": page, "options": DOCLING_OPTIONS}

        def convert() -> Fresh:
            body = {
                "options": {**DOCLING_OPTIONS, "page_range": [page, page]},
                "sources": [
                    {
                        "kind": "file",
                        "base64_string": base64.b64encode(data).decode("ascii"),
                        "filename": f"{sha256}.pdf",
                    }
                ],
            }
            response = self.http.post(f"{self.url}/v1/convert/source", json=body)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "success":
                raise ParseError(f"docling failed on page {page}: {payload.get('errors')}")
            return Fresh(response={"md_content": payload["document"]["md_content"] or ""})

        markdown: str = self.cache.call("parse", request, convert).response["md_content"]
        return markdown


def parse_source(
    source: Source, data: bytes, docling: DoclingClient, vision: VisionReader | None = None
) -> ParsedDocument:
    """The source's file, parsed. `data` must be the file the manifest hashed."""
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != source.sha256:
        raise ParseError(
            f"{source.id}: the file's sha256 is {sha256}, the manifest's {source.sha256}"
        )
    if source.format == "html":
        text = html.to_markdown(html.decode(data), html.profile_for(str(source.url)))
        pages = [ParsedPage(number=1, method=ParseMethod.HTML, markdown=text)]
        parser = html.READER
    elif source.format == "pdf":
        pdf_pages = read_pdf(data)
        repeated = furniture(pdf_pages)
        pages = [
            _pdf_page(source, data, sha256, page, repeated, docling, vision) for page in pdf_pages
        ]
        parser = DOCLING
    else:
        raise ParseError(f"{source.id}: no reader for {source.format} sources")
    return ParsedDocument(
        source_id=source.id,
        law=source.law,
        jurisdiction=source.jurisdiction,
        language=source.language,
        edition=source.edition,
        sha256=sha256,
        parser=parser,
        pages=pages,
    )


def _pdf_page(
    source: Source,
    data: bytes,
    sha256: str,
    page: PdfPage,
    repeated: frozenset[str],
    docling: DoclingClient,
    vision: VisionReader | None,
) -> ParsedPage:
    source_id, number, layer = source.id, page.number, page.text
    if page.blank:
        log.info("%s page %d: blank", source_id, number)
        return ParsedPage(number=number, method=ParseMethod.TEXT_LAYER, markdown="")
    if not has_text_layer(layer):
        if vision is None:
            raise ParseError(f"{source_id}: page {number} has no text layer and no vision reader")
        markdown = vision.page_markdown(data, sha256, number, source.language)
        log.info("%s page %d: %s", source_id, number, ParseMethod.VISION.value)
        return ParsedPage(number=number, method=ParseMethod.VISION, markdown=markdown)
    markdown = _clean(docling.page_markdown(data, sha256, number))
    body = "\n".join(line for line in layer.splitlines() if _mask(line) not in repeated)
    kept = coverage(body, markdown)
    if kept < MIN_COVERAGE:
        lost = sorted((Counter(_words(body)) - Counter(_words(markdown))).elements())
        log.warning(
            "%s page %d: docling kept %.0f%% of the text layer's words, so the page keeps "
            "the raw text layer (lost: %s)",
            source_id,
            number,
            kept * 100,
            " ".join(lost[:12]),
        )
        markdown = layer.strip()
    log.info("%s page %d: %s", source_id, number, ParseMethod.TEXT_LAYER.value)
    return ParsedPage(number=number, method=ParseMethod.TEXT_LAYER, markdown=markdown)


def _clean(markdown: str) -> str:
    lines = [line for line in markdown.splitlines() if line.strip() != IMAGE_PLACEHOLDER]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _mask(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.casefold().split()))


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())
