# Data licences

The code is under the Apache License 2.0 (`LICENSE`). The data is not: each source keeps its own terms, recorded here and, per source, in the manifest's `license_basis` (`data/corpus/manifest.json`). This is my reading of each publisher's terms, checked when each source is fetched; it is not legal advice.

## Sources

| Jurisdiction | Sources | Basis | How Plumbline uses them |
| --- | --- | --- | --- |
| Spain | Ley 29/1994 de Arrendamientos Urbanos (LAU) and Ley 49/1960 de Propiedad Horizontal (LPH), consolidated texts from the Boletín Oficial del Estado | The BOE's reuse conditions for its content (cite the source and the date of last update, do not distort the meaning). Consolidated texts are informational; only the official publication is legally valid. | Committed, with the consolidation date; every citation names the BOE and the edition. |
| Colombia | Ley 820 de 2003 (urban housing leases) and Ley 675 de 2001 (horizontal property), official texts with their validity notes | Ley 23 de 1982, art. 41: laws and other official acts may be published freely, provided they match the official text. | Committed, with the source of each text and its validity notes kept verbatim. |
| Florida | 2026 Florida Statutes, chapter 83, part II, and sections 718.110(13), 718.112 and 718.116(11) | Public domain: statutes are not subject to copyright (the government edicts doctrine, *Georgia v. Public.Resource.Org*, 2020). | Committed, with the edition year. |
| Dubai | Law No. 26 of 2007 and Law No. 33 of 2008 (landlord and tenant relations), Law No. 4 of 2026 (shared housing), the tenancy provisions of the UAE Civil Transactions Law, the Dubai Land Department's tenancy guide | Published by the Government of Dubai and the UAE federal government; the English versions are translations and the Arabic text is authoritative. Reuse with attribution and a link to the official source. | **Never committed.** Fetched at build time by `make fetch` and checked against the manifest's hash; answers quote short spans with attribution and a link, and say that the Arabic text governs. |

Arabic text is not ingested; this is stated as a limitation.

## Plumbline's own data

| Data | Licence |
| --- | --- |
| The golden set's questions, reference answers and verification records (`data/golden/`) | CC BY 4.0 |
| The synthetic leases and their expected findings (`data/leases/`) | CC BY 4.0 |
| Model-output recordings (`cache/`) | CC BY 4.0 for Plumbline's prompts; the quoted statute text inside them keeps its source's terms |

The golden set's questions paraphrase real questions from official FAQs and public forums; none is copied.
