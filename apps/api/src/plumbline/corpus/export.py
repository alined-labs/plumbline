"""Build the folder the maintainer publishes as the golden set's dataset.

    uv run python -m plumbline.corpus.export data/golden/golden_v1.jsonl dist/golden-v1

The folder holds the dataset card with its statistics (README.md), the golden file and its dev and
test halves, the synthetic leases with their expected findings, the corpus manifest, the data
licences, the changelog and a SHA256SUMS list. Running this publishes nothing: the maintainer
uploads the folder.

A file that is still a draft is refused, because a published item has been verified and has its
split; `--draft` builds the folder anyway, for a dry run.

One rule comes from the licences. The passage a reviewer copied from the official text
(`verification.quoted_text`) is kept only for items whose gold references are all in sources the
repository itself redistributes (Florida, Spain). For an item that cites a fetch-only source
(Dubai's portal forbids redistribution; Colombia's compilation protects its notes) the passage is
replaced by a statement that it is withheld, so the dataset never carries a copy of that text.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.corpus.split import report
from plumbline.settings import ROOT
from rag_eval.schema import GoldenFileError, GoldenItem, Split, dump_golden, load_golden

CARD: Final = ROOT / "data" / "golden" / "DATASET_CARD.md"
CHANGELOG: Final = ROOT / "data" / "golden" / "CHANGELOG.md"
LEASES: Final = ROOT / "data" / "leases"
LICENCES: Final = ROOT / "DATA_LICENSES.md"
MARKER: Final = "<!-- statistics -->"
WITHHELD: Final = (
    "[Withheld: the source is not redistributed. Read the article in the edition the "
    "reference names; corpus_manifest.json says where it is published.]"
)
LICENCE_NOTICE: Final = """# Licence

The questions, reference answers, verification records, synthetic leases and expected findings in
this folder are licensed under the Creative Commons Attribution 4.0 International licence
(CC BY 4.0): https://creativecommons.org/licenses/by/4.0/

The statutes the items refer to are not in this folder and keep their publishers' terms, which
DATA_LICENSES.md records.
"""


class ExportError(ValueError):
    """The golden file cannot be published as it is."""


def withhold_quotes(item: GoldenItem, manifest: Manifest) -> GoldenItem:
    """The item, with the reviewer's quoted passage replaced if any gold reference is in a source
    the repository does not redistribute (or in none the manifest knows)."""
    if item.verification is None:
        return item
    committed = {(s.law, s.edition): s.committed for s in manifest.sources}
    if all(committed.get((ref.law, ref.edition), False) for ref in item.gold_refs):
        return item
    verification = item.verification.model_copy(update={"quoted_text": WITHHELD})
    return item.model_copy(update={"verification": verification})


def unpublishable(items: Sequence[GoldenItem]) -> list[str]:
    """Why a file is not ready to publish: items nobody verified and items with no split."""
    problems = [f"{item.id}: not verified" for item in items if item.verification is None]
    problems += [f"{item.id}: no split" for item in items if item.split is Split.UNASSIGNED]
    return problems


def statistics(items: Sequence[GoldenItem]) -> str:
    """Markdown tables of the file's makeup, for the card."""
    tables = [report(items)]
    for title, key in (
        ("source type", lambda item: item.source_type.value),
        ("difficulty", lambda item: item.difficulty.value),
        ("added in", lambda item: item.added_in),
    ):
        tables.append(_counts(title, items, key))
    dated = sum(1 for item in items if item.as_of or item.signed_on)
    return "\n".join(tables) + f"\n{len(items)} items, {dated} of them dated.\n"


def _counts(title: str, items: Sequence[GoldenItem], key: Callable[[GoldenItem], str]) -> str:
    counts = Counter(key(item) for item in items)
    lines = [f"| {title} | items |", "| --- | ---: |"]
    lines += [f"| {name} | {counts[name]} |" for name in sorted(counts)]
    return "\n".join(lines) + "\n"


def build(
    golden: Path,
    out: Path,
    manifest: Manifest | None = None,
    *,
    draft: bool = False,
) -> list[Path]:
    """Write the folder `out` (which must not exist yet) and return the files in it."""
    manifest = manifest or load_manifest(MANIFEST)
    try:
        items = load_golden(golden)
    except GoldenFileError as exc:
        raise ExportError(str(exc)) from exc
    problems = unpublishable(items)
    if problems and not draft:
        shown = "; ".join(problems[:5])
        raise ExportError(f"{golden.name} is a draft ({len(problems)} problems: {shown})")
    if out.exists():
        raise ExportError(f"{out} exists already")
    items = [withhold_quotes(item, manifest) for item in items]

    out.mkdir(parents=True)
    dump_golden(items, out / golden.name)
    dump_golden([item for item in items if item.split is Split.DEV], out / "dev.jsonl")
    dump_golden([item for item in items if item.split is Split.TEST], out / "test.jsonl")
    leases = out / "leases"
    leases.mkdir()
    for lease in sorted(LEASES.glob("*.md")):
        if lease.name != "README.md":
            shutil.copyfile(lease, leases / lease.name)
    shutil.copyfile(LEASES / "expected_findings.json", leases / "expected_findings.json")
    shutil.copyfile(MANIFEST, out / "corpus_manifest.json")
    shutil.copyfile(LICENCES, out / "DATA_LICENSES.md")
    shutil.copyfile(CHANGELOG, out / "CHANGELOG.md")
    (out / "LICENSE.md").write_text(LICENCE_NOTICE, encoding="utf-8")
    card = CARD.read_text(encoding="utf-8")
    if MARKER not in card:
        raise ExportError(f"{CARD.name} has no {MARKER} line to put the statistics in")
    (out / "README.md").write_text(card.replace(MARKER, statistics(items)), encoding="utf-8")
    return _write_checksums(out)


def _write_checksums(out: Path) -> list[Path]:
    files = sorted(path for path in out.rglob("*") if path.is_file())
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(out).as_posix()}"
        for path in files
    ]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [*files, out / "SHA256SUMS"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.corpus.export",
        description="Build the dataset folder for the maintainer to publish.",
    )
    parser.add_argument("golden", type=Path, help="the frozen golden file")
    parser.add_argument("out", type=Path, help="the folder to create (it must not exist)")
    parser.add_argument("--draft", action="store_true", help="build even if the file is a draft")
    args = parser.parse_args(argv)
    try:
        files = build(args.golden, args.out, draft=args.draft)
    except ExportError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"wrote {len(files)} files to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
