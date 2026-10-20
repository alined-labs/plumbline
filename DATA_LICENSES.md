# Data licences

The code is under the Apache License 2.0 (`LICENSE`). The data is not: each source keeps its own terms, recorded here and, per source, in the manifest's `license_basis` (`data/corpus/manifest.json`). `make check` fails unless every source in the manifest has a row below that names its id and its basis, word for word. This is my reading of each publisher's terms, checked when each source was fetched; it is not legal advice.

## Sources

| Source (manifest id) | Publisher and terms | Basis (as the manifest records it) | Use |
| --- | --- | --- | --- |
| `fl-stat-83-2026`: Florida Statutes 2026, ch. 83, part II | The Florida Legislature, [Online Sunshine](https://www.leg.state.fl.us/statutes/) | `Public domain (government edicts doctrine)` | Committed |
| `fl-stat-718-2026`: Florida Statutes 2026, ss. 718.110, 718.112, 718.116 | The Florida Legislature, [Online Sunshine](https://www.leg.state.fl.us/statutes/) | `Public domain (government edicts doctrine)` | Committed |
| `es-lau-boe-2026-10-13`: Ley 29/1994 de Arrendamientos Urbanos, consolidated | Agencia Estatal Boletín Oficial del Estado, [conditions of reuse](https://www.boe.es/informacion/aviso_legal/index.php) | `BOE reuse conditions: source and update date cited; consolidated text, informational only` | Committed |
| `es-lph-boe-2026-10-05`: Ley 49/1960 sobre propiedad horizontal, consolidated | Agencia Estatal Boletín Oficial del Estado, [conditions of reuse](https://www.boe.es/informacion/aviso_legal/index.php) | `BOE reuse conditions: source and update date cited; consolidated text, informational only` | Committed |
| `dubai-law-26-2007-dlp-2024-12-20`: Law No. (26) of 2007, English translation | The Supreme Legislation Committee, Dubai Legislation Portal, [terms and conditions of use](https://dlp.dubai.gov.ae/en/Pages/TermsAndConditions.aspx) | `Dubai Legislation Portal terms: personal and research use only, no redistribution` | Fetch-only |
| `dubai-law-33-2008-dlp-2023-08-07`: Law No. (33) of 2008, English translation | The Supreme Legislation Committee, Dubai Legislation Portal, [terms and conditions of use](https://dlp.dubai.gov.ae/en/Pages/TermsAndConditions.aspx) | `Dubai Legislation Portal terms: personal and research use only, no redistribution` | Fetch-only |
| `dubai-dld-tenancy-guide-2020-02-07`: the Tenancy Guide | [Dubai Land Department](https://dubailand.gov.ae/) | `Dubai Land Department publication: research use, no redistribution` | Fetch-only |
| `co-ley-820-senado-2026-10-15`: Ley 820 de 2003, with its validity notes | Secretaría General del Senado, [basedoc](http://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html), compiled by Avance Jurídico | `Ley 23 de 1982, art. 41 for the law text; the editor's notes are protected: fetch-only` | Fetch-only |
| `co-ley-675-senado-2026-10-15`: Ley 675 de 2001, with its validity notes | Secretaría General del Senado, [basedoc](http://www.secretariasenado.gov.co/senado/basedoc/ley_0675_2001.html), compiled by Avance Jurídico | `Ley 23 de 1982, art. 41 for the law text; the editor's notes are protected: fetch-only` | Fetch-only |

Committed sources live in `data/corpus/raw/`; fetch-only sources are downloaded by `make fetch` into `data/corpus/fetched/`, which git ignores, and checked against the manifest's hash.

## The bases

**Florida: public domain.** Statutes are not subject to copyright: the government edicts doctrine covers works that legislators create in the course of their duties (*Georgia v. Public.Resource.Org, Inc.*, 590 U.S. 255 (2020)). Florida Statutes 2026 is the official statute law of the state (s. 11.2421, Florida Statutes). The Legislature's copyright notice covers its website; the committed files hold only the statute markup, cut from the page. Every citation names the edition year.

**Spain: the BOE's conditions of reuse.** The BOE's content may be reused, commercially or not, on these conditions: cite the source ("Fuente de los datos: Agencia Estatal Boletín Oficial del Estado") and the date of its last update; do not distort the meaning; do not suggest that the reuse is official or endorsed by the BOE; identify any change as such; keep the update-date metadata intact; and label consolidated legislation as a consolidated text of a merely informative character. Only the BOE's official editions are authentic. The committed records keep their metadata, including `fecha_actualizacion`, and every citation names the BOE and the consolidation date.

**Dubai: the portal's terms of use.** The Dubai Legislation Portal allows its material to be downloaded, stored and used for personal use or research only, and forbids republishing, redistributing, or making it available on any web portal or online service without the Supreme Legislation Committee's written consent. So no Dubai file is ever committed: `make fetch` downloads them at build time for indexing and evaluation. The English texts are translations; the Arabic text prevails. Whether the public demo may show Dubai text, even in short quoted spans, is open until the Committee's consent is sought; until then, treat answers that quote Dubai text as research use. The Dubai Land Department's terms page could not be read when the guide was fetched (HTTP 500 on 2026-10-20), so the guide is held to the same rule as the portal's laws.

**Colombia: the law is free, the notes are not.** Ley 23 de 1982 on copyright, art. 41, lets anyone reproduce laws and other official acts, provided the reproduction follows the official edition. That covers the text of Ley 820 de 2003 and Ley 675 de 2001, but not their validity notes: the Secretaría del Senado publishes Avance Jurídico's annotated compilation, whose pages state that the notes, concordances, editor's notes and the compilation's presentation are protected by copyright and forbid copying, reproducing or disseminating them. So neither file is committed: `make fetch` downloads them at build time, the index carries the law text and each provision's status, and answers quote a note only in a short span, attributed. The Senado served no HTTPS when they were pinned, so they are fetched over HTTP and held to their sha256; before pinning, their law text was compared with the copy of the same compilation the Ministry of Foreign Affairs publishes over HTTPS, and matched except for amendments that older copy lacks.

Arabic text is not ingested; this is stated as a limitation.

## Plumbline's own data

| Data | Licence |
| --- | --- |
| The golden set's questions, reference answers and verification records (`data/golden/`) | CC BY 4.0 |
| The synthetic leases and their expected findings (`data/leases/`) | CC BY 4.0 |
| Model-output recordings (`cache/`) | CC BY 4.0 for Plumbline's prompts; the quoted statute text inside them keeps its source's terms |

The golden set's questions paraphrase real questions from official FAQs and public forums; none is copied.
