"""`make ingest` (Lane D): from the corpus manifest to parsed documents, logged per source.

    uv run python -m plumbline.ingest [--source ID ...]

Each source's parse is read back from data/processed/ while its hash matches the
manifest's, and parsed only when it is missing or stale; a fetch-only source that is not
on this machine (make fetch) is reported and skipped. A fetch-only source's parse and
recordings stay under data/corpus/fetched/ (plumbline.ingest.processed), so in replay
mode one that this machine never parsed is reported and skipped too. The chunk, embed and index stages
follow (task D4) once the chunker and the embedder have merged.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from plumbline.cache import CacheMiss, ResponseCache, get_cache
from plumbline.corpus.manifest import MANIFEST, load_manifest
from plumbline.ingest.parse import DoclingClient, ParseError, parse_source
from plumbline.ingest.processed import (
    FETCHED,
    PROCESSED,
    local_cache,
    local_processed,
    read_processed,
    write_processed,
)
from plumbline.ingest.vision import VisionReader
from plumbline.settings import ROOT, get_settings

log = logging.getLogger("plumbline.ingest")


def main(
    argv: Sequence[str] | None = None,
    *,
    manifest: Path = MANIFEST,
    root: Path = ROOT,
    processed: Path = PROCESSED,
    fetched: Path = FETCHED,
) -> int:
    parser = argparse.ArgumentParser(description="Parse the corpus into data/processed/.")
    parser.add_argument("--source", action="append", help="only this source id (repeatable)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sources = load_manifest(manifest).sources
    if args.source:
        unknown = set(args.source) - {s.id for s in sources}
        if unknown:
            parser.error(f"not in the manifest: {', '.join(sorted(unknown))}")
        sources = [s for s in sources if s.id in args.source]
    settings = get_settings()
    caches = {  # by `committed`: recordings of committed sources go in git, the rest do not
        True: get_cache(),
        False: ResponseCache(settings.cache_mode, local_cache(fetched)),
    }
    docling = {kept: DoclingClient(settings.docling_url, cache) for kept, cache in caches.items()}
    vision = {kept: VisionReader(cache) for kept, cache in caches.items()}
    outcome: Counter[str] = Counter()
    for source in sources:
        path = root / source.path
        if not path.exists():
            log.warning(
                "%s: %s is not on this machine (make fetch); skipped", source.id, source.path
            )
            outcome["missing"] += 1
            continue
        folder = processed if source.committed else local_processed(fetched)
        document = read_processed(source, folder)
        status = "reused"
        if document is None:
            try:
                document = parse_source(
                    source, path.read_bytes(), docling[source.committed], vision[source.committed]
                )
            except CacheMiss:
                log.warning(
                    "%s: never parsed on this machine, and replay mode cannot call docling or the"
                    " vision model; parse it once with make up-ingest and CACHE_MODE=record"
                    " make ingest",
                    source.id,
                )
                outcome["unparsed"] += 1
                continue
            except ParseError:
                log.exception("%s: parsing failed", source.id)
                outcome["failed"] += 1
                continue
            write_processed(document, folder)
            status = "parsed"
        outcome[status] += 1
        methods = Counter(page.method.value for page in document.pages)
        log.info(
            "%s: %s, %d pages (%s), %d characters",
            source.id,
            status,
            len(document.pages),
            ", ".join(f"{n} {method}" for method, n in sorted(methods.items())),
            len(document.markdown),
        )
    log.info(
        "%d sources: %s", len(sources), ", ".join(f"{n} {k}" for k, n in sorted(outcome.items()))
    )
    return 1 if outcome["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
