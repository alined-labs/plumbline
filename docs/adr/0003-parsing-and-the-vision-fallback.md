# ADR-0003: Read HTML in code, PDFs page by page through docling, and scans with a vision model

- Status: proposed
- Date: 2026-10-19

## Context

Every answer cites an article, and where the source is a PDF, the page the article is on. A misnumbered page puts a citation's highlight on the wrong page, and a dropped line is law the system can never retrieve. The corpus is HTML from three publishers (the BOE, Florida's Online Sunshine, the Colombian Senate) and PDFs from Dubai, which are fetched at build time and never committed.

What we measured on 2026-10-19 with docling-serve 1.37.0 on CPU:

1. Its Markdown page-break placeholder is only written between pages that have content: a five-page PDF with two blank pages came back as three segments.
2. Its layout model can label a statute line as page furniture (`page_header`), and its Markdown export leaves furniture out: on a test page, the second line of an article disappeared from the Markdown.
3. A one-page conversion takes about 2 seconds.

The three publishers' HTML is structured and stable: article headings carry their own classes (`h5.articulo` at the BOE, `span.SectionNumber` at Online Sunshine, `a.bookmarkaj` at the Senate).

## Decision

1. HTML is read in code, with no model. One profile per host names the element that holds the law and the navigation, menus and empty boxes to drop. An unknown host, a page without that element and bytes that are not the declared charset are errors. On the live pages, all 53 articles of the LAU and all 74 sections of Florida's chapter 83 come out as their own blocks.
2. PDFs are parsed page by page. pypdfium2 reads each page's text layer, and a page with one goes to docling-serve with OCR off, one page per request, so a page number is always the page in the file.
3. docling's Markdown for a page is checked against the page's text layer: if it keeps less than 90% of the layer's words, counted with repeats, the page keeps the raw text layer instead, and the swap is logged with the lost words.
4. A page with nothing drawn on it is kept as an empty page. A page with content but no text layer, a scan, is rendered at 200 dpi in greyscale and transcribed to Markdown by Gemini (the strong model, temperature 0), told to copy it verbatim in its own language and to treat its text as data. `ParsedPage.method` records `html`, `text_layer` or `vision` for every page.
5. Every docling and vision call goes through the cache (kind `parse`), keyed by the file's hash, the page and the options or instructions, never the page's pixels. Each source's parse is committed to `data/processed/<source_id>.json`, so no other lane needs docling or a key to rebuild the index.

## Consequences

- Page numbers in citations are exact, which the page renderer depends on.
- When docling misjudges furniture, the page loses its formatting, not its text. The other way round, a page whose real furniture is more than a tenth of its words keeps that furniture as text, and the chunker must tolerate it.
- docling's own OCR (`ParseMethod.ocr`) is not used: a scan goes straight to the vision model, which returns structured Markdown in one call. A page with fewer than 20 characters in its text layer counts as having none.
- Converting page by page loses docling's view across pages: a table split over two pages stays two tables. The statutes in the corpus are prose.
- Cost: about 2 seconds of CPU per PDF page for docling; a scanned page costs well under a cent (the recorded test page cost US$0.0012).
- A new HTML publisher needs a profile, and a `txt` or `md` source needs a reader; both fail loudly until they have one.

## Alternatives considered

- **docling for the HTML too.** A reader written for three stable sites is exact and deterministic and needs no service running; on these pages docling would add nothing.
- **One whole-document conversion, split on the page-break placeholder.** Measured: it misnumbers every page after a blank one.
- **docling's JSON output, grouped by each item's page.** Correct page numbers, but it means writing our own Markdown export of docling's document model.
- **docling's OCR for scans.** Not benchmarked yet. The synthetic scanned pages (task B7) are the test to compare the two on, and a reversal would be a new ADR.
- **PyMuPDF to render pages.** It is AGPL; pypdfium2 is Apache-2.0 or BSD.
