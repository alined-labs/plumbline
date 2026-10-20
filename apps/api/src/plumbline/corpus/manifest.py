"""The corpus manifest (data/corpus/manifest.json): one row per source, so every text the
system answers from is pinned to an edition, a URL, a hash and a licence basis.

Sources whose licence allows it are committed under data/corpus/raw/; the others (the
Dubai PDFs) are fetched at build time into data/corpus/fetched/, which git ignores, and
checked against the same hash.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from plumbline.core.types import Jurisdiction, Language
from plumbline.settings import ROOT

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=80)]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
# xml: the BOE's consolidated-legislation records, every block with all its versions.
Format = Literal["pdf", "html", "xml", "txt", "md"]
MANIFEST = ROOT / "data" / "corpus" / "manifest.json"
# Publishers that serve no HTTPS. The Senado refused connections on port 443 when Ley 820
# and Ley 675 were pinned (2026-10-20), and their text was checked against the HTTPS copy
# the Cancillería publishes of the same compilation. Drop a host once it serves HTTPS.
PLAIN_HTTP_HOSTS: Final = frozenset({"www.secretariasenado.gov.co"})


class Source(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug  # one edition of one law: "fl-stat-83-2026"
    law: Slug  # stable across editions: "fl-stat-83"; what ArticleRef.law names
    title: NonEmpty
    jurisdiction: Jurisdiction
    language: Language
    url: HttpUrl
    # Further URLs joined into the same file after `url`, each after a line naming it: the
    # other pages of a law its publisher splits, and the scripts that hold its notes.
    parts: list[HttpUrl] = Field(default_factory=list)
    edition: NonEmpty  # what ArticleRef.edition names: "2026", "boe-2025-03-26"
    consolidated_on: date | None = None
    retrieved_on: date
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    format: Format
    license_basis: NonEmpty  # one line; DATA_LICENSES.md has the detail
    committed: bool  # False: fetched at build time, never committed
    path: NonEmpty  # repo-relative: data/corpus/raw/... or data/corpus/fetched/...
    notes: str | None = None

    @model_validator(mode="after")
    def _where(self) -> Self:
        folder = "data/corpus/raw/" if self.committed else "data/corpus/fetched/"
        if not self.path.startswith(folder):
            raise ValueError(f"{self.id}: path must be under {folder}")
        for url in (self.url, *self.parts):
            plain = url.scheme == "http" and url.host in PLAIN_HTTP_HOSTS
            if url.scheme != "https" and not plain:
                raise ValueError(f"{self.id}: the source URL must be https: {url}")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    sources: list[Source]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return self

    def by_id(self) -> dict[str, Source]:
        return {s.id: s for s in self.sources}


def load_manifest(path: Path = MANIFEST) -> Manifest:
    return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_manifest(manifest: Manifest, path: Path = MANIFEST) -> None:
    """Write the manifest as the fetch script keeps it: two-space JSON, rows in the order
    they are declared, every field present."""
    text = json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
    path.write_text(f"{text}\n", encoding="utf-8")
