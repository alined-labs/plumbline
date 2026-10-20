"""A review sheet for a golden file: each item beside the pinned text of every article it cites,
so the reviewer reads the claim and the statute together instead of looking each article up.

    uv run python -m plumbline.corpus.review data/golden/drafts/golden_v0.jsonl
    uv run python -m plumbline.corpus.review FILE --item es-0008 --item fl-0001 --chars 0
    uv run python -m plumbline.corpus.review FILE --prefix du- --category lease_check
    uv run python -m plumbline.corpus.review FILE --list

The sheet is Markdown on stdout. It quotes statute text, including Dubai's and Colombia's,
whose licences do not allow redistribution: it is for the reviewer's own reading, so do not
commit it. A Spanish article is shown as it stood on the item's `signed_on` or `as_of` date,
or on the edition's own date when the item has none.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from plumbline.corpus.leases import ExpectedFindings, load_expected
from plumbline.corpus.manifest import MANIFEST, Manifest, Source, load_manifest
from plumbline.corpus.refs import article_exists, article_text, paragraph_text
from plumbline.settings import ROOT
from rag_eval.schema import ArticleRef, Category, GoldenItem, load_golden


def render_item(
    item: GoldenItem,
    manifest: Manifest,
    expected: ExpectedFindings | None,
    root: Path = ROOT,
    chars: int = 600,
) -> str:
    sources = {(source.law, source.edition): source for source in manifest.sources}
    day = item.signed_on or item.as_of
    lines = [f"## {item.id} · {item.category.value} · {item.difficulty.value}", ""]
    lines.append(f"**Question.** {item.question}")
    if item.signed_on is not None:
        lines.append(
            f"\n**Signed on** {item.signed_on.isoformat()}: the law in force that day governs."
        )
    elif item.as_of is not None:
        lines.append(f"\n**As of** {item.as_of.isoformat()}: the answer must hold on that date.")
    if item.lease_id is not None:
        lines.append(f"\n**Lease.** `data/leases/{item.lease_id}.md`")
    if item.expected_abstain:
        lines.append("\n**Expected:** abstain (out of scope).")
    if item.reference_answer:
        lines.append(f"\n**Reference answer.** {item.reference_answer}")
    lines.append(f"\n**Source ({item.source_type.value}).** {item.source_note or ''}")
    for ref in item.gold_refs:
        source = sources.get((ref.law, ref.edition))
        paragraph = f", paragraph {ref.paragraph}" if ref.paragraph else ""
        lines.append(f"\n### {ref.key} (edition {ref.edition}){paragraph}")
        if source is None:
            lines.append("\n*Not in the manifest.*")
            continue
        lines.append(f"\n{source.url} · sha256 `{source.sha256[:12]}`")
        lines.append("\n" + _quote(source, ref, day, root, chars))
    if expected is not None and item.lease_id is not None:
        lines += _findings(item, expected)
    return "\n".join(lines) + "\n"


def _quote(source: Source, ref: ArticleRef, day: date | None, root: Path, chars: int) -> str:
    """The cited paragraph(s), when the reference names them and they can be found, then the
    article from its start (cut at `chars`, or whole when `chars` is 0)."""
    exists = article_exists(source, ref.article, root)
    if exists is None:
        return "*The source file is not on this machine: run `make fetch`.*"
    text = article_text(source, ref.article, day, root) if exists else None
    if text is None:
        return f"*Article {ref.article} is not in {source.id}.*"
    parts = []
    if ref.paragraph:
        cited = paragraph_text(text, ref.paragraph)
        if cited is None:
            parts.append(
                f"*Cited paragraph {ref.paragraph} could not be located; read the article.*"
            )
        else:
            parts.append(f"**Cited paragraph {ref.paragraph}**\n\n" + _blockquote(cited))
    shown = text if not chars or len(text) <= chars else text[:chars].rstrip() + " …"
    parts.append(
        "**The article" + (" begins" if shown != text else "") + "**\n\n" + _blockquote(shown)
    )
    return "\n\n".join(parts)


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def _findings(item: GoldenItem, expected: ExpectedFindings) -> list[str]:
    lease = next((lease for lease in expected.leases if lease.lease_id == item.lease_id), None)
    if lease is None:
        return []
    cited = {ref.key for ref in item.gold_refs}
    lines = [f"\n### The lease's planted findings for these articles ({lease.lease_id})"]
    lines += [
        f"\n- Clause {f.clause}: “{f.quote}” — {f.issue}"
        for f in lease.findings
        if f.violates.key in cited
    ]
    lines += [
        f"\n- Clause {w.clause} (lawful): “{w.quote}” — {w.why}"
        for w in lease.lawful
        if w.allowed_by.key in cited
    ]
    return lines


def select(
    items: Sequence[GoldenItem],
    ids: Sequence[str] = (),
    prefixes: Sequence[str] = (),
    categories: Sequence[str] = (),
) -> list[GoldenItem]:
    """The items to read: those named by id or by an id prefix (all of them when neither is
    given), narrowed to the categories asked for."""
    chosen = list(items)
    if ids or prefixes:
        chosen = [item for item in chosen if item.id in ids or item.id.startswith(tuple(prefixes))]
    if categories:
        chosen = [item for item in chosen if item.category.value in categories]
    return chosen


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.corpus.review",
        description="Print each golden item beside the pinned text of the articles it cites.",
    )
    parser.add_argument("file", type=Path, help="a golden JSONL file")
    parser.add_argument("--item", action="append", default=[], metavar="ID", help="only this item")
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        metavar="PREFIX",
        help="only items whose id starts with PREFIX, such as du- or xj-",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        choices=[category.value for category in Category],
        metavar="NAME",
        help="only items of this category",
    )
    parser.add_argument("--list", action="store_true", help="one line per item, not the sheet")
    parser.add_argument(
        "--chars", type=int, default=600, help="how much of each article to show; 0 for all"
    )
    args = parser.parse_args(argv)
    items = load_golden(args.file)
    unknown = sorted(set(args.item) - {item.id for item in items})
    if unknown:
        print(f"{args.file}: no item {', '.join(unknown)}", file=sys.stderr)
        return 1
    chosen = select(items, args.item, args.prefix, args.category)
    if not chosen:
        print(f"{args.file}: no item matches", file=sys.stderr)
        return 1
    if args.list:
        for item in chosen:
            print(
                f"{item.id}  {item.category.value:<18} {item.difficulty.value:<6} {item.question}"
            )
        return 0
    manifest = load_manifest(MANIFEST)
    expected_file = ROOT / "data" / "leases" / "expected_findings.json"
    expected = load_expected(expected_file) if expected_file.is_file() else None
    print(f"# Review sheet for {args.file.name}\n")
    for item in chosen:
        print(render_item(item, manifest, expected, ROOT, args.chars))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
