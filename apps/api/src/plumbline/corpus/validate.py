"""Validate the data `make check` depends on: the corpus manifest, every committed source's
hash, and every golden-set file. Lane B extends it (synthetic leases and their expected
findings, scanned pages).

    uv run python -m plumbline.corpus.validate
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from pydantic import ValidationError

from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.settings import ROOT
from rag_eval.schema import GoldenFileError, load_golden


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
    problems = check_sources(manifest) + check_golden()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"data ok: {len(manifest.sources)} sources in the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
