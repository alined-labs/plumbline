"""Fetch the corpus sources, hash them and pin them in the manifest.

Every source is declared once, in SOURCES. The script downloads the publisher's page and,
when the page wraps the statute in parts that change between downloads (the day's date, a
form token), keeps only the statute's own markup, cut byte for byte. It hashes what it
keeps, and the manifest row pins that hash, so any later download can be checked against
it.

    uv run python -m plumbline.corpus.fetch                 # make fetch
    uv run python -m plumbline.corpus.fetch --check         # verify only; writes nothing
    uv run python -m plumbline.corpus.fetch --repin ID ...  # take a reviewed change upstream

The default run fills in what is missing. A declared source with no manifest row is
downloaded, written and pinned. A pinned source whose file is absent (a fetch-only source
on a fresh clone) is downloaded and kept only if it matches its pin. A file already on
disk is checked against its pin and never downloaded again. --check downloads every
source again and compares it with its pin, which tells whether each URL still serves the
pinned text. --repin downloads the named sources again and rewrites their files and rows.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import httpx

from plumbline.core.types import Jurisdiction, Language
from plumbline.corpus.manifest import (
    MANIFEST,
    Format,
    Manifest,
    Source,
    load_manifest,
    save_manifest,
)
from plumbline.settings import ROOT

USER_AGENT: Final = "plumbline-corpus-fetch (+https://github.com/alined-labs/plumbline)"
TIMEOUT: Final = httpx.Timeout(60.0, connect=15.0)


class FetchError(Exception):
    """A source that could not be downloaded, or cut as declared."""


@dataclass(frozen=True)
class Declared:
    """A source as declared here; its manifest row adds the hash and the retrieval date."""

    id: str
    law: str
    title: str
    jurisdiction: Jurisdiction
    language: Language
    url: str
    edition: str
    format: Format
    license_basis: str
    committed: bool
    consolidated_on: date | None = None
    notes: str | None = None
    # Markers that each begin one element of the page to keep: its start tag, plus enough
    # of what follows to be unique. Each element is cut through its matching end tag, byte
    # for byte, and the elements are written one per line. Empty: keep the whole page.
    keep: tuple[bytes, ...] = ()
    accept: str | None = None  # the Accept header, for an API that needs one

    @property
    def path(self) -> str:
        folder = "raw" if self.committed else "fetched"
        return f"data/corpus/{folder}/{self.id}.{self.format}"

    def row(self, sha256: str, retrieved_on: date) -> Source:
        declared = {
            name: getattr(self, name) for name in Source.model_fields if hasattr(self, name)
        }
        return Source.model_validate({**declared, "sha256": sha256, "retrieved_on": retrieved_on})


def florida_section(number: str) -> bytes:
    """Where section `number` begins in the Florida Legislature's statute markup (a section
    whose number carries a footnote mark, such as 83.5615, begins differently)."""
    return f'<div class="Section"><span class="SectionNumber">{number}&#x2003;'.encode()


FLORIDA_PART_II: Final = (
    b'<div class="Part"><div class="PartTitle"><div class="PartNumber">PART II</div>'
)
FLORIDA_BASIS: Final = "Public domain (government edicts doctrine)"
BOE_BASIS: Final = (
    "BOE reuse conditions: source and update date cited; consolidated text, informational only"
)
BOE_RECORD: Final = (
    "The BOE's consolidated-legislation open-data record: metadata (with the update date), "
    "analysis, and the text, every block with all its versions and their dates. A "
    "consolidated text is informational; only the BOE's official editions are authentic."
)


def boe_record(identifier: str) -> str:
    return f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{identifier}"


SOURCES: Final[tuple[Declared, ...]] = (
    Declared(
        id="fl-stat-83-2026",
        law="fl-stat-83",
        title="Florida Statutes 2026, chapter 83 (Landlord and Tenant), part II: Residential Tenancies",
        jurisdiction=Jurisdiction.FLORIDA,
        language=Language.EN,
        url="https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0000-0099/0083/0083.html&StatuteYear=2026",
        edition="2026",
        format="html",
        license_basis=FLORIDA_BASIS,
        committed=True,
        notes=(
            "Part II (ss. 83.40-83.684), cut from the statute markup of the chapter page "
            "(flsenate.gov serves the same bytes); parts I and III are not in the corpus. "
            "Florida Statutes 2026 is the official statute law (s. 11.2421). "
            "s. 83.5615 takes effect only upon the repeal of the federal Protecting Tenants at "
            "Foreclosure Act (its Note)."
        ),
        keep=(FLORIDA_PART_II,),
    ),
    Declared(
        id="fl-stat-718-2026",
        law="fl-stat-718",
        title="Florida Statutes 2026, chapter 718 (Condominiums): ss. 718.110, 718.112 and 718.116",
        jurisdiction=Jurisdiction.FLORIDA,
        language=Language.EN,
        url="https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0700-0799/0718/0718.html&StatuteYear=2026",
        edition="2026",
        format="html",
        license_basis=FLORIDA_BASIS,
        committed=True,
        notes=(
            "Sections 718.110, 718.112 and 718.116, cut in that order from the statute markup "
            "of the chapter page (flsenate.gov serves the same bytes); the rest of chapter 718 "
            "is not in the corpus. The provisions on tenancies: 718.110(13) (amendments "
            "restricting rentals), 718.112(2)(k) (lease approval fees and the association's "
            "security deposit) and 718.116(11) (rent demanded from the tenant of a delinquent "
            "owner)."
        ),
        keep=tuple(florida_section(n) for n in ("718.110", "718.112", "718.116")),
    ),
    Declared(
        id="es-lau-boe-2026-10-13",
        law="es-lau",
        title="Ley 29/1994, de 24 de noviembre, de Arrendamientos Urbanos (consolidated text)",
        jurisdiction=Jurisdiction.SPAIN,
        language=Language.ES,
        url=boe_record("BOE-A-1994-26003"),
        edition="boe-2026-10-13",
        consolidated_on=date(2026, 10, 13),
        format="xml",
        license_basis=BOE_BASIS,
        committed=True,
        accept="application/xml",
        notes=(
            f"{BOE_RECORD} Reading copy: https://www.boe.es/buscar/act.php?id=BOE-A-1994-26003. "
            "Holds the amendments of Real Decreto-ley 29/2026, in force from 2026-10-08 with no "
            "validation by Congress recorded when retrieved (it re-enacts RDL 26/2026, repealed "
            "on 2026-10-02), and announces art. 10 as reworded by RDL 28/2026 from 2026-11-15."
        ),
    ),
    Declared(
        id="es-lph-boe-2026-10-05",
        law="es-lph",
        title="Ley 49/1960, de 21 de julio, sobre propiedad horizontal (consolidated text)",
        jurisdiction=Jurisdiction.SPAIN,
        language=Language.ES,
        url=boe_record("BOE-A-1960-10906"),
        edition="boe-2026-10-05",
        consolidated_on=date(2026, 10, 5),
        format="xml",
        license_basis=BOE_BASIS,
        committed=True,
        accept="application/xml",
        notes=(
            f"{BOE_RECORD} Reading copy: https://www.boe.es/buscar/act.php?id=BOE-A-1960-10906. "
            "Holds art. 10 and the third additional provision as reworded by Ley 4/2026, in "
            "force from 2026-10-23."
        ),
    ),
)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def element(page: bytes, marker: bytes) -> bytes:
    """The element that `marker` begins, through its matching end tag, cut byte for byte.

    The marker must occur exactly once, so a page that changes shape fails loudly instead
    of yielding the wrong text. Nesting is counted on the marker's own tag name only,
    which is enough for the generated statute markup this cuts.
    """
    count = page.count(marker)
    if count != 1:
        raise FetchError(f"the marker {marker[:60]!r} occurs {count} times in the page")
    start_tag = re.match(rb"<([A-Za-z][A-Za-z0-9]*)", marker)
    if start_tag is None:
        raise FetchError(f"the marker {marker[:60]!r} does not begin with a start tag")
    tags = re.compile(rb"<(/?)" + start_tag.group(1) + rb"(?=[\s/>])")
    begin = page.index(marker)
    depth = 0
    for tag in tags.finditer(page, begin):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return page[begin : page.index(b">", tag.end()) + 1]
    raise FetchError(f"the element {marker[:60]!r} never closes")


def download(client: httpx.Client, source: Declared) -> bytes:
    """What the manifest pins for `source`: the whole page, or the elements it keeps."""
    try:
        headers = {"Accept": source.accept} if source.accept else None
        response = client.get(source.url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"{source.url}: {exc}") from exc
    if response.url.host != httpx.URL(source.url).host:
        raise FetchError(f"{source.url} redirected to another host: {response.url}")
    if not source.keep:
        return response.content
    return b"".join(element(response.content, marker) + b"\n" for marker in source.keep)


def write(path: Path, content: bytes) -> None:
    """Write through a temporary file, so an interrupted run never leaves half a source."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    partial.write_bytes(content)
    partial.replace(path)


def undeclared(sources: Sequence[Declared], manifest: Manifest) -> list[str]:
    declared = {source.id for source in sources}
    return [
        f"{row.id}: in the manifest but not declared in plumbline.corpus.fetch"
        for row in manifest.sources
        if row.id not in declared
    ]


def verify(source: Declared, row: Source, client: httpx.Client, root: Path) -> list[str]:
    """Check a pinned source: its declaration, then its file, downloading the file only
    when it is absent and keeping the download only if it matches the pin."""
    if source.row(row.sha256, row.retrieved_on) != row:
        return [
            f"{source.id}: the declaration differs from its manifest row; "
            f"review it, then --repin {source.id}"
        ]
    file = root / row.path
    if file.is_file():
        digest = sha256(file.read_bytes())
        if digest != row.sha256:
            return [f"{source.id}: {row.path} has sha256 {digest}, the manifest pins {row.sha256}"]
        print(f"{source.id}: ok")
        return []
    content = download(client, source)
    digest = sha256(content)
    if digest != row.sha256:
        return [
            f"{source.id}: the download has sha256 {digest}, the manifest pins {row.sha256}; "
            "the publisher changed it (see --check)"
        ]
    write(file, content)
    print(f"{source.id}: fetched {row.path}, sha256 matches")
    return []


def fetch(
    sources: Sequence[Declared],
    manifest: Manifest,
    client: httpx.Client,
    *,
    root: Path = ROOT,
    repin: frozenset[str] = frozenset(),
    today: date | None = None,
) -> tuple[Manifest, list[str]]:
    """The default run, and --repin: the manifest to save and the problems found. A pinned
    row changes only when its id is in `repin`."""
    retrieved_on = today or datetime.now(UTC).date()
    pinned = manifest.by_id()
    problems = undeclared(sources, manifest)
    unknown = repin - {source.id for source in sources}
    problems += [f"{id_}: --repin names a source that is not declared" for id_ in sorted(unknown)]
    rows: list[Source] = []
    for source in sources:
        row = pinned.get(source.id)
        try:
            if row is None or source.id in repin:
                content = download(client, source)
                row = source.row(sha256(content), retrieved_on)
                write(root / row.path, content)
                print(f"{source.id}: pinned {row.path} ({len(content):,} bytes, {row.sha256[:12]})")
            else:
                problems += verify(source, row, client, root)
        except FetchError as exc:
            problems.append(f"{source.id}: {exc}")
        if row is not None:
            rows.append(row)
    declared = {source.id for source in sources}
    rows += [row for row in manifest.sources if row.id not in declared]
    return Manifest(sources=rows), problems


def check(sources: Sequence[Declared], manifest: Manifest, client: httpx.Client) -> list[str]:
    """--check: download every declared source again and compare it with its pin."""
    pinned = manifest.by_id()
    problems = undeclared(sources, manifest)
    for source in sources:
        row = pinned.get(source.id)
        if row is None:
            problems.append(f"{source.id}: declared but not pinned; run without --check")
            continue
        try:
            digest = sha256(download(client, source))
        except FetchError as exc:
            problems.append(f"{source.id}: {exc}")
            continue
        if digest == row.sha256:
            print(f"{source.id}: the URL still serves the pinned text")
        else:
            problems.append(
                f"{source.id}: the URL now serves a different text (sha256 {digest}); "
                "declare the new edition, or review the change and --repin"
            )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.corpus.fetch",
        description="Download the corpus sources, check them against the manifest, pin new ones.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="download every source again and compare it with its pin; write nothing",
    )
    mode.add_argument(
        "--repin",
        nargs="+",
        default=[],
        metavar="ID",
        help="download these sources again and rewrite their files and manifest rows",
    )
    args = parser.parse_args(argv)
    manifest = load_manifest(MANIFEST)
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
        transport=httpx.HTTPTransport(retries=2),
    ) as client:
        if args.check:
            problems = check(SOURCES, manifest, client)
        else:
            updated, problems = fetch(SOURCES, manifest, client, repin=frozenset(args.repin))
            if updated != manifest:
                save_manifest(updated, MANIFEST)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
