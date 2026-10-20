"""Reading the BOE's consolidated-legislation open data (Source.format "xml") into Markdown
without a parser model (ParseMethod.HTML): the Spanish statutes, with every version of
every article and the dates each wording applied.

The record is texto/bloque/version: a bloque is one article, heading, preamble or
signature; each of its versions holds the wording one norm (id_norma) gave it, published
on fecha_publicacion and applying from fecha_vigencia. The Markdown keeps the shape of the
BOE's own web page, which the chunker already reads, and adds the versions:

- An article (tipo "precepto") is written once per version, in the BOE's order (oldest
  first), each preceded by one marker line the chunker turns into effective dates:

      <!-- plumbline:version block=a9 norm=BOE-A-2019-3108 published=2019-03-05 effective=2019-03-06 -->

  `effective=` is empty when the BOE gives no date (the date is then only in the
  version's note). A wording applies until the next version's effective date.
- Headings, the preamble and the signature are written once, in their latest wording,
  without a marker.
- Article headings become "##### ", the headings of títulos and capítulos "#### ",
  paragraphs plain blocks, and the BOE's notes (amendments, "Téngase en cuenta", earlier
  or later wordings they quote) "> " quotes: notes are never the law in force.

The file is untrusted input: Python's XML parser (expat 2.4.1 or later) neither expands entities
recursively nor fetches external ones.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import Final

READER: Final = "plumbline boe-xml 1"  # ParsedDocument.parser; bump it when the output changes
HEADINGS: Final = frozenset(
    {"titulo", "titulo_num", "titulo_tit", "capitulo", "capitulo_num", "capitulo_tit"}
    | {"seccion", "subseccion", "anexo", "anexo_num", "anexo_tit"}
)
ARTICLE: Final = "articulo"
VERSIONED: Final = "precepto"


class BoeError(ValueError):
    """The record is not a consolidated text the reader understands."""


def to_markdown(data: bytes) -> str:
    try:
        root = ET.fromstring(data)  # noqa: S314 (expat expands no entities recursively)
    except ET.ParseError as exc:
        raise BoeError(f"not well-formed XML: {exc}") from exc
    texto = root.find("data/texto")
    if texto is None:
        raise BoeError("no data/texto element: not a consolidated-legislation record")
    blocks: list[str] = []
    for bloque in texto.iter("bloque"):
        versions = bloque.findall("version")
        if not versions:
            continue
        if bloque.get("tipo") == VERSIONED:
            for version in versions:
                blocks.append(_marker(bloque, version))
                blocks.extend(_blocks(version))
        else:
            blocks.extend(_blocks(versions[-1]))
    return "\n\n".join(blocks)


def _marker(bloque: ET.Element, version: ET.Element) -> str:
    fields = {
        "block": bloque.get("id", ""),
        "norm": version.get("id_norma", ""),
        "published": _date(version.get("fecha_publicacion", "")),
        "effective": _date(version.get("fecha_vigencia", "")),
    }
    return "<!-- plumbline:version " + " ".join(f"{k}={v}" for k, v in fields.items()) + " -->"


def _date(value: str) -> str:
    """The BOE's YYYYMMDD as ISO 8601; "" stays ""."""
    if not value:
        return ""
    if len(value) != 8 or not value.isdigit():
        raise BoeError(f"unexpected BOE date {value!r}")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _blocks(element: ET.Element, quote: str = "") -> Iterator[str]:
    """The Markdown blocks of a version's children, in order."""
    for child in element:
        if child.tag == "blockquote":
            yield from _blocks(child, quote + "> ")
        elif child.tag == "table":
            for row in child.iter("tr"):
                cells = [_text(cell) for cell in row if cell.tag in {"td", "th"}]
                if any(cells):
                    yield quote + " | ".join(cells)
        elif child.tag == "p":
            text = _text(child)
            if not text:
                continue
            css = child.get("class", "")
            prefix = "##### " if css == ARTICLE else "#### " if css in HEADINGS else ""
            yield quote + prefix + text
        else:
            yield from _blocks(child, quote)


def _text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())
