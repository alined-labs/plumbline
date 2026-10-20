"""Validate the data `make check` depends on: the corpus manifest, every committed source's
hash, the licence row of every source, the synthetic leases' expected findings and their
scanned pages, every golden-set file, and that the golden drafts agree with each other.

    uv run python -m plumbline.corpus.validate
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from plumbline.corpus.export import WITHHELD
from plumbline.corpus.leases import ExpectedFindings, clauses, load_expected, squeeze
from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.corpus.refs import article_exists
from plumbline.settings import ROOT
from rag_eval.schema import (
    ArticleRef,
    Category,
    GoldenFileError,
    GoldenItem,
    Jurisdiction,
    Split,
    load_golden,
)

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


def check_ref(
    where: str, ref: ArticleRef, manifest: Manifest, root: Path, jurisdiction: Jurisdiction | None
) -> list[str]:
    """One ArticleRef: its law and edition are in the manifest, the law is of `jurisdiction`
    when one is given, and the article is in the pinned file (when the file is here)."""
    source = {(s.law, s.edition): s for s in manifest.sources}.get((ref.law, ref.edition))
    if source is None:
        return [f"{where}: {ref.law} edition {ref.edition} is not in the manifest"]
    if source.jurisdiction != ref.jurisdiction or jurisdiction not in (None, ref.jurisdiction):
        return [f"{where}: {ref.key} is not {(jurisdiction or ref.jurisdiction).value} law"]
    if article_exists(source, ref.article, root) is False:
        return [f"{where}: article {ref.article} is not in {source.id}"]
    return []


def check_leases(manifest: Manifest, root: Path = ROOT) -> list[str]:
    """Every synthetic lease has expected findings; every finding and lawful clause names a
    clause of its lease, quotes it word for word, and cites an article that is in the pinned
    edition of a law in the manifest, of the lease's own jurisdiction."""
    folder = root / "data" / "leases"
    leases = {path.stem: path for path in folder.glob("*.md") if path.name != "README.md"}
    expected_file = folder / "expected_findings.json"
    if not expected_file.is_file():
        return [f"{expected_file.relative_to(root)} is missing"] if leases else []
    try:
        expected = load_expected(expected_file)
    except (ValidationError, ValueError) as exc:
        return [f"{expected_file.relative_to(root)}: {exc}"]
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
            problems += check_ref(where, ref, manifest, root, lease.jurisdiction)
            if clause not in sections:
                problems.append(f"{where}: the lease has no such clause")
            elif squeeze(quote) not in squeeze(sections[clause]):
                problems.append(f"{where}: the quote is not in the clause")
    return problems


def check_scans(root: Path = ROOT) -> list[str]:
    """Every scanned page has its expected text, and every expected text its page, and each
    belongs to a lease that exists, with the whole lease's scanned PDF beside them."""
    folder = root / "data" / "leases" / "scans"
    if not folder.is_dir():
        return []
    pages = re.compile(r"^(?P<lease>[a-z0-9-]+)-p(?P<page>\d+)\.(?P<kind>png|txt)$")
    found: dict[tuple[str, str], set[str]] = {}
    problems: list[str] = []
    for path in sorted(folder.iterdir()):
        match = pages.match(path.name)
        if match is None:
            if not path.name.endswith(".pdf"):
                problems.append(f"data/leases/scans/{path.name}: not a scanned page")
            continue
        found.setdefault((match["lease"], match["page"]), set()).add(match["kind"])
    for (lease, page), kinds in sorted(found.items()):
        if kinds != {"png", "txt"}:
            problems.append(f"{lease}-p{page}: needs both a .png and its expected .txt")
        if not (root / "data" / "leases" / f"{lease}.md").is_file():
            problems.append(f"{lease}-p{page}: there is no lease {lease}.md")
        if not (folder / f"{lease}.pdf").is_file():
            problems.append(f"{lease}: its scanned pages have no {lease}.pdf")
    return problems


def check_golden(root: Path = ROOT, manifest: Manifest | None = None) -> list[str]:
    """Every golden file validates. With the manifest, every gold reference is also checked:
    its law and edition are in the manifest, and its article is in the pinned file. A
    lease-check item must read a lease that exists, be dated with that lease's signing date,
    and cite only articles the lease's expected findings plant or allow. A verified item that
    cites a fetch-only source holds the withheld marker in `quoted_text`, never the text, since
    those sources' terms forbid a copy in the repository. Only `golden_v*.jsonl`
    files are golden files; other lists beside them (second sources, the cross-check) are not."""
    problems: list[str] = []
    expected = _expected(root) if manifest is not None else {}
    for path in sorted((root / "data" / "golden").glob("**/golden_v*.jsonl")):
        try:
            items = load_golden(path)
        except GoldenFileError as exc:
            problems.append(str(exc))
            continue
        if manifest is None:
            continue
        for item in items:
            where = f"{path.name} {item.id}"
            for ref in item.gold_refs:
                problems += check_ref(where, ref, manifest, root, None)
            if item.category is Category.LEASE_CHECK:
                problems += _check_lease_item(where, item, expected)
            if item.verification is not None and item.verification.quoted_text != WITHHELD:
                committed = {(s.law, s.edition): s.committed for s in manifest.sources}
                if not all(committed.get((r.law, r.edition), False) for r in item.gold_refs):
                    problems.append(
                        f"{where}: quotes a fetch-only source; store the withheld marker"
                    )
    return problems


def check_versions(root: Path = ROOT) -> list[str]:
    """A later draft keeps every item of an earlier draft, unchanged. While v0 is still being
    verified, a fix made to one of its items has to be made in the v1 draft too, or the two
    would quietly say different things. The `split` and `verification` fields are left out:
    the freeze sets the first and the verifier the second."""
    drafts: dict[int, dict[str, dict[str, Any]]] = {}
    names: dict[int, str] = {}
    for path in sorted((root / "data" / "golden" / "drafts").glob("golden_v*.jsonl")):
        named = re.fullmatch(r"golden_v(\d+)\.jsonl", path.name)
        if named is None:
            continue
        try:
            items = load_golden(path)
        except GoldenFileError:
            continue  # check_golden reports it
        number = int(named[1])
        names[number] = path.name
        drafts[number] = {
            item.id: item.model_dump(exclude={"split", "verification"}) for item in items
        }
    problems = []
    for earlier, before in drafts.items():
        for later, kept in drafts.items():
            if later <= earlier:
                continue
            for item_id, content in before.items():
                if item_id not in kept:
                    problems.append(f"{names[later]}: {item_id} from {names[earlier]} is missing")
                elif kept[item_id] != content:
                    changed = sorted(key for key in content if content[key] != kept[item_id][key])
                    problems.append(
                        f"{names[later]}: {item_id} differs from {names[earlier]} in "
                        f"{', '.join(changed)}"
                    )
    return problems


def check_frozen(root: Path = ROOT) -> list[str]:
    """A frozen `golden_v<N>.jsonl` keeps what freezing promises: every item is verified, none
    was added in a later version, and from v1 on every item is in dev or test. The merge queue
    holds the file until the human has read every line; this stops an unfinished one reaching it."""
    problems: list[str] = []
    for path in sorted((root / "data" / "golden").glob("golden_v*.jsonl")):
        named = re.fullmatch(r"golden_v(\d+)\.jsonl", path.name)
        if named is None:
            continue
        number = int(named[1])
        try:
            items = load_golden(path)
        except GoldenFileError:
            continue  # check_golden reports it
        for item in items:
            where = f"{path.name} {item.id}"
            if item.verification is None:
                problems.append(f"{where}: frozen but not verified")
            if int(item.added_in[1:]) > number:
                problems.append(f"{where}: added in {item.added_in}, after this version")
            if number >= 1 and item.split is Split.UNASSIGNED:
                problems.append(f"{where}: frozen without a dev or test split")
    return problems


def _expected(root: Path) -> dict[str, tuple[date, set[str]]]:
    """Each lease's signing date and the article keys its expected findings cite."""
    file = root / "data" / "leases" / "expected_findings.json"
    if not file.is_file():
        return {}
    found: ExpectedFindings = load_expected(file)
    return {
        lease.lease_id: (
            lease.signed_on,
            {f.violates.key for f in lease.findings} | {w.allowed_by.key for w in lease.lawful},
        )
        for lease in found.leases
    }


def _check_lease_item(
    where: str, item: GoldenItem, expected: dict[str, tuple[date, set[str]]]
) -> list[str]:
    if item.lease_id not in expected:
        return [f"{where}: there is no lease {item.lease_id} in expected_findings.json"]
    signed, keys = expected[item.lease_id]
    problems = []
    if item.signed_on != signed:
        problems.append(f"{where}: signed_on is {item.signed_on}, the lease was signed {signed}")
    problems += [
        f"{where}: {ref.key} is not an article {item.lease_id}'s findings cite"
        for ref in item.gold_refs
        if ref.key not in keys
    ]
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
        + check_scans()
        + check_golden(manifest=manifest)
        + check_versions()
        + check_frozen()
    )
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"data ok: {len(manifest.sources)} sources in the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
