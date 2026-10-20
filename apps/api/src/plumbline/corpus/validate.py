"""Validate the data `make check` depends on: the corpus manifest, every committed source's
hash, the licence row of every source, and every golden-set file. Lane B extends it
(synthetic leases and their expected findings, scanned pages).

    uv run python -m plumbline.corpus.validate
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.settings import ROOT
from rag_eval.schema import GoldenFileError, load_golden

LICENCES = ROOT / "DATA_LICENSES.md"


def check_sources(manifest: Manifest, root: Path = ROOT) -> list[str]:
    """Problems with the files behind the manifest; a fetch-only source that has not been
    fetched yet is not a problem (CI never fetches)."""
    problems: list[str] = []
    for source in manifest.sources:
        file = root / source.path
        if not file.is_file():
            if source.committed:
                problems.append(f"{source.id}: {source.path} is missing")
            continue
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != source.sha256:
            problems.append(f"{source.id}: sha256 is {digest}, the manifest says {source.sha256}")
    return problems


def check_editions(manifest: Manifest) -> list[str]:
    """One edition of one law is one source: two would make an ArticleRef ambiguous. This
    judges the committed manifest, not the model, so a test may build any manifest it needs."""
    editions = Counter((source.law, source.edition) for source in manifest.sources)
    return [
        f"{law} {edition}: more than one source for the same law and edition"
        for (law, edition), count in sorted(editions.items())
        if count > 1
    ]


def check_unlisted(manifest: Manifest, root: Path = ROOT) -> list[str]:
    """Files under data/corpus/raw/ that no committed source owns: nobody pinned their
    hash or recorded their licence, so they must not ship."""
    raw = root / "data" / "corpus" / "raw"
    if not raw.is_dir():
        return []
    owned = {source.path for source in manifest.sources if source.committed}
    files = (path for path in sorted(raw.iterdir()) if path.name != ".gitattributes")
    return [
        f"{path.relative_to(root)}: under raw/ but in no manifest row"
        for path in files
        if path.relative_to(root).as_posix() not in owned
    ]


def check_licences(manifest: Manifest, licences: str) -> list[str]:
    """Every source needs a line in DATA_LICENSES.md that names its id and its licence
    basis, each in backticks and word for word: no source enters the corpus on a basis
    nobody has written down, and a basis cannot drift from the one documented."""
    lines = licences.splitlines()
    problems: list[str] = []
    for source in manifest.sources:
        rows = [line for line in lines if f"`{source.id}`" in line]
        if not rows:
            problems.append(f"{source.id}: no row in DATA_LICENSES.md")
        elif not any(f"`{source.license_basis}`" in row for row in rows):
            problems.append(
                f"{source.id}: its row in DATA_LICENSES.md does not give the basis "
                f"`{source.license_basis}`"
            )
    return problems


def check_golden(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for path in sorted((root / "data" / "golden").glob("**/*.jsonl")):
        try:
            load_golden(path)
        except GoldenFileError as exc:
            problems.append(str(exc))
    return problems


def main() -> int:
    try:
        manifest = load_manifest(MANIFEST)
    except (OSError, ValidationError, ValueError) as exc:
        print(f"{MANIFEST.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return 1
    problems = (
        check_sources(manifest)
        + check_editions(manifest)
        + check_unlisted(manifest)
        + check_licences(manifest, LICENCES.read_text(encoding="utf-8"))
        + check_golden()
    )
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"data ok: {len(manifest.sources)} sources in the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
