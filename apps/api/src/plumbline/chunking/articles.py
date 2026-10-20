"""From a parsed document to its articles, and from an article to its numbered paragraphs.

Lines before the first article (a preamble, a statement of reasons, an index) belong to
no article and are not chunked. Lines between a division heading and the next article
name the division and are not law text either.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date

from plumbline.chunking.profiles import PROFILES, Profile
from plumbline.chunking.text import clean_line
from plumbline.core.types import ParsedDocument, ProvisionStatus

ORDINALS = {
    "primera": "1", "segunda": "2", "tercera": "3", "cuarta": "4", "quinta": "5",
    "sexta": "6", "séptima": "7", "octava": "8", "novena": "9", "décima": "10",
}  # fmt: skip
DIVISION_NAMES = {"TITULO": "Título", "CAPITULO": "Capítulo", "SECCION": "Sección"}
DIVISION_RANKS = {"Título": 0, "Part": 0, "Chapter": 0, "Capítulo": 1, "Sección": 2}
REPEALED = re.compile(
    r"^\(?(Derogad|Suprimid|Sin contenido|Repealed)|^Art[íi]culo (derogado|subrogado)", re.I
)
STRUCK_DOWN = re.compile(r"^Art[íi]culo (declarado )?INEXEQUIBLE")
IN_FORCE_FROM = re.compile(r"en vigor a partir del (\d{2})/(\d{2})/(\d{4})")
MARKER = re.compile(r"<([^<>]+)>")
STRUCK = re.compile(r"~~.*?~~")


@dataclass
class Article:
    """An article (or section, or disposición) as the source lays it out."""

    article: str  # the bare id: "9", "9 bis", "DT 1", "83.49"
    name: str  # "Artículo 9", "Disposición transitoria primera", "s. 83.49"
    heading: str | None
    divisions: list[str]  # ["Título II", "Capítulo II"]
    page: int
    opening: str  # the line that opens it, without the text that follows the heading
    body: list[str] = field(default_factory=list)  # the law text, one line per paragraph
    notes: list[str] = field(default_factory=list)  # amendment history (Spain, Florida)
    validity: list[str] = field(default_factory=list)  # validity markers (Colombia)

    @property
    def status(self) -> ProvisionStatus:
        lines = [self.heading or "", *(marker.strip("<>") for marker in self.validity)]
        if any(STRUCK_DOWN.match(line) for line in lines):
            return ProvisionStatus.STRUCK_DOWN
        if any(REPEALED.match(line) for line in lines):
            return ProvisionStatus.REPEALED
        return ProvisionStatus.IN_FORCE

    @property
    def effective_from(self) -> date | None:
        """When the text shown came into force, from the BOE's version lines. "Última
        actualización" names the current version. Without it, the line that created the
        text ("Texto original", "Texto añadido") dates the current version only if
        nothing changed the text since: at most one "Se ..." note, its own addition.
        Otherwise the date is unknown, and None is safer than a wrong date."""
        current = [n for n in self.notes if n.startswith("Última actualización")]
        created = [n for n in self.notes if n.startswith(("Texto original", "Texto añadido"))]
        unchanged = sum(n.startswith("Se ") for n in self.notes) <= 1
        for note in current or (created if unchanged else []):
            if found := IN_FORCE_FROM.search(note):
                day, month, year = map(int, found.groups())
                return date(year, month, day)
        return None


def split_markers(line: str) -> tuple[str, list[str]]:
    """Colombia: the line without its <...> validity markers and its struck-down words,
    and the markers, verbatim."""
    found = [f"<{marker}>" for marker in MARKER.findall(line)]
    text = " ".join(STRUCK.sub("", MARKER.sub("", line)).split())
    # Removing struck words strands the punctuation around them ("servicios , siempre",
    # "su pago, ."): drop the space before it, a comma left before other punctuation, and
    # punctuation left at the start of the line.
    text = re.sub(r"([,;:])(?=[,.;:])", "", re.sub(r"\s+([,.;:])", r"\1", text))
    return text.lstrip(",.;: "), found


def _division(line: str) -> str:
    # "TÍTULO II" -> "Título II", "CAPITULO IV." -> "Capítulo IV".
    word, rest = line.rstrip(".").split(" ", 1)
    plain = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().upper()
    return f"{DIVISION_NAMES.get(plain, word.capitalize())} {rest}"


def _looks_like_heading(line: str, profile: Profile) -> bool:
    return (
        len(line.split()) <= 10
        and not line.endswith((".", ":", ";", ","))
        and not (numbering(line, profile.levels))
    )


def _open(match: re.Match[str], profile: Profile, divisions: list[str], page: int) -> Article:
    groups = match.groupdict()
    if groups.get("kind"):
        kind, ordinal = groups["kind"].lower(), groups["ord"].lower()
        article = f"D{kind[0].upper()} {ORDINALS.get(ordinal, ordinal)}"
        name = f"Disposición {kind} {ordinal}"
    else:
        article, name = groups["id"], profile.name.format(groups["id"])
    heading = groups.get("heading")
    if heading and profile.markers:
        heading = split_markers(heading)[0].rstrip(" ,") or None
    rest = match.start("rest") if groups.get("rest") is not None else len(match.string)
    opening = match.string[:rest].strip()
    if profile.markers:
        opening = split_markers(opening)[0]
    # A Spanish disposición follows the last Título but belongs to none.
    within = [] if groups.get("kind") else list(divisions)
    return Article(article, name, heading, within, page, opening)


def parse_articles(doc: ParsedDocument) -> list[Article]:
    profile = PROFILES[doc.jurisdiction]
    articles: list[Article] = []
    divisions: list[str] = []
    loose: list[str] = []  # lines outside any article, for a heading above the next one
    heading: str | None = None  # Dubai: a heading covers the articles under it
    for page in doc.pages:
        for raw in page.markdown.splitlines():
            line = clean_line(raw)
            if not line or profile.skip.match(line):
                continue
            current = articles[-1] if articles and not loose else None
            if profile.division.match(line):
                division = _division(line)
                rank = DIVISION_RANKS.get(division.split(" ")[0], 0)
                divisions = [d for d in divisions if DIVISION_RANKS.get(d.split(" ")[0], 0) < rank]
                divisions.append(division)
                loose = [line]
                continue
            match = next((m for p in profile.articles if (m := p.match(line))), None)
            if match is None:
                if current is None:
                    loose.append(line)
                elif profile.note.match(line):
                    current.notes.append(line)
                else:
                    text, markers = split_markers(line) if profile.markers else (line, [])
                    current.validity.extend(markers)
                    if text:
                        current.body.append(text)
                continue
            article = _open(match, profile, divisions, page.number)
            if profile.heading_before:
                above = current.body if current else loose
                if above and _looks_like_heading(above[-1], profile):
                    heading = above.pop()
                    article.opening = f"{heading}\n{article.opening}"
                article.heading = heading
            if match.groupdict().get("rest"):
                text, markers = (
                    split_markers(match["rest"]) if profile.markers else (match["rest"], [])
                )
                article.validity.extend(markers)
                if text:
                    article.body.append(text)
            articles.append(article)
            loose = []
    return articles


def numbering(line: str, levels: Sequence[re.Pattern[str]]) -> list[tuple[int, str]]:
    """The paragraph markers a line opens with, as (depth, marker): "(1)(a) In an
    action" gives [(0, "(1)"), (1, "(a)")]. Markers must be followed by a space, so
    "1.5 percent" opens nothing."""
    found: list[tuple[int, str]] = []
    rest, depth = line, 0
    while depth < len(levels):
        match = next(
            ((d, m) for d in range(depth, len(levels)) if (m := levels[d].match(rest))), None
        )
        if match is None:
            break
        depth, found_match = match
        found.append((depth, found_match.group(0)))
        rest, depth = rest[found_match.end() :], depth + 1
    return found if found and (not rest or rest[0].isspace()) else []


@dataclass
class Paragraph:
    markers: tuple[str, ...]  # from the article down: ("(3)", "(a)")
    lines: list[str] = field(default_factory=list)  # its own lines, before any child
    children: list[Paragraph] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.walk())

    def walk(self) -> Iterator[str]:
        yield from self.lines
        for child in self.children:
            yield from child.walk()


def paragraph_tree(body: Sequence[str], levels: Sequence[re.Pattern[str]]) -> Paragraph:
    """The article's numbered paragraphs as a tree. A line without a marker continues
    the paragraph above it, so a form or a list quoted inside (3)(a) stays in (3)(a)."""
    root = Paragraph(())
    stack: list[tuple[int, Paragraph]] = [(-1, root)]
    for line in body:
        opened = numbering(line, levels)
        for depth, marker in opened:
            while stack[-1][0] >= depth:
                stack.pop()
            child = Paragraph((*stack[-1][1].markers, marker))
            stack[-1][1].children.append(child)
            stack.append((depth, child))
        stack[-1][1].lines.append(line)
    return root
