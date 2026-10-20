"""Validate the data `make check` depends on: the corpus manifest, every committed source's
hash, the licence row of every source, the synthetic leases' expected findings, and every
golden-set file.

    uv run python -m plumbline.corpus.validate
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from plumbline.corpus.leases import clauses, load_expected, squeeze
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


def check_leases(manifest: Manifest, root: Path = ROOT) -> list[str]:
    """Every synthetic lease has expected findings; every finding and lawful clause names a
    clause of its lease, quotes it word for word, and cites a law and edition that are in
    the manifest, of the lease's own jurisdiction."""
    folder = root / "data" / "leases"
    leases = {path.stem: path for path in folder.glob("*.md") if path.name != "README.md"}
    expected_file = folder / "expected_findings.json"
    if not expected_file.is_file():
        return [f"{expected_file.relative_to(root)} is missing"] if leases else []
    try:
        expected = load_expected(expected_file)
    except (ValidationError, ValueError) as exc:
        return [f"{expected_file.relative_to(root)}: {exc}"]
    editions = {(source.law, source.edition): source for source in manifest.sources}
    listed = [lease.lease_id for lease in expected.leases]
    problems = [
        f"{lease_id}: listed twice"
        for lease_id in sorted(set(listed))
        if listed.count(lease_id) > 1
    ]
    problems += [
        f"{name}.md: no entry in expected_findings.json"
        for name in sorted(set(leases) - set(listed))
    ]
    for lease in expected.leases:
        path = leases.get(lease.lease_id)
        if path is None:
            problems.append(f"{lease.lease_id}: expected_findings.json lists a lease with no file")
            continue
        text = path.read_text(encoding="utf-8")
        if lease.signed_on.isoformat() not in text:
            problems.append(
                f"{lease.lease_id}: the lease does not state its signing date {lease.signed_on}"
            )
        sections = clauses(text)
        cited = [(item.clause, item.quote, item.violates) for item in lease.findings]
        cited += [(item.clause, item.quote, item.allowed_by) for item in lease.lawful]
        for clause, quote, ref in cited:
            where = f"{lease.lease_id} clause {clause}"
            source = editions.get((ref.law, ref.edition))
            if source is None:
                problems.append(f"{where}: {ref.law} edition {ref.edition} is not in the manifest")
            elif not source.jurisdiction == ref.jurisdiction == lease.jurisdiction:
                problems.append(f"{where}: {ref.key} is not {lease.jurisdiction.value} law")
            if clause not in sections:
                problems.append(f"{where}: the lease has no such clause")
            elif squeeze(quote) not in squeeze(sections[clause]):
                problems.append(f"{where}: the quote is not in the clause")
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
        + check_leases(manifest)
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
