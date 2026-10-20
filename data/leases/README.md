# Synthetic leases

Ten invented leases in English across the four jurisdictions, each with planted clauses that conflict with the statutes, and `expected_findings.json` listing every planted finding with the article it violates. They are the lease checker's test and the lease-check items of the golden set. Every name, address and amount in them is fictitious. CC BY 4.0. Lane B owns this folder.

## Format

Each lease is `<lease_id>.md`: a short header with its id, jurisdiction and signing date, the parties, then its clauses as `## Clause <n>. <title>` sections. `expected_findings.json` (`plumbline.corpus.leases.ExpectedFindings`) has one entry per lease:

- `signed_on`: the law that applies is the law in force on this date, which matters in Spain, where the LAU changed on 2026-10-08.
- `findings`: the clauses the checker must report, each with its number, the offending words quoted verbatim, the issue in one sentence, and the `ArticleRef` it violates, pinned to the manifest's edition.
- `lawful`: clauses that look suspect but are lawful, each with the article that allows it; the checker must not report them.

`make check` validates every lease against it: each lease has findings, each quote is in its clause, and each article is a law and edition in the manifest, of the lease's jurisdiction.

## The leases

| Lease | Signed | Planted findings | Lawful lookalikes |
| --- | --- | --- | --- |
| `fl-lease-01`, Miami apartment | 2026-08-15 | waiver of Part II rights (s. 83.47(1)(a)); landlord's liability excluded (s. 83.47(1)(b)); deposit returned in 60 days without notice (s. 83.49(3)(a)) | 30 days' notice to end a month-to-month tenancy (s. 83.57(3)) |
| `fl-lease-02`, Fort Lauderdale condominium | 2026-09-01 | approval fee of $150 per spouse; approval fee charged again on renewal; association deposit of two months' rent (all s. 718.112(2)(k)); entry for repairs without notice (s. 83.53(2)) | rent paid to the association when the owner is delinquent (s. 718.116(11)) |
| `fl-lease-03`, Orlando house | 2026-10-01 | termination on 24 hours' notice for late rent (s. 83.56(3)); lockout and utility shut-off (s. 83.67(1), (2)) | deposit in a separate non-interest-bearing account (s. 83.49(1)(a)) |
| `es-lease-01`, Madrid flat | 2026-02-01 | fianza of two months (art. 36.1); additional guarantee of three months (art. 36.5); three months' rent in advance (art. 17.2); agency fee charged to the tenant (art. 20.1) | property tax with its annual amount stated (art. 20.1) |
| `es-lease-02`, Valencia flat, company landlord | 2026-04-01 | three-year term with the extensions waived (art. 9.1); fianza updated every year (art. 36.2) | additional guarantee of two months (art. 36.5) |
| `es-lease-03`, Seville flat | 2026-03-10 | landlord takes the flat back at any time on 15 days' notice (art. 9.3); every repair put on the tenant (art. 21.1) | partial sublet only with written consent (art. 8.2) |
| `co-lease-01`, Bogotá apartment | 2026-06-01 | cash deposit of two months' rent (art. 16); rent up 10% every six months (art. 20) | a co-signer's personal guarantee (art. 16) |
| `co-lease-02`, Medellín apartment | 2026-07-15 | rent above 1% of the capped commercial value (art. 18); landlord ends an extension on 30 days' notice without compensation (art. 22.7) | the tenant's early termination with notice and compensation (art. 24.4); a CPI-capped yearly increase (art. 20) |
| `dubai-lease-01`, Dubai Marina apartment, a renewal | 2026-05-10 | rent raised 10% on renewal although it is only 4% below the Rent Index average (Decree No. (43) of 2013, art. 1(a), as the DLD's tenancy guide reproduces it); non-refundable deposit (Law No. (26) of 2007, art. 20) | no assignment or sublet without consent (Law No. (26) of 2007, art. 24) |
| `dubai-lease-02`, Jumeirah Village Circle townhouse | 2026-03-01 | landlord ends the lease at any time on 30 days' notice (Law No. 26 of 2007, art. 7); the lease ends on sale (Law No. 26 of 2007, art. 28) | the tenant pays government fees for the use of the property (Law No. 26 of 2007, art. 22) |

The flood disclosure (s. 83.512, Florida Statutes) is never planted: whether it applies depends on facts a lease does not show.

## Scanned pages

`scans/` holds four scanned-looking pages for the OCR path, made from two of the leases (`fl-lease-03`, in English, and `co-lease-01`, whose parties carry Spanish names and accents). Each lease is printed on US Letter pages, tilted by a fraction of a degree (between 0.6 and 1.3, in both directions), rasterized at 150 dpi in grayscale, and given scanner banding, specks and an edge shadow, so that no text layer survives:

- `<lease_id>.pdf`: every page of the lease as an image-only PDF, as a scanner makes it.
- `<lease_id>-p<n>.png`: page n as an image, and `<lease_id>-p<n>.txt`: the text printed on it, one printed line per line. A parser's output is compared with this text, ignoring line breaks.

`uv run python -m plumbline.corpus.scans` rebuilds them from the leases with a seeded generator, so a lease's edit shows up as a changed scan, and `make check` fails until the scans are rebuilt. The pages need only pypdfium2 and the standard library.

## The disclaimer

`disclaimer.txt` is the text every lease check shows beside its findings (`plumbline.corpus.leases.lease_disclaimer()`), as `plumbline.core.stream.DISCLAIMER` is shown beside every answer: information and not advice, what a check cannot know, and that no lawyer has reviewed it.
