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

## Adding a source

A source is one edition of one law. `make check` fails until each of these is done.

1. **Read the publisher's terms and write the basis down.** Add a row to `DATA_LICENSES.md` that names the source's id and gives its basis word for word, between backticks, as the manifest will record it. If the terms do not allow redistribution the source is fetch-only (`committed=False`): `make fetch` downloads it into `fetched/`, which git ignores, and only its manifest row is committed.
2. **Declare it** in `SOURCES` in `plumbline/corpus/fetch.py` with a `Declared(...)`: `id` (`<law>-<edition>`, unique), `law` (stable across editions: what a gold reference's `law` names), `title`, `jurisdiction`, `language`, `url` (HTTPS; plain HTTP only for a host named in `PLAIN_HTTP_HOSTS`, with the reason), `edition` (what a reference's `edition` names; there is one source per law and edition), `format` (`pdf`, `html`, `xml`, `txt` or `md`), `license_basis` and `committed`. Add as needed `consolidated_on`, `notes`, `keep` (the page's own elements to keep, when the rest of the page changes from one download to the next), `accept` (an Accept header) and `parts` (more URLs joined into the same file).
3. **Pin it.** `make fetch` downloads the source, cuts it as declared, writes the file (`raw/` for a committed source, `fetched/` otherwise), hashes it and writes its manifest row. Then run `uv run python -m plumbline.corpus.fetch --check`: a source that does not match its own pin straight after pinning has a part that changes between downloads, and needs `keep` markers. Commit the manifest, and the file if the source is committed.
4. **Teach the readers.** `plumbline.corpus.refs.article_exists` and `article_text` must know how the source numbers its articles, so that a golden reference to it can be checked, and Lane D's reader in `plumbline.ingest` must read its format. Add a test with a real article of the source.
5. **Run `make check`.** It validates the manifest, every committed file's hash, the licence rows, that no file under `raw/` lacks a manifest row, and every golden reference.

When the publisher changes a pinned text, `--check` says so. `--repin ID` pins the new text once you have read the difference. A new edition of a law is a new source: a new id and edition, the same `law`, so references already written keep pointing at the text they were written against.

## Formats

- Florida (`fl-stat-*`): the Florida Legislature's statute markup, UTF-8. A `div.Section` holds `span.SectionNumber` (the number, then an em space), `span.Catchline` and `span.SectionBody`, whose `div.Subsection`, `div.Paragraph`, `div.SubParagraph` and `div.SubSubParagraph` each start with a `span.Number` such as `(1)`, `(a)`, `1.` or `a.`. The `div.History` and any `div.Note` follow the body. A footnote mark (`<sup>`) can precede a section number, as on s. 83.5615.
- Spain (`es-*`): the BOE's consolidated-legislation open-data record, UTF-8 XML. `metadatos` holds `fecha_actualizacion` (the edition) and the law's status, `analisis` the norms it amends and that amend it, and `texto` one `bloque` per article or heading (`id`, `tipo`, `titulo`) with every `version` of its wording: `id_norma` (the norm that set it), `fecha_publicacion` and `fecha_vigencia` (when it took effect). Inside a version, `p.articulo` is the heading, `p.parrafo` the text, and a `blockquote` the BOE's notes on the amendments. Some versions have an empty `fecha_vigencia`, and their note gives the dates: the last version of LAU art. 10 carries RDL 29/2026's wording, in effect from 2026-10-08, and quotes RDL 28/2026's, from 2026-11-15.
- Dubai (`dubai-*`, fetch-only): PDFs with a text layer. The laws are the Supreme Legislation Committee's English translations, and the Arabic text prevails. Art. 1 of Law No. (33) of 2008 restates eleven articles of Law No. (26) of 2007 under their original numbers, so those articles have two texts, the original and the restated one, and the restated one applies. The DLD's tenancy guide reproduces the tenancy legislation, including Decree No. (43) of 2013 on rent increases, but its text layer drops every "fi" ligature ("frst" for "first").
- Colombia (`co-*`, fetch-only): the Senado's basedoc pages, which declare ISO-8859-1 but are Windows-1252, each followed by the script that fills its note boxes, every part after a line `<!-- plumbline part: <url> -->` and each script wrapped in `<script>` tags, so that an HTML reader skips it (its "Legislación Anterior" boxes hold superseded wordings of articles, which must not be read as law). A box is an `a.caja_vja_encabezado` link to `insRowN()` (Notas de Vigencia, Jurisprudencia Vigencia, Legislación Anterior) followed by an empty `table#TableN`; the page's script holds the box's HTML in `insRowN`'s `description[0]`. Struck-down text is replaced inline by a marker such as `<Inciso 3o. INEXEQUIBLE>`.

## Gaps

Sources the plan names that are not in the corpus yet, and what lets them in:

- Dubai, Law No. (4) of 2026 regulating the management and occupancy of shared housing, announced by the Dubai Media Office on 2026-03-11, in force 180 days after its publication in the Official Gazette (reported as 2026-08-26): the Dubai Legislation Portal has no English text of it, and Arabic is not ingested. It is declared when the portal publishes its English translation.
- The UAE Civil Transactions Law: Federal Law No. (5) of 1985 was repealed by Federal Decree-Law No. (25) of 2025, in force from 2026-06-01. Its official portal, uaelegislation.gov.ae, refuses automated downloads, so `make fetch` cannot fetch it. It is pinned as a fetch-only source once its official PDF is saved by hand into `fetched/`, with the scope of its lease articles checked and recorded in the source's notes.

Until then, questions that need either law are out of scope for the golden set.

One more gap the plan does not name: Spain's Real Decreto-ley 29/2026 (BOE-A-2026-20823, in force from 2026-10-08) amends the LAU, which the pinned LAU holds, but its fifth and sixth final provisions act on existing leases directly (an extraordinary extension of up to two years at the end of the compulsory term, and a 2% cap on yearly rent updates until 2027-12-31), and those are not in the LAU's text. As of 2026-10-20 Congress has neither validated nor repealed it. It can be pinned from the same BOE open-data record, under the same reuse conditions, once Congress has voted; until then a question that needs those provisions is partial. `data/golden/drafts/NOTES.md` has the detail.
