"""How each corpus marks its structure, read from the official sources' own layout: the
line that opens an article, the divisions above it, the numbering inside it, and the lines
that annotate the law instead of being part of it.

Every pattern runs on a line already cleaned by `text.clean_line`. Paragraph markers are
kept as the source writes them ("(3)", "1.", "a)"), and each corpus's label puts them in
the form its citations use.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from plumbline.core.types import Jurisdiction

NEVER = re.compile(r"(?!)")


@dataclass(frozen=True)
class Profile:
    # Groups: "id", or "kind" and "ord" for a Spanish disposición; "heading" and "rest"
    # (text that follows the heading on the same line) when the line carries them.
    articles: tuple[re.Pattern[str], ...]
    name: str  # how the article is named in a path and a header: "Artículo {}"
    division: re.Pattern[str]  # Título, Capítulo, Sección, Chapter
    levels: tuple[re.Pattern[str], ...]  # paragraph markers, outermost first
    note: re.Pattern[str]  # amendment history: kept, out of the indexed text
    skip: re.Pattern[str]  # the source's own furniture between articles: dropped
    label: Callable[[str, str, Sequence[str]], str]  # (law name, article, markers)
    heading_before: bool = False  # the heading is the line above the article (Dubai)
    markers: bool = False  # inline <...> validity markers and ~~struck~~ text (Colombia)
    versioned: bool = False  # articles open only after a version marker (Spain's BOE reader)
    reproduces_laws: bool = False  # a source may restate other laws' articles (Dubai)
    # Patterns tried only on Markdown heading lines, with the heading in the same line.
    heading_articles: tuple[re.Pattern[str], ...] = ()


def _spain_label(law: str, article: str, markers: Sequence[str]) -> str:
    # "LAU, art. 9.1.a)"; a disposición is named without "art.": "LAU, DT 1.2".
    head = article if article[:1] == "D" else f"art. {article}"
    return f"{law}, {head}" + "".join(f".{m.rstrip('.')}" for m in markers)


def _colombia_label(law: str, article: str, markers: Sequence[str]) -> str:
    # "Ley 820 de 2003, art. 22, num. 8, lit. a)"; "..., art. 8, parágrafo".
    def name(marker: str) -> str:
        if marker[0].isdigit():
            return f"num. {marker.rstrip('.')}"
        if marker.endswith(")"):
            return f"lit. {marker}"
        return marker.rstrip(".").lower()

    return ", ".join([f"{law}, art. {article}", *map(name, markers)])


def _dubai_label(law: str, article: str, markers: Sequence[str]) -> str:
    # "Law No. 26 of 2007, Art. 25(1)"; a law the guide reproduces names itself:
    # "DLD Tenancy Guide, Decree 43/2013 art. 1(a)".
    head = article if " art. " in article else f"Art. {article}"
    return f"{law}, {head}" + "".join(f"({m.rstrip('.')})" for m in markers)


def _florida_label(law: str, article: str, markers: Sequence[str]) -> str:
    # Every Florida source is the Florida Statutes: "Fla. Stat. § 83.49(3)(a)1."
    return f"Fla. Stat. § {article}" + "".join(markers)


SPANISH_DIVISION = re.compile(r"^(T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N)\s+\S+$", re.IGNORECASE)

PROFILES: dict[Jurisdiction, Profile] = {
    # The BOE's open-data record, as its reader writes it: each version of an article after
    # a version marker, opening with "Artículo 9. Plazo mínimo.", "Artículo veintiuno."
    # (the LPH numbers in words) or "Disposición transitoria primera. Contratos ...". Only
    # the line after a marker opens an article, so a body that quotes an article of
    # another law never does. Notes on each version follow it as quotes.
    Jurisdiction.SPAIN: Profile(
        articles=(
            re.compile(
                r"^Art[íi]culo (?P<id>\d+(?: (?:bis|ter|quater|quinquies))?|[a-záéíóú]+)\.(?: (?P<heading>.+?)\.?)?$"
            ),
            re.compile(
                r"^Disposici[óo]n (?P<kind>adicional|transitoria|derogatoria|final)(?: (?P<ord>\w+))?\.?(?: (?P<heading>.+?)\.?)?$",
                re.IGNORECASE,
            ),
        ),
        name="Artículo {}",
        division=SPANISH_DIVISION,
        levels=(re.compile(r"[A-Z]\)"), re.compile(r"\d+\."), re.compile(r"[a-zñ]\)")),
        note=NEVER,
        skip=NEVER,
        label=_spain_label,
        versioned=True,
    ),
    # Secretaría del Senado: "ARTÍCULO 8o. OBLIGACIONES DEL ARRENDADOR. Son ..." with the
    # heading in capitals, or no heading ("ARTÍCULO 60. Las sanciones ...", "ARTÍCULO 40.
    # <Artículo derogado ...>"). Validity markers sit inline in angle brackets; struck-down
    # words are struck through; the headings of the collapsed note boxes have no text.
    Jurisdiction.COLOMBIA: Profile(
        articles=(
            re.compile(
                r"^ART[ÍI]CULO (?P<id>\d+)\s*[oº°]?\. (?P<heading>[^a-záéíóúüñ<]+?)\.(?: (?P<rest>.*))?$"
            ),
            re.compile(r"^ART[ÍI]CULO (?P<id>\d+)\s*[oº°]?\.(?: (?P<rest>.*))?$"),
        ),
        name="Artículo {}",
        division=re.compile(r"^CAP[ÍI]TULO [IVXLC]+\.?$", re.IGNORECASE),
        levels=(re.compile(r"\d+\.|PAR[ÁA]GRAFO(?: \d+\s*[oº°]?)?\."), re.compile(r"[a-z]\)")),
        note=NEVER,
        skip=re.compile(
            r"^(Resumen de Notas de Vigencia|Notas de Vigencia|Jurisprudencia Vigencia"
            r"|Legislación Anterior|Concordancias|Doctrina Concordante|Notas del Editor)$"
        ),
        label=_colombia_label,
        markers=True,
    ),
    # Dubai Legislation Portal (English translation): a heading line, then "Article (4)"
    # on its own; a heading covers the articles after it until the next one. The DLD's
    # guide reproduces three laws one after another, and Law No. (33) of 2008 restates
    # Law No. (26) of 2007's articles, so numbers repeat within a source.
    Jurisdiction.DUBAI: Profile(
        articles=(re.compile(r"^Article \((?P<id>\d+)\)$"),),
        name="Article {}",
        division=re.compile(r"^(Chapter|Part) \S+$", re.IGNORECASE),
        levels=(re.compile(r"\d+\."), re.compile(r"[a-z]\.")),
        note=NEVER,
        skip=NEVER,
        label=_dubai_label,
        heading_before=True,
        reproduces_laws=True,
        heading_articles=(re.compile(r"^(?P<heading>[^.;:,]{1,80}?) Article \((?P<id>\d+)\)$"),),
    ),
    # Online Sunshine: "83.49 Deposit money or advance rent; duty of landlord and tenant.—"
    # then subsections (1), paragraphs (a), subparagraphs 1. and sub-subparagraphs a.,
    # which may share a line ("(1)(a) In an action ..."). History and Note lines follow.
    Jurisdiction.FLORIDA: Profile(
        articles=(re.compile(r"^(?P<id>\d{1,3}\.\d{2,4}) (?P<heading>[^—]+?)\.?—(?P<rest>.*)$"),),
        name="s. {}",
        division=NEVER,
        levels=(
            re.compile(r"\(\d+\)"),
            re.compile(r"\([a-z]\)"),
            re.compile(r"\d+\."),
            re.compile(r"[a-z]\."),
        ),
        note=re.compile(r"^(History|Note)\.—"),
        skip=NEVER,
        label=_florida_label,
    ),
}
