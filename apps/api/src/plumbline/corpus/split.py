"""A seeded, stratified split of a golden file into dev and test (Gate 2).

    uv run python -m plumbline.corpus.split data/golden/drafts/golden_v1.jsonl
    uv run python -m plumbline.corpus.split FILE OUTPUT [--test 60] [--seed TEXT] [--drop ID ...]

The split is applied when the human freezes a version, not while the file is a draft: the freeze
branch runs this on the verified draft and commits OUTPUT as `data/golden/golden_v<N>.jsonl`.
Once frozen, the `split` field is part of the file and never changes. Without OUTPUT the command
only prints how the items would fall.

Items dropped at the freeze (`--drop`) are left out after the split, not before: every item is
assigned as if none were dropped, so an item that was dev in the draft is dev in the frozen file.
Other lanes build on the dev items before the freeze (the judge's labels, for one), and a split
recomputed without the dropped items could move some of those into test. The price is that the
frozen file keeps the strata only as closely as the drops allow.

A third of the items go to test (60 of 180). They are spread so that each category keeps its
share of test; inside a category each place (one jurisdiction, several, or none) keeps its share,
and inside a place each language. At every level the test places are shared out in proportion to
the number of items below, by largest remainder, and a group's leftover place goes to whichever
groups have the largest fractions. Which items of the smallest group are taken is decided by a
hash of the seed and the item's id, not by a random generator, so the split is the same on every
machine and Python version, and does not depend on the order of the lines or on any field of an
item except its id, category, jurisdictions and language.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from rag_eval.schema import GoldenFileError, GoldenItem, Split, dump_golden, load_golden

SEED: Final = "plumbline-golden-split-v1"

Key = Callable[[GoldenItem], str]


def category_of(item: GoldenItem) -> str:
    return item.category.value


def place_of(item: GoldenItem) -> str:
    """The one jurisdiction an item is about, "several" for a comparison, "none" for an item that
    names no jurisdiction (an out-of-scope question)."""
    places = sorted({jurisdiction.value for jurisdiction in item.jurisdictions})
    if not places:
        return "none"
    return places[0] if len(places) == 1 else "several"


def language_of(item: GoldenItem) -> str:
    return item.source_language.value


# From the widest group to the narrowest: the order the test places are shared out in.
LEVELS: Final[tuple[tuple[str, Key], ...]] = (
    ("category", category_of),
    ("place", place_of),
    ("language", language_of),
)


def assign_splits(
    items: Sequence[GoldenItem], test_size: int, seed: str = SEED
) -> list[GoldenItem]:
    """The same items, in the same order, each with `split` set to dev or test. `test_size`
    items go to test. Items that already have a split are refused: a frozen set is not re-cut."""
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("item ids are not unique")
    assigned = sorted(item.id for item in items if item.split is not Split.UNASSIGNED)
    if assigned:
        raise ValueError(f"already split: {', '.join(assigned[:5])}")
    if not 0 <= test_size <= len(items):
        raise ValueError(f"cannot put {test_size} of {len(items)} items in test")
    chosen: set[str] = set()
    _choose(list(items), test_size, seed, "", [key for _, key in LEVELS], chosen)
    return [
        item.model_copy(update={"split": Split.TEST if item.id in chosen else Split.DEV})
        for item in items
    ]


def _choose(
    group: list[GoldenItem], count: int, seed: str, path: str, keys: list[Key], chosen: set[str]
) -> None:
    """Put `count` of the items in `group` in test, spread over the groups the next key makes."""
    if count == 0:
        return
    if not keys:
        by_rank = sorted(group, key=lambda item: _rank(seed, item.id))
        chosen.update(item.id for item in by_rank[:count])
        return
    buckets: dict[str, list[GoldenItem]] = {}
    for item in group:
        buckets.setdefault(keys[0](item), []).append(item)
    shares = _shares({name: len(members) for name, members in buckets.items()}, count, seed, path)
    for name, share in shares.items():
        _choose(buckets[name], share, seed, f"{path}/{name}", keys[1:], chosen)


def _shares(sizes: dict[str, int], count: int, seed: str, path: str) -> dict[str, int]:
    """`count` places shared out over groups of the given sizes, in proportion to them. Each
    group gets the whole number of its share; the places left over go one each to the groups
    with the largest fractions, ties broken by the hash. Integer arithmetic throughout, so a
    fraction is never a rounding accident."""
    total = sum(sizes.values())
    shares: dict[str, int] = {}
    fractions: dict[str, int] = {}
    for name, size in sizes.items():
        shares[name], fractions[name] = divmod(size * count, total)
    left_over = count - sum(shares.values())
    # Every group that gets a place here has a fraction above zero, so it is never over-filled.
    by_claim = sorted(sizes, key=lambda name: (-fractions[name], _rank(seed, f"{path}/{name}")))
    for name in by_claim[:left_over]:
        shares[name] += 1
    return shares


def _rank(seed: str, name: str) -> str:
    return hashlib.sha256(f"{seed}/{name}".encode()).hexdigest()


def drop_after_split(items: Sequence[GoldenItem], dropped: Sequence[str]) -> list[GoldenItem]:
    """The split items without the dropped ones. An id that is not in the file is refused, so
    a mistyped id cannot leave an item in that was meant to go."""
    unknown = sorted(set(dropped) - {item.id for item in items})
    if unknown:
        raise ValueError(f"cannot drop items that are not in the file: {', '.join(unknown)}")
    return [item for item in items if item.id not in set(dropped)]


def report(items: Sequence[GoldenItem]) -> str:
    """Markdown tables of how many items of each category, place and language are in dev and test."""
    lines = []
    for title, key in LEVELS:
        counts = Counter((key(item), item.split) for item in items)
        lines += [f"| {title} | dev | test | all |", "| --- | ---: | ---: | ---: |"]
        for name in sorted({name for name, _ in counts}):
            dev, test = counts[(name, Split.DEV)], counts[(name, Split.TEST)]
            total = dev + test + counts[(name, Split.UNASSIGNED)]
            lines.append(f"| {name} | {dev} | {test} | {total} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.corpus.split",
        description="Split a golden file into dev and test, stratified and seeded.",
    )
    parser.add_argument("file", type=Path, help="a golden JSONL file with no split assigned")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="where to write the items with their split; without it, only the report is printed",
    )
    parser.add_argument("--test", type=int, help="items for test (default: a third of the file)")
    parser.add_argument("--seed", default=SEED, help=f"the seed text (default: {SEED})")
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="ID",
        help="leave this item out after splitting (repeatable); the others keep their side",
    )
    args = parser.parse_args(argv)
    try:
        items = load_golden(args.file)
        test_size = args.test if args.test is not None else round(len(items) / 3)
        split = drop_after_split(assign_splits(items, test_size, args.seed), args.drop)
    except (GoldenFileError, ValueError) as exc:
        print(f"{args.file}: {exc}", file=sys.stderr)
        return 1
    print(report(split))
    if args.output is not None:
        dump_golden(split, args.output)
        print(f"wrote {len(split)} items to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
