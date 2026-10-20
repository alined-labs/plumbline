"""Reading the HTML statute sources without a parser model (ParseMethod.HTML): Florida's
Online Sunshine statutes and the Colombian Senate's laws, each turned into Markdown with
one block per paragraph.

Each site has a profile: the element that holds the law, or none when the committed file
is the law alone (Lane B cuts Florida's statute markup out of its page), and the elements
inside it that are navigation, forms, a table of contents or empty boxes. A host without a
profile is an error, because reading a whole page would mix menus into the law. The pages
are old and not always well formed (Colombia's opens one container inside another and
never closes it), so an element ends at its matching end tag or, failing that, at the end
of the page.

Struck-through text is kept as ~~text~~: the Colombian Senate strikes out the words the
Constitutional Court declared unconstitutional (INEXEQUIBLE), and the chunker must be able
to tell them from the law in force. Underlined words (conditionally upheld) are still law
and stay plain text.

The Senate's validity notes ("Notas de vigencia", the Court's rulings, the original
wording) are not in its pages: each page's script fills its note boxes. Lane B commits a
law as its pages, each followed by its script, every part after a line
"<!-- plumbline part: <url> -->". The reader puts each script's notes into the boxes of
the page before it, as quotes, so the chunker reads them as notes, never as law in force,
and leaves the scripts themselves out.
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

READER = "plumbline html 3"  # ParsedDocument.parser; bump it when the output changes


class HtmlError(ValueError):
    """The page cannot be read: unknown site, undecodable bytes or no law container."""


@dataclass(frozen=True)
class Profile:
    container: str | None  # the id of the element that holds the law; None: the whole file
    skip: frozenset[str] = frozenset()  # "tag", "tag.class", ".class" or "#id"
    prepare: Callable[[str], str] | None = None  # rewrites the file before it is read


PART = re.compile(r"<!-- plumbline part: (\S+) -->")
NOTE = re.compile(
    r"function insRow(\d+)\(\)\s*\{\s*var description = new Array\(\);\s*"
    r'description\[0\] = "((?:[^"\\]|\\.)*)";'
)
NOTE_BOX = re.compile(r'<table id="Table(\d+)"[^>]*>\s*</table>', re.IGNORECASE)


def senate_notes(html: str) -> str:
    """The Senate's pages with each page's notes in its boxes, as quotes, and without the
    scripts that held them. A file without part lines is returned as it is."""
    pieces = PART.split(html)  # text before the first part, then url, body, url, body...
    if len(pieces) == 1:
        return html
    pages: list[str] = [pieces[0]]
    for url, body in zip(pieces[1::2], pieces[2::2], strict=True):
        if not url.endswith(".js"):
            pages.append(body)
            continue
        notes = {int(n): _unescape(text) for n, text in NOTE.findall(body)}
        pages[-1] = _fill_boxes(pages[-1], notes, url)  # this script fills the page before it
    return "".join(pages)


def _fill_boxes(page: str, notes: dict[int, str], script: str) -> str:
    """The page with each box replaced by its note. A box its script has no note for is an
    error: silently empty, it would hide that a provision was struck down or amended."""

    def note(box: re.Match[str]) -> str:
        number = int(box[1])
        if number not in notes:
            raise HtmlError(f"{script} has no note for box {number}: has the script changed?")
        return f"<blockquote>{notes[number]}</blockquote>"

    return NOTE_BOX.sub(note, page)


def _unescape(js: str) -> str:
    """A JavaScript string literal's text: \\" is ", \\' is ' and so on."""
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), js)


PROFILES: dict[str, Profile] = {
    # The committed files are cuts of the statute markup alone. div.CatchlineIndex is each
    # part's table of contents: it repeats every section title. A <sup> is a footnote mark,
    # and one before a section number would glue onto it ("1" + "83.5615"); the footnote
    # itself is the section's own Note, which is kept.
    "www.leg.state.fl.us": Profile(None, frozenset({"div.CatchlineIndex", "sup"})),
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
        senate_notes,
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
STRUCK = frozenset({"s", "strike", "del"})
# Stand-ins for the ~~ around struck text until whitespace is normalized, so that
# "<s> words </s>" becomes "~~words~~", which Markdown reads as strikethrough.
OPEN, CLOSE = "\x00", "\x01"


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
    reader.feed(profile.prepare(html) if profile.prepare else html)
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
        self.found = profile.container is None
        self.blocks: list[str] = []
        self._text: list[str] = []
        self._prefix = ""  # of the block being read: "## ", "- " or ""
        self._quote = 0  # blockquote depth
        self._struck = 0  # strikethrough depth
        # An open container or skipped element: its tag, and how many of that tag are open
        # inside it, so the matching end tag can be found in tag soup. Without a container,
        # the whole file sits in a root whose end tag never comes.
        self._inside: tuple[str, int] | None = None if profile.container else ("", 1)
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
        elif tag in STRUCK:
            self._struck += 1
            if self._struck == 1:
                self._text.append(OPEN)

    def handle_endtag(self, tag: str) -> None:
        if self._inside is None:
            return
        if self._skipping is not None:
            self._skipping = _shallower(self._skipping, tag)
        elif tag in BLOCKS:
            self.flush()
            if tag == "blockquote" and self._quote:
                self._quote -= 1
        elif tag in STRUCK and self._struck:
            self._struck -= 1
            if not self._struck:
                self._text.append(CLOSE)
        self._inside = _shallower(self._inside, tag)
        if self._inside is None:
            self._skipping = None  # tag soup: the container closed inside a skipped element

    def handle_data(self, data: str) -> None:
        if self._reading():
            self._text.append(data)

    def flush(self) -> None:
        if self._struck:  # a struck run that crosses a block ends here and goes on in the next
            self._text.append(CLOSE)
        text = " ".join("".join(self._text).split())
        text = re.sub(f"{OPEN}\\s*", "~~", re.sub(f"\\s*{CLOSE}", "~~", text))
        text = text.replace("~~~~", "")  # nothing struck, or two struck runs that touch
        if text:
            self.blocks.append("> " * self._quote + self._prefix + text)
        self._text = [OPEN] if self._struck else []
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
