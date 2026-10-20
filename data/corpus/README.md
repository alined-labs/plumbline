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
- Spain (`es-*`): the BOE's consolidated-legislation open-data record, UTF-8 XML. `metadatos` holds `fecha_actualizacion` (the edition) and the law's status, `analisis` the norms it amends and that amend it, and `texto` one `bloque` per article or heading (`id`, `tipo`, `titulo`) with every `version` of its wording: `id_norma` (the norm that set it), `fecha_publicacion` and `fecha_vigencia` (when it took effect). Inside a version, `p.articulo` is the heading, `p.parrafo` the text, and a `blockquote` the BOE's notes on the amendments. Some versions have an empty `fecha_vigencia`, and their note gives the dates: the last version of LAU art. 10 carries RDL 29/2026's wording, in effect from 2026-10-08, and quotes RDL 28/2026's, from 2026-11-15.
- Dubai (`dubai-*`, fetch-only): PDFs with a text layer. The laws are the Supreme Legislation Committee's English translations, and the Arabic text prevails. Art. 1 of Law No. (33) of 2008 restates eleven articles of Law No. (26) of 2007 under their original numbers, so those articles have two texts, the original and the restated one, and the restated one applies. The DLD's tenancy guide reproduces the tenancy legislation, including Decree No. (43) of 2013 on rent increases, but its text layer drops every "fi" ligature ("frst" for "first").
- Colombia (`co-*`, fetch-only): the Senado's basedoc pages, which declare ISO-8859-1 but are Windows-1252, each followed by the script that fills its note boxes, every part after a line `<!-- plumbline part: <url> -->` and each script wrapped in `<script>` tags, so that an HTML reader skips it (its "Legislación Anterior" boxes hold superseded wordings of articles, which must not be read as law). A box is an `a.caja_vja_encabezado` link to `insRowN()` (Notas de Vigencia, Jurisprudencia Vigencia, Legislación Anterior) followed by an empty `table#TableN`; the page's script holds the box's HTML in `insRowN`'s `description[0]`. Struck-down text is replaced inline by a marker such as `<Inciso 3o. INEXEQUIBLE>`.
