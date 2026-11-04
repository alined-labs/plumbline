"""From a parsed document to its articles, and from an article to its numbered paragraphs.

Lines before the first article (a preamble, a statement of reasons, an index) belong to
no article and are not chunked. Lines between a division heading and the next article
name the division and are not law text either. A line the reader wrote as a "> " quote is
a note, whatever it says: the readers quote every amendment note, court ruling and earlier
or later wording, and none of them is the law in force.

The BOE reader writes each version of an article after a version marker, oldest first, so
an amended article is parsed once per version, each with the dates it applied.
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

# Spanish numbers in words, as the LPH numbers its articles ("Artículo veintiuno") and
# both laws their dispositions ("Disposición adicional duodécima"): ordinals in both
# genders, then the cardinals the LPH uses from ten on.
_ORDINALS = (
    "primer", "segund", "tercer", "cuart", "quint", "sext", "séptim", "octav", "noven",
    "décim", "undécim", "duodécim", "decimotercer", "decimocuart", "decimoquint",
    "decimosext", "decimoséptim", "decimoctav", "decimonoven", "vigésim",
)  # fmt: skip
_CARDINALS = (
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
    "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
    "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve",
)  # fmt: skip
NUMBER_WORDS = {
    **{f"{stem}{end}": str(n) for n, stem in enumerate(_ORDINALS, 1) for end in "oa"},
    **{word: str(n) for n, word in enumerate(_CARDINALS, 10)},
}  # fmt: skip
DIVISION_NAMES = {"TITULO": "Título", "CAPITULO": "Capítulo", "SECCION": "Sección"}
DIVISION_RANKS = {"Título": 0, "Part": 0, "Chapter": 0, "Capítulo": 1, "Sección": 2}
REPEALED = re.compile(
    r"^\(?(Derogad|Suprimid|Sin contenido|Repealed)|^Art[íi]culo (derogado|subrogado)", re.I
)
STRUCK_DOWN = re.compile(r"^Art[íi]culo (declarado )?INEXEQUIBLE")
VERSION = re.compile(
    r"^<!-- plumbline:version block=(?P<block>\S+) norm=(?P<norm>\S*)"
    r" published=(?P<published>\S*) effective=(?P<effective>\S*) -->$"
)
MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip
_DAY = r"(\d{1,2}) de (" + "|".join(MONTHS) + r") de (\d{4})"
WITH_EFFECT = re.compile(r"con efectos de " + _DAY)
# A later wording the BOE quotes but has not consolidated yet: the current one ends then.
FUTURE = re.compile(r"^Téngase en cuenta que, con efectos de " + _DAY + r", se modifica")
# A renumbered disposición: "Anteriormente era la disposición adicional."
FORMERLY = re.compile(
    r"^Anteriormente era la disposición (?P<kind>adicional|transitoria|derogatoria|final)"
    r"(?: (?P<ord>\w+))?\.?$"
)
# Dubai: the title line of a law or decree that a source reproduces ("Decree No. (43) of
# 2013", "Law No. (33) of 2008 Amending").
LAW_TITLE = re.compile(r"^(Law|Decree) No\. ?\((\d+)\) of (\d{4})\b")
MARKER = re.compile(r"<([^<>]+)>")
STRUCK = re.compile(r"~~.*?~~")


@dataclass
class Version:
    """One BOE version of an article: its block, the norm that set its wording, and the
    day it took effect. The BOE leaves the day empty for some versions; their note says
    "con efectos de 8 de octubre de 2026", and without that the publication day is the
    earliest the wording can have applied, so the as-of filter never serves it before."""

    block: str
    norm: str
    published: str
    effective: date | None = None
    dated_by: str = "boe"  # "boe", "note" or "published": where `effective` came from

    def date_from(self, own_notes: Sequence[str]) -> None:
        """Date an undated version from the notes it adds (the BOE repeats every older
        note under each newer version, so an old "con efectos de" would date it years
        early), and never before it was published."""
        published = date.fromisoformat(self.published)
        found = [
            _day(*groups)
            for note in own_notes
            if note.startswith("Se ")
            for groups in WITH_EFFECT.findall(note)
        ]
        if found:
            self.effective, self.dated_by = max(min(found), published), "note"
        else:
            self.effective, self.dated_by = published, "published"


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
    version: Version | None = None  # Spain: the BOE version this text is
    effective_to: date | None = None  # Spain: the next version's day; exclusive

    @property
    def status(self) -> ProvisionStatus:
        # A repealed BOE version keeps its heading, and its whole body is "(Derogado)".
        only = self.body if len(self.body) == 1 else []
        lines = [self.heading or "", *only, *(marker.strip("<>") for marker in self.validity)]
        if any(STRUCK_DOWN.match(line) for line in lines):
            return ProvisionStatus.STRUCK_DOWN
        if any(REPEALED.match(line) for line in lines):
            return ProvisionStatus.REPEALED
        return ProvisionStatus.IN_FORCE

    @property
    def effective_from(self) -> date | None:
        return self.version.effective if self.version else None


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
        kind, ordinal = groups["kind"].lower(), (groups.get("ord") or "única").lower()
        article = f"D{kind[0].upper()} {NUMBER_WORDS.get(ordinal, ordinal)}"
        name = f"Disposición {kind} {ordinal}"
    else:
        article = NUMBER_WORDS.get(groups["id"].lower(), groups["id"])
        if not article[0].isdigit():
            raise ValueError(f"not an article number: {groups['id']!r}")
        name = profile.name.format(article)
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
    version: Version | None = None  # Spain: a marker read; the next line opens its article
    law: str | None = None  # Dubai: the law the source reproduces at this point
    last = 0  # Dubai: the previous article's number, to see the numbering restart
    for page in doc.pages:
        for raw in page.markdown.splitlines():
            if marker := VERSION.match(raw.strip()):
                if version is not None:
                    raise ValueError(
                        f"{doc.source_id}: version of {version.block} opens no article"
                    )
                version = Version(marker["block"], marker["norm"], marker["published"])
                version.effective = _iso(marker["effective"])
                continue
            line = clean_line(raw)
            if not line or profile.skip.match(line):
                continue
            current = articles[-1] if articles and not loose else None
            if version is None and raw.lstrip().startswith(">"):
                if current is not None:
                    current.notes.append(line)
                continue
            if profile.division.match(line):
                version = None  # the BOE versions a few divisions too (the LPH's Capítulo III)
                division = _division(line)
                rank = DIVISION_RANKS.get(division.split(" ")[0], 0)
                divisions = [d for d in divisions if DIVISION_RANKS.get(d.split(" ")[0], 0) < rank]
                divisions.append(division)
                loose = [line]
                continue
            match = None
            if version is not None or not profile.versioned:
                match = next((m for p in profile.articles if (m := p.match(line))), None)
            if match is None and raw.lstrip().startswith("#"):
                # Dubai: docling sometimes writes the heading and the article on one
                # heading line ("## Lease Contract Article (4)"). Only a Markdown heading
                # may: a body sentence ending "... in Article (9)" opens nothing.
                match = next((m for p in profile.heading_articles if (m := p.match(line))), None)
            if match is None:
                if version is not None:
                    raise ValueError(
                        f"{doc.source_id}: version of {version.block} opens no article"
                    )
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
            article.version, version = version, None
            above = current.body if current else loose
            fresh = False  # the article has a heading of its own, not one carried over
            if profile.heading_before:
                if match.groupdict().get("heading"):
                    heading, fresh = match["heading"], True
                elif above and _looks_like_heading(above[-1], profile):
                    heading, fresh = above.pop(), True
                    article.opening = f"{heading}\n{article.opening}"
                article.heading = heading
            if profile.reproduces_laws:
                number = int(article.article)
                # The first article, or the numbering restarts: maybe another law begins.
                if not articles or number <= last:
                    before, law = law, _next_law(above, doc.law, law)
                    if law != before and not fresh:
                        # A heading never carries from one law into the next.
                        heading = article.heading = None
                last = number
                if law:
                    article.article, article.name = f"{law} art. {number}", f"{law}, {article.name}"
            if match.groupdict().get("rest"):
                text, markers = (
                    split_markers(match["rest"]) if profile.markers else (match["rest"], [])
                )
                article.validity.extend(markers)
                if text:
                    article.body.append(text)
            articles.append(article)
            loose = []
    if profile.reproduces_laws:
        _number_repeats(articles)
    return _close_versions(articles)


def _iso(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _next_law(lines: list[str], own_law: str, law: str | None) -> str | None:
    """Dubai: the law whose title line is among `lines` ("Decree No. (43) of 2013" gives
    "Decree 43/2013"), or `law` when none is. The first title counts: the recitals after
    it cite other laws in the same form. A title of the source's own law, or of the law
    already current (a running header), starts nothing. A new law's title, and everything
    after it up to its first article (the recitals), leaves `lines`: it is no law text."""
    for index, line in enumerate(lines):
        if found := LAW_TITLE.match(line):
            title = f"{found[1]} {found[2]}/{found[3]}"
            own = f"dubai-{found[1].lower()}-{found[2]}-{found[3]}" == own_law
            if own or title == law:
                return law
            del lines[index:]
            return title
    return law


def _number_repeats(articles: Sequence[Article]) -> None:
    """Dubai: a number the same law uses twice keeps it the first time and carries its
    occurrence after: Law No. (33) of 2008 restates the old Article (2) and closes with
    an Article (2) of its own, which becomes "2 #2". A repeat with the same text as an
    earlier occurrence is a page parsed twice, not a second article: it keeps its number,
    so the chunker's duplicate guard refuses it."""
    seen: dict[str, list[list[str]]] = {}
    for article in articles:
        bodies = seen.setdefault(article.article, [])
        if bodies and article.body not in bodies:
            n = len(bodies) + 1
            bodies.append(article.body)
            article.article, article.name = f"{article.article} #{n}", f"{article.name} #{n}"
        elif not bodies:
            bodies.append(article.body)


def _close_versions(articles: list[Article]) -> list[Article]:
    """Spain: date each version, and end it when the next version of its block takes
    effect (versions arrive oldest first). The last version of a block ends early in two
    cases the notes state: a later wording the BOE quotes but has not consolidated yet
    ("Téngase en cuenta que, con efectos de 15 de noviembre de 2026, se modifica"), and a
    disposición renumbered into a new block ("Anteriormente era la disposición
    adicional"), which ends the old block's text where the new one begins."""
    before: dict[str, set[str]] = {}  # the notes each block's previous version carried
    for article in articles:
        if not article.version:
            continue
        older = before.get(article.version.block, set())
        if article.version.effective is None:
            article.version.date_from([n for n in article.notes if n not in older])
        before[article.version.block] = set(article.notes)
    kept: list[Article] = []
    for article, after in zip(articles, [*articles[1:], None], strict=True):
        this, following = article.version, after.version if after else None
        if this and following and following.block == this.block:
            start, end = this.effective, following.effective  # both dated above
            if start and end and end <= start:
                # Replaced the day it took effect: it never applied. Only the BOE's own
                # dates may say so; a date read from a note that lands here is wrong.
                if not this.dated_by == following.dated_by == "boe":
                    raise ValueError(f"version {this.norm} of {this.block} ends before it began")
                continue
            article.effective_to = following.effective
        elif this and this.effective:
            future = [_day(*m.groups()) for n in article.notes if (m := FUTURE.match(n))]
            if ends := [d for d in future if d > this.effective]:
                article.effective_to = min(ends)
        kept.append(article)
    _close_renumbered(kept)
    return kept


def _close_renumbered(articles: Sequence[Article]) -> None:
    for article in articles:
        found = next((m for n in article.notes if (m := FORMERLY.match(n))), None)
        if found is None or article.effective_from is None:
            continue
        ordinal = (found["ord"] or "única").lower()
        old = f"D{found['kind'][0].upper()} {NUMBER_WORDS.get(ordinal, ordinal)}"
        for earlier in articles:
            start = earlier.effective_from
            if (
                earlier.article == old
                and earlier.effective_to is None
                and start is not None
                and start < article.effective_from
            ):
                earlier.effective_to = article.effective_from


def _day(day: str, month: str, year: str) -> date:
    return date(int(year), MONTHS.index(month) + 1, int(day))


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
