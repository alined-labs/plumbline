# Corpus

`manifest.json` lists every source: one edition of one law, with its URL, retrieval date, sha256 and licence basis (`plumbline.corpus.manifest.Source`). `make check` validates it and checks every committed file's hash.

- `raw/`: sources whose licence allows redistribution, committed byte for byte (`raw/.gitattributes` stops git from converting their line endings, which would break their hashes).
- `fetched/`: sources fetched at build time by `make fetch` and never committed (the Dubai PDFs). Git ignores this folder; the manifest still pins their hashes.

Lane B owns this folder. `DATA_LICENSES.md` explains each basis.

## Fetching

`plumbline.corpus.fetch` declares every source in one table (`SOURCES`) and writes the files and the manifest rows from it.

- `make fetch` downloads what is missing: a fetch-only source on a fresh clone, kept only if it matches its pinned hash, or a newly declared source, which it pins. Files already on disk are only checked.
- `uv run python -m plumbline.corpus.fetch --check` downloads every source again and reports any whose text no longer matches its pin. It writes nothing.
- `uv run python -m plumbline.corpus.fetch --repin ID ...` downloads those sources again and rewrites their files and rows, once you have reviewed the change.

Some publishers wrap the statute in parts that change from one download to the next: Online Sunshine prints the day's date, and flsenate.gov adds form tokens. For those, the declaration names the statute's own elements to keep, and the file holds those elements, cut byte for byte, one per line. Their hash is then the same on every download, and the Florida cuts hash the same on both of the Legislature's sites.

## Formats

- Florida (`fl-stat-*`): the Florida Legislature's statute markup, UTF-8. A `div.Section` holds `span.SectionNumber` (the number, then an em space), `span.Catchline` and `span.SectionBody`, whose `div.Subsection`, `div.Paragraph`, `div.SubParagraph` and `div.SubSubParagraph` each start with a `span.Number` such as `(1)`, `(a)`, `1.` or `a.`. The `div.History` and any `div.Note` follow the body. A footnote mark (`<sup>`) can precede a section number, as on s. 83.5615.
