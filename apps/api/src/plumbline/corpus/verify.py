"""Write `verification` records into a golden file from a list, so nobody hand-edits its lines.

    uv run python -m plumbline.corpus.verify data/golden/drafts/golden_v1.jsonl RECORDS \\
        --checked-by "Lane B (Claude Opus), cross-checked by gemini-3.8-flash; ..."
    uv run python -m plumbline.corpus.verify FILE RECORDS --checked-on 2026-10-20 --dry-run

RECORDS is a JSONL file with one object per item to verify:

    {"id": "es-0002", "second_source": "Title, https://...", "quoted_text": "...", "notes": "..."}

`id` and `second_source` are required. `checked_by` and `checked_on` may be given per record;
otherwise the command's options apply (`--checked-on` defaults to today). `quoted_text` is the
statute text that supports the answer, in its original language. When it is given, it must be
found in one of the item's cited articles as that article stood on the item's `signed_on` or
`as_of` date (the edition's own date otherwise), after whitespace is squeezed and curly quotes are made plain; a quote that leaves
words out marks the gap with "…" or "[...]", and each piece must then be found in order. When it
is left out, it is taken from the pinned text: the cited paragraph of each gold reference, or the
whole article when the reference names no paragraph. An item with no gold reference (an
out-of-scope question) has nothing to quote from, so its record must carry its own `quoted_text`,
which is not checked.

An item that cites a fetch-only source (Dubai's portal forbids redistribution; Colombia's
compilation protects its notes) is still checked against that text, but its `quoted_text` is
stored as the export's withheld marker, so the repository never carries a copy;
`plumbline.corpus.validate` refuses anything else there.

Nothing is written unless every record is good: an unknown id, a record for an item that is
already verified (unless `--replace`), a quote not in the pinned text or a source that is not on
this machine (Dubai and Colombia are fetch-only: run `make fetch`) is reported, and the file is
left as it was. The file is rewritten in its canonical form, so only the verified lines change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from plumbline.corpus.export import WITHHELD
from plumbline.corpus.manifest import MANIFEST, Manifest, Source, load_manifest
from plumbline.corpus.refs import article_text, paragraph_text
from plumbline.settings import ROOT
from rag_eval.schema import ArticleRef, GoldenItem, Verification, dump_golden, load_golden

# A quote that leaves words out says so with an ellipsis; each piece is then found in turn.
GAP: Final = re.compile(r"\s*(?:…|\[\.\.\.\]|\[…\])\s*")

# Typographic quotes are read as plain ones: a checker types ' where the statute prints ’.
QUOTES: Final = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

Text = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class Record(BaseModel):
    """One line of RECORDS: what the checker read for one item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Text
    second_source: Text
    quoted_text: Text | None = None
    notes: Text | None = None
    checked_by: Text | None = None
    checked_on: date | None = None


class RecordError(ValueError):
    """A record that cannot be applied; the message says which and why."""


def load_records(path: Path) -> list[Record]:
    records: list[Record] = []
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(Record.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}:{number}: {exc}")
    if errors:
        raise RecordError("\n".join(errors))
    return records


def squeeze(text: str) -> str:
    """One space between words, in one Unicode form, with plain quotes, so line breaks, composed
    or decomposed accents and curly apostrophes do not decide whether a quote matches."""
    return " ".join(unicodedata.normalize("NFC", text).translate(QUOTES).split())


def quote_in(quote: str, text: str) -> bool:
    """Whether every piece of `quote` (split at its ellipses) is in `text`, in order, each as
    whole words: "30 días" must not be found inside "130 días"."""
    haystack, start = squeeze(text), 0
    for piece in (squeeze(part) for part in GAP.split(quote)):
        if not piece:
            continue
        found = _whole(piece, haystack, start)
        if found < 0:
            return False
        start = found + len(piece)
    return True


def _whole(piece: str, haystack: str, start: int) -> int:
    """Where `piece` first occurs in `haystack` from `start` with no letter or digit running
    on at either end, or -1. An end of the piece that is not a word character needs no edge.
    A number runs on through a separator between two digits, so "1.000" is not found inside
    "1.000.000", nor "artículo 9" inside "artículo 9.3"."""
    found = haystack.find(piece, start)
    while found >= 0:
        end = found + len(piece)
        if _edge(piece[0], haystack[found - 2 : found][::-1]) and _edge(
            piece[-1], haystack[end : end + 2]
        ):
            return found
        found = haystack.find(piece, found + 1)
    return -1


def _edge(inner: str, outside: str) -> bool:
    """Whether a match ends cleanly: `inner` is the piece's character at that end, `outside` the
    next one or two characters of the haystack beyond it, nearest first."""
    if not outside or not inner.isalnum():
        return True
    if outside[0].isalnum():
        return False
    # "9" then ".3": the separator joins two digits, so the number goes on.
    return not (inner.isdigit() and outside[0] in ".,/" and outside[1:2].isdigit())


def _source(item: GoldenItem, ref: ArticleRef, manifest: Manifest) -> Source:
    source = next(
        (s for s in manifest.sources if (s.law, s.edition) == (ref.law, ref.edition)), None
    )
    if source is None:
        raise RecordError(f"{item.id}: {ref.law} edition {ref.edition} is not in the manifest")
    return source


def _pinned(item: GoldenItem, ref: ArticleRef, manifest: Manifest, root: Path) -> str:
    """The cited article as it stood on the item's date, without the BOE's version header."""
    source = _source(item, ref, manifest)
    if not (root / source.path).is_file():
        raise RecordError(f"{item.id}: {source.id} is not on this machine; run `make fetch`")
    text = article_text(source, ref.article, item.signed_on or item.as_of, root)
    if text is None:
        raise RecordError(f"{item.id}: article {ref.article} is not in {source.id}")
    if text.startswith("[BOE-"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text


def quoted_text(item: GoldenItem, record: Record, manifest: Manifest, root: Path) -> str:
    """The record's quote, checked against the pinned text, or one taken from it; the withheld
    marker, once checked, for an item that cites a fetch-only source."""
    found = _quoted_text(item, record, manifest, root)
    if not all(_source(item, ref, manifest).committed for ref in item.gold_refs):
        return WITHHELD
    return found


def _quoted_text(item: GoldenItem, record: Record, manifest: Manifest, root: Path) -> str:
    if not item.gold_refs:
        if record.quoted_text is None:
            raise RecordError(f"{item.id}: cites no article, so the record must carry quoted_text")
        return record.quoted_text
    articles = [(ref, _pinned(item, ref, manifest, root)) for ref in item.gold_refs]
    if record.quoted_text is not None:
        if not any(quote_in(record.quoted_text, text) for _, text in articles):
            raise RecordError(
                f"{item.id}: quoted_text is not in the pinned text of "
                + ", ".join(ref.key for ref, _ in articles)
                + _dated(item)
            )
        return record.quoted_text
    parts = []
    for ref, text in articles:
        cited = paragraph_text(text, ref.paragraph) if ref.paragraph else text
        if cited is None:
            raise RecordError(
                f"{item.id}: paragraph {ref.paragraph} of {ref.key} cannot be located; "
                "give quoted_text in the record"
            )
        label = f"{ref.law} art. {ref.article}" + (f" {ref.paragraph}" if ref.paragraph else "")
        parts.append(f"[{label}] {cited}")
    return "\n\n".join(parts)


def _dated(item: GoldenItem) -> str:
    day = item.signed_on or item.as_of
    return f" as it stood on {day.isoformat()}" if day else ""


def apply_records(
    items: Sequence[GoldenItem],
    records: Sequence[Record],
    checked_by: str | None,
    checked_on: date,
    manifest: Manifest,
    root: Path = ROOT,
    replace: bool = False,
) -> list[GoldenItem]:
    """The items, in order, with a verification written for each record. Raises RecordError
    naming every record that cannot be applied, and then applies none."""
    by_id = {item.id: item for item in items}
    verified: dict[str, Verification] = {}
    errors: list[str] = []
    seen: set[str] = set()
    for record in records:
        try:
            if record.id in seen:
                raise RecordError(f"{record.id}: two records for the same item")
            seen.add(record.id)
            item = by_id.get(record.id)
            if item is None:
                raise RecordError(f"{record.id}: no such item in the file")
            if item.verification is not None and not replace:
                raise RecordError(f"{record.id}: already verified; pass --replace to rewrite it")
            checker = record.checked_by or checked_by
            if checker is None:
                raise RecordError(f"{record.id}: no checked_by in the record or the command")
            verified[record.id] = Verification(
                quoted_text=quoted_text(item, record, manifest, root),
                second_source=record.second_source,
                checked_on=record.checked_on or checked_on,
                checked_by=checker,
                notes=record.notes,
            )
        except RecordError as exc:
            errors.append(str(exc))
    if errors:
        raise RecordError("\n".join(errors))
    return [
        item.model_copy(update={"verification": verified[item.id]}) if item.id in verified else item
        for item in items
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.corpus.verify",
        description="Write verification records into a golden file from a JSONL list.",
    )
    parser.add_argument("file", type=Path, help="the golden JSONL file to update in place")
    parser.add_argument("records", type=Path, help="one JSON object per item to verify")
    parser.add_argument("--checked-by", help="who checked, for records that do not say")
    parser.add_argument(
        "--checked-on",
        type=date.fromisoformat,
        default=date.today(),
        help="the day the items were checked, for records that do not say (default: today)",
    )
    parser.add_argument("--replace", action="store_true", help="rewrite existing verifications")
    parser.add_argument("--dry-run", action="store_true", help="check the records, write nothing")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    try:
        items = load_golden(args.file)
        updated = apply_records(
            items,
            load_records(args.records),
            args.checked_by,
            args.checked_on,
            load_manifest(args.manifest),
            replace=args.replace,
        )
    except ValueError as exc:  # RecordError, GoldenFileError, a bad date
        print(exc, file=sys.stderr)
        return 1
    count = sum(1 for old, new in zip(items, updated, strict=True) if old is not new)
    if not args.dry_run:
        dump_golden(updated, args.file)
    action = "would verify" if args.dry_run else "verified"
    print(f"{action} {count} of {len(items)} items in {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
