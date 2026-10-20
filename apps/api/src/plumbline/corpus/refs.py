"""Where an ArticleRef points in the pinned file.

The golden set and the lease findings name articles by number. `article_exists` looks the
article up in the source's own text, so a wrong number cannot enter the benchmark, and
`article_text` reads it, so a reviewer sees the pinned wording beside the claim. A source that
is not on this machine (a fetch-only one, where `make fetch` has not run) cannot be looked up:
the answer is then None, and CI, which never fetches, checks the committed sources only.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Final

import pypdfium2 as pdfium

from plumbline.corpus.fetch import element
from plumbline.corpus.manifest import Source
from plumbline.settings import ROOT

# The Ley de Propiedad Horizontal numbers its articles in words, as the BOE prints them.
LPH_ORDINALS: Final = (
    "primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "séptimo", "octavo", "noveno",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho",
    "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro",
)  # fmt: skip
# The DLD guide reproduces three laws, whose article numbers repeat, so its articles are named
# by the law they sit in: "Decree 43/2013 art. 1".
GUIDE_ARTICLE: Final = re.compile(
    r"^Decree (?P<number>\d+)/(?P<year>\d{4}) art\. (?P<article>\d+)$"
)
SCRIPT: Final = re.compile(r"(?is)<(script|style)\b.*?</\1>")


@lru_cache(maxsize=16)
def _text(path: Path, encoding: str) -> str:
    """The file's text as its publisher wrote it. An HTML page loses its scripts, which hold
    earlier wordings of articles (the Senado's note boxes) that are not the law."""
    data = path.read_bytes()
    if path.suffix == ".pdf":
        pdf = pdfium.PdfDocument(data)
        try:
            return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        finally:
            pdf.close()
    text = data.decode(encoding, errors="replace")
    return SCRIPT.sub(" ", text) if path.suffix == ".html" else text


def article_exists(source: Source, article: str, root: Path = ROOT) -> bool | None:
    """Whether `article` is in the source's file, or None when the file is not here."""
    path = root / source.path
    if not path.is_file():
        return None
    law = source.law
    text = _text(path, "cp1252" if law.startswith("co-ley-") else "utf-8")
    if law.startswith("fl-stat-"):
        return f'<span class="SectionNumber">{article}&#x2003;' in text
    if law == "es-lau":
        return f'titulo="Artículo {article}"' in text
    if law == "es-lph":
        if not article.isdigit() or not 1 <= int(article) <= len(LPH_ORDINALS):
            return False
        return f'titulo="Artículo {LPH_ORDINALS[int(article) - 1]}"' in text
    if law.startswith("co-ley-"):
        # The pages write accents as entities (ART&Iacute;CULO) and may use a non-breaking space.
        heading = rf"ART[ÍI]CULO[\s\xa0]+{re.escape(article)}[oº°]?\."
        return re.search(heading, html.unescape(text)) is not None
    if law == "dubai-dld-tenancy-guide":
        named = GUIDE_ARTICLE.match(article)
        if named is None:
            return False
        start = text.find(f"Decree No. ({named['number']}) of {named['year']}")
        return start >= 0 and f"Article ({named['article']})" in text[start : start + 4000]
    if law.startswith("dubai-law-"):
        return re.search(rf"\nArticle \({re.escape(article)}\)\s*\n", text) is not None
    return None


def article_text(
    source: Source, article: str, as_of: date | None = None, root: Path = ROOT
) -> str | None:
    """The pinned wording of `article`, for a reviewer, or None when the article or the file
    is not here. A Spanish article is read as it stood on `as_of` (the edition's own date by
    default), with the norm that set that wording; its amendment notes are left out. An
    article that appears twice in a file (Law No. (33) of 2008 has two Article (2)) is read in
    each place, one after the other."""
    path = root / source.path
    if not path.is_file() or article_exists(source, article, root) is not True:
        return None
    law = source.law
    if law.startswith("fl-stat-"):
        marker = f'<div class="Section"><span class="SectionNumber">{article}&#x2003;'.encode()
        fragment = element(path.read_bytes(), marker).decode("utf-8")
        # Each subsection and paragraph starts a line, so its number can be found.
        text = re.sub(r"</div>|<br\s*/?>", "\n", re.sub(r"<div\b", "\n<div", fragment))
        return _tidy(html.unescape(re.sub(r"<[^>]+>", "", text)))
    if law in {"es-lau", "es-lph"}:
        return _boe_article(path, source, article, as_of)
    text = _text(path, "cp1252" if law.startswith("co-ley-") else "utf-8")
    if law.startswith("co-ley-"):
        return _senado_article(html.unescape(text), article)
    if law == "dubai-dld-tenancy-guide":
        named = GUIDE_ARTICLE.match(article)
        start = text.find(f"Decree No. ({named['number']}) of {named['year']}") if named else -1
        return _pdf_article(text[start:], named["article"]) if named else None
    return _pdf_article(text, article)


def _tidy(text: str) -> str:
    """Whitespace squeezed: one space between words, one line break between paragraphs."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _boe_article(path: Path, source: Source, article: str, as_of: date | None) -> str | None:
    day = (as_of or source.consolidated_on or date.max).strftime("%Y%m%d")
    name = LPH_ORDINALS[int(article) - 1] if source.law == "es-lph" else article
    root = ET.fromstring(path.read_bytes())  # noqa: S314 (a committed file whose hash is pinned)
    for block in root.iter("bloque"):
        if block.get("titulo") != f"Artículo {name}":
            continue
        chosen = None
        for version in block.findall("version"):
            effective = version.get("fecha_vigencia") or ""
            if effective and effective <= day:
                chosen = version
        if chosen is None:
            return None
        paragraphs = [
            "".join(child.itertext())
            for child in chosen
            if child.tag != "blockquote" and "".join(child.itertext()).strip()
        ]
        header = f"[{chosen.get('id_norma')}, in force from {chosen.get('fecha_vigencia')}]"
        return header + "\n" + _tidy("\n".join(paragraphs))
    return None


def _senado_article(text: str, article: str) -> str | None:
    text = re.sub(r"(?is)<table\b.*?</table>", " ", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?i)</p>|<br\s*/?>", "\n", text)))
    for label in (
        "Resumen de Notas de Vigencia", "Notas de Vigencia", "Jurisprudencia Vigencia",
        "Legislación Anterior", "Notas del Editor", "Concordancias", "Doctrina Concordante",
    ):  # fmt: skip
        text = text.replace(label, " ")
    start = re.search(rf"ART[ÍI]CULO[\s\xa0]+{re.escape(article)}[oº°]?\.", text)
    if start is None:
        return None
    following = re.search(r"\n\s*ART[ÍI]CULO[\s\xa0]+\d+[oº°]?\.", text[start.end() :])
    end = start.end() + following.start() if following else len(text)
    block = text[start.start() : end]
    # A chapter heading sits between two articles: it belongs to the next one, not to this.
    return _tidy(re.split(r"\n\s*CAP[ÍI]TULO\s+[IVXLC]+\.?\s*\n", block)[0])


def _pdf_article(text: str, article: str) -> str | None:
    heading = re.compile(rf"\nArticle \({re.escape(article)}\)\s*\n")
    following = re.compile(r"\nArticle \(\d+\)\s*\n")
    found = []
    for start in heading.finditer(text):
        end = following.search(text, start.end())
        found.append(_tidy(text[start.start() : end.start() if end else len(text)]))
    return "\n---\n".join(found) or None


MARKER: Final = re.compile(r"\([0-9a-z]+\)|[0-9]+|[a-z]\)")


def paragraph_text(text: str, paragraph: str) -> str | None:
    """The cited paragraph(s) of an article's text, or None when they cannot be found.

    `paragraph` is what an ArticleRef carries, such as "(11)", "(2)(k)", "1", "e)" or
    "(3)(a), (3)(b)": alternatives separated by commas, each a chain of markers from the outer
    to the inner paragraph. Each is found by its marker at the start of a line, and runs until
    the next line that opens a paragraph of the same kind.
    """
    found = []
    for alternative in paragraph.split(","):
        chain = MARKER.findall(alternative)
        excerpt = _excerpt(text.splitlines(), chain) if chain else None
        if excerpt is not None and excerpt not in found:
            found.append(excerpt)
    return "\n---\n".join(found) or None


def _opens(line: str, marker: str) -> str | None:
    """What follows `marker` when the line opens with it, or None."""
    if marker[0] == "(":
        return line[len(marker) :] if line.startswith(marker) else None
    if marker.endswith(")"):
        return line[len(marker) :] if line.startswith(marker) else None
    opened = re.match(rf"{re.escape(marker)}(?=[.)\s]|$)[.)]?", line)
    return line[opened.end() :] if opened else None


def _excerpt(lines: list[str], chain: list[str]) -> str | None:
    start = 0
    rest = ""
    for position, marker in enumerate(chain):
        for index in range(start, len(lines)):
            # The inner marker may follow the outer one on the same line ("(11)(a) If ...").
            candidate = rest.lstrip() if position and index == start else lines[index]
            after = _opens(candidate, marker)
            if after is not None:
                start, rest = index, after
                break
        else:
            return None
    kind = _kind(chain[-1])
    end = next(
        (i for i in range(start + 1, len(lines)) if _kind_of_line(lines[i]) == kind), len(lines)
    )
    return "\n".join(lines[start:end])


def _kind(marker: str) -> str:
    if marker[0] == "(":
        return "(n)" if marker[1:-1].isdigit() else "(a)"
    return "a)" if marker.endswith(")") else "1."


def _kind_of_line(line: str) -> str | None:
    for marker in MARKER.findall(line[:6]):
        if line.startswith(marker):
            return _kind(marker)
    return None
