"""Reading the HTML statute sources without a parser model (ParseMethod.HTML): the BOE's
consolidated texts, Florida's Online Sunshine chapters and the Colombian Senate's laws,
each turned into Markdown with one block per paragraph.

Each site has a profile: the element that holds the law, and the elements inside it that
are navigation, forms, a table of contents or empty boxes. A host without a profile is an
error, because reading a whole page would mix menus into the law. The pages are old and
not always well formed (Colombia's opens one container inside another and never closes
it), so an element ends at its matching end tag or, failing that, at the end of the page.
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

READER = "plumbline html 1"  # ParsedDocument.parser; bump it when the output changes


class HtmlError(ValueError):
    """The page cannot be read: unknown site, undecodable bytes or no law container."""


@dataclass(frozen=True)
class Profile:
    container: str  # the id of the element that holds the law
    skip: frozenset[str] = frozenset()  # "tag", "tag.class", ".class" or "#id"


PROFILES: dict[str, Profile] = {
    # div.marcadores is a jump menu listing every article. Each article sits in a div.bloque;
    # p.bloque is the "[Bloque 14: #a9]" label above it.
    "www.boe.es": Profile("textoxslt", frozenset({"div.marcadores", "p.bloque", "p.linkSubir"})),
    # div.CatchlineIndex is each part's table of contents: it repeats every section title.
    "www.leg.state.fl.us": Profile("statutes", frozenset({"div.CatchlineIndex"})),
    # The validity boxes are empty tables that a script fills in; only their labels are here.
    # a.antsig links to the law's previous and next pages: a long law spans several pages.
    "www.secretariasenado.gov.co": Profile(
        "aj_data",
        frozenset(
            {
                "#update_date",
                "#selector_aj",
                "#imprimir",
                "#logo_aj",
                "a.hlk_inicio",
                "a.antsig",
                "a.caja_vja_encabezado",
                "a.caja_vja_encabezado_c",
                "table",
            }
        ),
    ),
}
ALWAYS_SKIPPED = frozenset(
    {"head", "title", "script", "style", "noscript", "form", "nav", "button", "select", "iframe"}
)
VOID = frozenset({"br", "hr", "img", "input", "meta", "link", "wbr", "col", "area", "source"})
BLOCKS = frozenset(
    {"p", "div", "li", "tr", "blockquote", "table", "ul", "ol", "center", "dt", "dd", "pre"}
    | {f"h{n}" for n in range(1, 7)}
)
CELLS = frozenset({"td", "th"})


def profile_for(url: str) -> Profile:
    host = urlsplit(url).hostname or ""
    try:
        return PROFILES[host]
    except KeyError:
        raise HtmlError(f"no HTML profile for {host}: add one to plumbline.ingest.html") from None


def decode(raw: bytes) -> str:
    """The page's text, in the charset it declares (UTF-8 when it declares none). As in
    browsers, ISO-8859-1 is read as Windows-1252, its superset."""
    declared = re.search(rb"""charset=["']?([A-Za-z0-9_-]+)""", raw[:4096])
    name = declared.group(1).decode("ascii") if declared else "utf-8"
    try:
        codec = codecs.lookup(name).name
    except LookupError as exc:
        raise HtmlError(f"unknown charset {name}") from exc
    if codec in {"latin-1", "iso8859-1"}:
        codec = "cp1252"
    try:
        return raw.decode(codec)
    except UnicodeDecodeError as exc:
        raise HtmlError(f"the page is not valid {codec}: {exc}") from exc


def to_markdown(html: str, profile: Profile) -> str:
    reader = _Reader(profile)
    reader.feed(html)
    reader.close()
    if not reader.found:
        raise HtmlError(f"no element with id {profile.container!r} in the page")
    reader.flush()
    return "\n\n".join(reader.blocks)


def _matches(selector: str, tag: str, classes: set[str], element_id: str | None) -> bool:
    if selector.startswith("#"):
        return selector[1:] == element_id
    name, _, cls = selector.partition(".")
    return (not name or name == tag) and (not cls or cls in classes)


class _Reader(HTMLParser):
    def __init__(self, profile: Profile) -> None:
        super().__init__(convert_charrefs=True)
        self.profile = profile
        self.found = False
        self.blocks: list[str] = []
        self._text: list[str] = []
        self._prefix = ""  # of the block being read: "## ", "- " or ""
        self._quote = 0  # blockquote depth
        # An open container or skipped element: its tag, and how many of that tag are open
        # inside it, so the matching end tag can be found in tag soup.
        self._inside: tuple[str, int] | None = None
        self._skipping: tuple[str, int] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            if tag in {"br", "hr"} and self._reading():
                self.flush()
            return
        values = dict(attrs)
        element_id = values.get("id")
        classes = set((values.get("class") or "").split())
        if self._inside is None:
            if element_id == self.profile.container:
                self.found = True
                self._inside = (tag, 1)
            return
        self._inside = _deeper(self._inside, tag)
        if self._skipping is not None:
            self._skipping = _deeper(self._skipping, tag)
            return
        if tag in ALWAYS_SKIPPED or any(
            _matches(s, tag, classes, element_id) for s in self.profile.skip
        ):
            self._skipping = (tag, 1)
            return
        if tag in BLOCKS:
            self.flush()
            if tag == "blockquote":
                self._quote += 1
            elif tag[0] == "h" and tag[1:].isdigit():
                self._prefix = "#" * int(tag[1:]) + " "
            elif tag == "li":
                self._prefix = "- "
        elif tag in CELLS and self._text:
            self._text.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if self._inside is None:
            return
        if self._skipping is not None:
            self._skipping = _shallower(self._skipping, tag)
        elif tag in BLOCKS:
            self.flush()
            if tag == "blockquote" and self._quote:
                self._quote -= 1
        self._inside = _shallower(self._inside, tag)
        if self._inside is None:
            self._skipping = None  # tag soup: the container closed inside a skipped element

    def handle_data(self, data: str) -> None:
        if self._reading():
            self._text.append(data)

    def flush(self) -> None:
        text = " ".join("".join(self._text).split())
        if text:
            self.blocks.append("> " * self._quote + self._prefix + text)
        self._text = []
        self._prefix = ""

    def _reading(self) -> bool:
        return self._inside is not None and self._skipping is None


def _deeper(open_element: tuple[str, int], tag: str) -> tuple[str, int]:
    name, depth = open_element
    return (name, depth + 1) if tag == name else open_element


def _shallower(open_element: tuple[str, int], tag: str) -> tuple[str, int] | None:
    name, depth = open_element
    if tag != name:
        return open_element
    return (name, depth - 1) if depth > 1 else None
