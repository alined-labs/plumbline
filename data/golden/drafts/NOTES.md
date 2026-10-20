# Golden set v0 drafts: notes for the verifier

`golden_v0.jsonl` holds 60 drafted items. Nothing in it is verified: every `verification` field is empty, every `split` is `unassigned`, and the file is not frozen. These notes say how the drafts were made, what the machine already checks, and where a human reading should look hardest.

## What the build already checks

`make check` fails unless, for every item:

- it validates against `rag_eval.schema.GoldenItem`, and ids are unique;
- each gold reference names a law and edition that are in `data/corpus/manifest.json`, with the law's jurisdiction;
- each gold reference's article **exists in the pinned file** (`plumbline.corpus.refs`). This catches a mistyped or invented article number, not a misread one: an article that exists but does not say what the answer claims is exactly what a human must find. The Dubai and Colombian sources are fetch-only, so this part runs only on a machine where `make fetch` has run;
- a lease-check item reads a lease that exists, carries that lease's signing date as `signed_on`, and cites only articles the lease's `expected_findings.json` plants or allows.

## Reading the drafts against the statute

`uv run python -m plumbline.corpus.review data/golden/drafts/golden_v0.jsonl` prints each item beside the pinned text of every article it cites: the cited paragraph first, then the start of the article, and for a lease check the lease's planted findings. A Spanish article is shown as it stood on the item's `signed_on` or `as_of` date, with the norm that set that wording. Use `--item ID` for one item and `--chars 0` for whole articles. The sheet quotes statute text, including Dubai's and Colombia's, which may not be redistributed, so it is for your own reading: do not commit it.

## What is in it

| | Items |
| --- | ---: |
| single article | 17 |
| multi article | 9 |
| cross jurisdiction | 8 |
| numeric or date-conditional | 6 |
| out of scope | 8 |
| partial | 3 |
| lease check | 9 |
| **total** | **60** |

By jurisdiction (items whose only jurisdiction is the one named, answerable): Florida 10, Spain 13, Colombia 11, Dubai 10; the 8 cross-jurisdiction items name two or three; the 8 out-of-scope items leave `jurisdictions` empty on purpose, so "ten Florida items" counts the same whichever way you count them. `source_language` is `es` when any gold text is Spanish, `en` otherwise (28 English, 32 Spanish).

Thirteen items carry `as_of` or `signed_on`.

## Where each question came from

`source_note` says, item by item, which source was used and how it was read. In all, 17 items come from official guidance, 4 from public forum threads and 39 are synthetic; the synthetic ones are the comparisons, the out-of-scope questions, the lease checks and the topics no source reviewed poses. Every question is my own phrasing; none is copied. How the real sources were read:

- **The Florida Bar's consumer pamphlet** (floridabar.org blocks automated access): read in the Internet Archive's copy of 2025-12-24. Its topics seeded `fl-0001`, `0003`, `0004`, `0005`, `0007`, `0008`.
- **The Ministerio de Vivienda's FAQ** (mivau.gob.es, ten questions): read in full. It seeded `es-0001`, `0002`, `0006`.
- **Bogotá's Secretaría del Hábitat**: its FAQ page on housing leases (2013) and its didactic booklet (October 2020) were read in full. They seeded `co-0001`, `0002`, `0003`, `0004`, `0008`, `0009`.
- **The DLD's Tenancy Guide**: read in the fetched PDF. It seeded `du-0001` and `du-0007` (it reproduces the legislation rather than posing questions).
- **Forum threads**: two Expat.com Spain threads (`es-0004`, `es-0005`) and one Expat.com UAE thread (`du-0008`) were read. For `fl-0002`, only the *title* of a public Avvo question was readable (its page is behind a bot challenge), so the facts in that question are mine.
- Not read, so not claimed: Avvo and Expat Woman threads, the Florida Bar's own pages, Miami-Dade's Notice of Tenant Rights (its PDF returned 404).

## Where to look hardest

1. **Spain is mid-reform.** Real Decreto-ley 29/2026 (in force from 2026-10-08, with no validation by Congress recorded when the LAU was pinned) rewrote art. 18.1 (the IPC cap became the IRAV), art. 20 (agency fees can no longer be passed on "directly or indirectly"), art. 36.5 and art. 11 (the agreed compensation for leaving early is gone). Congress must debate and vote on it within 30 days of its promulgation, so it may be repealed again. Real Decreto-ley 28/2026 rewords art. 10 from 2026-11-15. So: no item rests on art. 10; the items on arts. 9, 17 and 36 rest on provisions whose substance is the same before and after (art. 36.5 gained sentences on rent-default insurance and temporary leases, which the answers do not rely on); and the items where the wording changed carry a date (`es-0008`, `es-0009`, `es-0010`, `xj-0005`) that points at the pre-decree text, which stays true whatever Congress decides. Re-check these when you verify. `es-0006` cites art. 5(e) of the LAU, whose wording the decree also changed ("the whole of a dwelling" became "the whole or part", with a 31-day cap); its answer describes the activity without the changed words.
2. **A stale official source.** The Florida Bar's pamphlet still says, in its landlord section, that a month-to-month tenancy ends on 15 days' notice; its tenant section says 30. The statute, s. 83.57(3), has said 30 days since ch. 2023-314, and `fl-0003` follows the statute.
3. **Dubai's rent-increase decree is only in the guide.** Decree No. (43) of 2013 is in the corpus only inside the DLD's 2020 Tenancy Guide, which names its articles by their law. `du-0007`, `du-0009` and the finding in `dubai-lease-01` cite it as article `Decree 43/2013 art. 1` of the guide's source (`dubai-dld-tenancy-guide`). The guide is dated 2020; check that the decree is still the rule. The chunker does not yet key articles this way (see the note to Lane A).
4. **Law No. (33) of 2008 restates eleven articles of Law No. (26) of 2007** under their old numbers (2, 3, 4, 9, 13, 14, 15, 25, 26, 29 and 36). Gold references for those cite the restated article, law `dubai-law-33-2008`; the superseded original stays in the index, which is deliberate: a system that retrieves it has found text no longer in force.
5. **Article numbers for the LPH are numeric** (`17` for "Artículo diecisiete"), as lawyers cite it. The pipeline does not parse the LPH's word ordinals yet.
6. **The leases' "lawful lookalikes" are interpretive.** For example, that a co-signer is not a real guarantee under Ley 820 art. 16, or that a stated annual IBI is a lawful pass-on under LAU art. 20.1. They come from the statute's wording, not from a second source.
7. **Partial items** (`fl-0008`, `co-0009`, `du-0008`) rely on a stated gap: the Miami-Dade ordinance, the year's price-index figure, and Dubai's holiday-home regime are not indexed. Confirm the gap is real.
8. **Struck-down or repealed text.** No gold item relies on a provision a court struck down or the legislature repealed (Ley 820 arts. 35, 36, 38, 39 and 40 are marked repealed by the Código General del Proceso; art. 12 has two struck-down paragraphs). Status questions belong in v1.

## Second sources to use when verifying

| Jurisdiction | A second source that covers most items |
| --- | --- |
| Florida | the Florida Bar pamphlet (see above); Online Sunshine's own page for each section |
| Spain | the MIVAU FAQ, and the BOE's own consolidated page for each article and date |
| Colombia | the Bogotá booklet and FAQ, and the Ministry of Foreign Affairs' HTTPS copy of the same compilation (`cancilleria.gov.co`, compared with the pinned text before pinning) |
| Dubai | the DLD Tenancy Guide, which reproduces both laws and the decree |
