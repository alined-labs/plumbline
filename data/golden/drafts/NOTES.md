# Golden set drafts: notes for the verifier

Two drafts are here. `golden_v0.jsonl` holds 60 items (Gate 2a). `golden_v1.jsonl` holds 180 (Gate 2): the same 60, word for word, and 120 added in v1. Nothing in either is verified: every `verification` field is empty, every `split` is `unassigned`, and neither file is frozen. These notes say how the drafts were made, what the build already checks, and where a human reading should look hardest.

## What the build already checks

`make check` fails unless, for every item in every draft:

- it validates against `rag_eval.schema.GoldenItem`, and ids are unique;
- each gold reference names a law and edition that are in `data/corpus/manifest.json`, with the law's jurisdiction;
- each gold reference's article **exists in the pinned file** (`plumbline.corpus.refs`). This catches a mistyped or invented article number, not a misread one: an article that exists but does not say what the answer claims is exactly what a human must find. The Dubai and Colombian sources are fetch-only, so this part runs only on a machine where `make fetch` has run;
- a lease-check item reads a lease that exists, carries that lease's signing date as `signed_on`, and cites only articles the lease's `expected_findings.json` plants or allows;
- every item of the v0 draft is in the v1 draft, unchanged except for `split` and `verification`. If you correct a v0 item, correct it in both files.

Once a file is frozen as `data/golden/golden_v<N>.jsonl`, `make check` also demands that every item is verified, that none was added in a later version, and, from v1 on, that every item has its dev or test split.

## Reading the drafts against the statute

`uv run python -m plumbline.corpus.review data/golden/drafts/golden_v1.jsonl` prints each item beside the pinned text of every article it cites: the cited paragraph first, then the start of the article, and for a lease check the lease's planted findings. A Spanish article is shown as it stood on the item's `signed_on` or `as_of` date, with the norm that set that wording. Use `--item ID` for one item, `--prefix fl-` or `--category lease_check` to read a place or a kind of item at a time, `--list` for one line per item, and `--chars 0` for whole articles. The sheet quotes statute text, including Dubai's and Colombia's, which may not be redistributed, so it is for your own reading: do not commit it.

## What is in v1

| | v0 | added in v1 | total |
| --- | ---: | ---: | ---: |
| single article | 17 | 37 | 54 |
| multi article | 9 | 16 | 25 |
| cross jurisdiction | 8 | 16 | 24 |
| numeric or date-conditional | 6 | 13 | 19 |
| out of scope | 8 | 17 | 25 |
| partial | 3 | 2 | 5 |
| lease check | 9 | 19 | 28 |
| **total** | **60** | **120** | **180** |

The plan's mix is single 57, multi 25, cross 24, numeric 19, out of scope 25, partial 2, lease check 28. Partial is 5 because three are real non-Florida cases (`co-0009`, `du-0008`, `du-0027`), as the brief allows; the 3 extra partials come out of single-article, so 54 + 5 = 57 + 2.

By jurisdiction: Florida 30, Spain 36, Colombia 34, Dubai 31 (items about one jurisdiction), 24 comparisons that name two to four, and 25 out-of-scope questions that name none on purpose. Languages: `source_language` is `es` when any gold text is Spanish, `en` otherwise (87 English, 93 Spanish). Difficulty: 38 easy, 73 medium, 69 hard. 38 items carry `as_of` or `signed_on`. The 28 lease checks cover all ten synthetic leases, two to four items each. The items cite 103 different articles of all nine laws; `es-lph` and the DLD guide (4 items each) and `co-ley-675` (6) are the least used.

## The dev/test split

`uv run python -m plumbline.corpus.split data/golden/drafts/golden_v1.jsonl` prints how the 180 items fall into dev (120) and test (60); give it an output path to write the split file. The freeze branch runs it on the verified draft; the draft itself is never split. Each category keeps a third in test, to within one item; within a category each place and then each language keeps its share, by largest remainder; ties go by a hash of the seed and the id, so the result does not depend on the order of lines or on the machine. If you drop or recategorise an item before freezing, the split is recomputed from what is left. As of this commit:

| category | dev | test | all |
| --- | ---: | ---: | ---: |
| cross_jurisdiction | 16 | 8 | 24 |
| lease_check | 19 | 9 | 28 |
| multi_article | 16 | 9 | 25 |
| numeric_date | 13 | 6 | 19 |
| out_of_scope | 17 | 8 | 25 |
| partial | 3 | 2 | 5 |
| single_article | 36 | 18 | 54 |

| place | dev | test | all |
| --- | ---: | ---: | ---: |
| colombia | 23 | 11 | 34 |
| dubai | 21 | 10 | 31 |
| florida | 20 | 10 | 30 |
| none | 17 | 8 | 25 |
| several | 16 | 8 | 24 |
| spain | 23 | 13 | 36 |

| language | dev | test | all |
| --- | ---: | ---: | ---: |
| en | 59 | 28 | 87 |
| es | 61 | 32 | 93 |

Items on the same lease or the same article can land on both sides; the split balances the three strata, not leakage.

## Where each question came from

`source_note` says, item by item, which source was used and how it was read. In v1, 44 items come from official guidance (17 in v0, 27 added), 4 from public forum threads (all v0) and 132 are synthetic (39 in v0, 93 added): the comparisons, the out-of-scope questions, the lease checks and the topics no source reviewed poses. Every question is my own phrasing; none is copied. How the real sources were read:

- **The Florida Bar's consumer pamphlet** (floridabar.org blocks automated access): read in the Internet Archive's copy of 2025-12-24, re-read in full for v1. Its topics seeded `fl-0001`, `0003`, `0004`, `0005`, `0007`, `0008` and, in v1, `fl-0011`, `0012`, `0013`, `0014`, `0018`, `0019`, `0020`, `0022`.
- **The Ministerio de Vivienda's FAQ** (mivau.gob.es, ten questions): read in full. It seeded `es-0001`, `0002`, `0006`. No Spanish item added in v1 is seeded by a source: they are synthetic.
- **Bogotá's Secretaría del Hábitat**: its FAQ page on housing leases (2013, four questions) and its didactic booklet (October 2020, six landlord and nine tenant questions) were read in full. They seeded `co-0001`, `0002`, `0003`, `0004`, `0008`, `0009` and, in v1, `co-0012` (copy of the contract), `0013` (receipts), `0014` (paying by deposit), `0015` (the tenant who does not pay the administration), `0022` (coexistence problems), `0025` (provisional handover of the property), `0029` (repairs and the 30% limit).
- **The DLD's Tenancy Guide** is a registration manual with no questions; it seeded `du-0001` and `du-0007` (it reproduces the legislation). **The DLD's Frequently Asked Questions page** (dubailand.gov.ae, about 400 entries, read on 2026-10-20) answers tenancy and Rental Disputes Centre questions; it seeded `du-0011` to `du-0015`, `du-0021` to `du-0027`. Where the page's answer goes beyond the statute (a lawsuit at the Rental Disputes Centre, proof of return, a "3 months" notice for a rent increase where Law 33/2008 says 90 days), the reference answer follows the statute only, and `source_note` says so.
- **Forum threads**: two Expat.com Spain threads (`es-0004`, `es-0005`) and one Expat.com UAE thread (`du-0008`) were read. For `fl-0002`, only the *title* of a public Avvo question was readable (its page is behind a bot challenge), so the facts in that question are mine.
- Not read, so not claimed: Avvo and Expat Woman threads, the Florida Bar's own pages, Miami-Dade's Notice of Tenant Rights (its PDF returned 404).

## Where to look hardest

1. **Spain is mid-reform, and the BOE record has three steps in October 2026.** Real Decreto-ley 26/2026 (of 29 September, in force 2026-10-01, BOE-A-2026-20266) changed the LAU and added arts. 9 bis and 21 bis; Congress's resolution of 2 October (BOE-A-2026-20526) set that change aside; and Real Decreto-ley 29/2026 (of 6 October, in force 2026-10-08, BOE-A-2026-20823) made it again, with no validation by Congress recorded when the LAU was pinned. Congress must debate it within 30 days, so it may be repealed again. Real Decreto-ley 28/2026 rewords art. 10 from 2026-11-15, and the LPH's art. 10 has a version from 2026-10-23. Date-pinned items rest on the text before October; undated items rest on today's text and use only provisions that are the same before and after. The wording changed in, among others: art. 5(e) (`es-0006`, described neutrally), art. 11 (`es-0010`, `xj-0005`), art. 18.1 (the IPC cap became the IRAV: `xj-0023` is pinned to 2026-03-01), art. 20 (`es-0009`, `es-0029`, `es-0033`), art. 21 (a new paragraph 5 lets the tenant carry out repairs and deduct them from the rent after fifteen days: `xj-0019` is pinned to 2026-03-01; `es-0022` and `xj-0004` rest on paragraphs 1 to 4, which did not change, so their answers are true today but do not mention paragraph 5), art. 25.8 (the waiver of the right of first refusal is now forbidden: `es-0030`), art. 27.2(f), art. 36.5 (rent-default insurance may not be required; temporary leases are capped at one month: `es-0002`, `es-0005`, `xj-0001` describe the rule for ordinary leases) and art. 36.7. Re-check these when you verify.
2. **A stale official source.** The Florida Bar's pamphlet still says, in its landlord section, that a month-to-month tenancy ends on 15 days' notice; its tenant section says 30. The statute, s. 83.57(3), has said 30 days since ch. 2023-314, and `fl-0003` and `xj-0018` follow the statute.
3. **Dubai's rent-increase decree is only in the guide.** Decree No. (43) of 2013 is in the corpus only inside the DLD's 2020 Tenancy Guide, which names its articles by their law. `du-0007`, `du-0009`, `du-0024` and `du-0030` cite it as article `Decree 43/2013 art. 1` of the guide's source (`dubai-dld-tenancy-guide`). The guide is dated 2020, and its list of bands is lettered a, b, c, d, e, f where "b." is only the second line of band a's sentence, so the bands are (a), (c), (d), (e), (f) in the pinned text and the references use those letters; the decree may letter them a to e. Check that the decree is still the rule: the DLD's FAQ page describes a "Smart Residential Rent Index" with increases of 0% to 20%, which fits, but does not name the decree. The chunker does not yet key articles this way (see the note to Lane A).
4. **Law No. (33) of 2008 restates eleven articles of Law No. (26) of 2007** under their old numbers (2, 3, 4, 9, 13, 14, 15, 25, 26, 29 and 36). Gold references for those cite the restated article, law `dubai-law-33-2008`; the superseded original stays in the index, which is deliberate: a system that retrieves it has found text no longer in force. Law 33/2008 has two "Article (2)"; no item cites that number.
5. **Article numbers for the LPH are numeric** (`17` for "Artículo diecisiete"), as lawyers cite it. The pipeline does not parse the LPH's word ordinals yet.
6. **The leases' "lawful lookalikes" are interpretive.** For example, that a co-signer is not a real guarantee under Ley 820 art. 16 (`co-0031`), or that a stated annual IBI is a lawful pass-on under LAU art. 20.1. They come from the statute's wording, not from a second source.
7. **Partial items** (`fl-0008`, `fl-0025`, `co-0009`, `du-0008`, `du-0027`) rely on a stated gap: the Miami-Dade ordinance and a hypothetical city ordinance, the year's price-index figure, Dubai's holiday-home regime, and the Rental Disputes Centre's procedure for a landlord who refuses the rent are not indexed. Confirm each gap is real; I searched the three Dubai sources for `du-0027` and found no such procedure.
8. **Out-of-scope items tied to a gap in the corpus** (`oos-0013`, `oos-0014`) rest on Dubai's Law No. (4) of 2026 and the UAE Civil Transactions Law, which `data/corpus/README.md` lists as not indexed. If either is added, the item must move or go.
9. **Status questions.** `co-0021` asks whether Ley 820 art. 39 is still in force; the Senado's compilation marks it, with arts. 35, 36, 38 and 40, repealed by the Código General del Proceso from 2014-01-01, and the answer rests on that note. The pipeline marks such an article as repealed, and `Chunk.in_force_on` is false for those, so a date-filtered search cannot return it: either status questions have a path that includes repealed provisions, or this item measures that gap. No other item relies on a provision a court struck down or the legislature repealed (Ley 820 art. 12 has two struck-down paragraphs, art. 37 has struck-down words, and the second paragraph of Ley 675 art. 62 is marked repealed; none is cited for what it said).
10. **Florida's s. 83.56 was amended in 2026** (ch. 2026-143): the only change is an added example in subsection (2)(a), "an act of fraudulent entry of a residential dwelling unit"; `xj-0010` and `fl-0026` rest on other parts. The same law's s. 83.684 (ch. 2026-125) is not cited.
11. **Colombian items built on the Civil Code.** `co-0029` and `xj-0019` describe Ley 820 art. 27, whose deduction right applies "in the case of art. 1993 of the Civil Code"; the Civil Code is not indexed, so the answers say so and do not say whether the case applies.

## Second sources to use when verifying

| Jurisdiction | A second source that covers most items |
| --- | --- |
| Florida | the Florida Bar pamphlet (see above); Online Sunshine's own page for each section |
| Spain | the MIVAU FAQ, and the BOE's own consolidated page for each article and date |
| Colombia | the Bogotá booklet and FAQ, and the Ministry of Foreign Affairs' HTTPS copy of the same compilation (`cancilleria.gov.co`, compared with the pinned text before pinning) |
| Dubai | the DLD Tenancy Guide, which reproduces both laws and the decree, and the DLD's FAQ page |
