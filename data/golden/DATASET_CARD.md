# Plumbline tenancy-law golden set

A benchmark for question answering over residential tenancy law in four places: Dubai, Spain, Colombia and Florida. Each item is an English question, the statute articles that answer it, pinned to an edition of the law, and a reference answer written from the article text. Some items must be answered with an abstention, some only in part, some depend on the day a lease was signed, and some ask whether a clause of a synthetic lease is lawful. It is the set behind the results published for [Plumbline](https://github.com/alined-labs/plumbline), and it is meant to be reused: the corpus fetch script, the manifest that pins every edition by hash, and the scoring code are in the same repository.

It concerns legal information, not legal advice. Nothing in it should be read as advice about a real tenancy.

## Intended use

- Scoring a retrieval-augmented system on finding the right article, citing it faithfully, abstaining when the corpus cannot answer, answering in part when it can only partly, and respecting the date a rule applies.
- Cross-lingual retrieval: every question is English, while the Spanish and Colombian statutes are Spanish (about half the items have a Spanish gold text).
- Checking a lease clause against the law in force on the day the lease was signed.
- Comparing configurations of one system on `dev`, and reporting a final number on `test`.

Not intended for: training a model to give legal advice, deciding a real dispute, or estimating how a system would do on other places, other branches of law, or questions in another language.

## What is in an item

One JSON object per line (`rag_eval.schema.GoldenItem`; `rag-eval validate FILE` checks a file against it).

| Field | Meaning |
| --- | --- |
| `id` | Stable id: place (`fl`, `es`, `co`, `du`), `xj` for comparisons, `oos` for out of scope, then a number |
| `question` | The question, always in English |
| `source_language` | `es` when any gold text is Spanish, otherwise `en` |
| `jurisdictions` | The places the question is about; empty for an out-of-scope question |
| `category` | One of the seven below |
| `difficulty` | `easy`, `medium` or `hard`, the author's judgement |
| `gold_refs` | The articles that answer it: `jurisdiction`, `law` (the corpus id), `article`, an optional `paragraph` (for display only), and the `edition` the text was read in |
| `reference_answer` | The answer, written from the article text; absent for an out-of-scope question |
| `expected_abstain` | True when the right behaviour is to decline: the out-of-scope items |
| `partial` | True when only part of the question can be answered from the corpus |
| `as_of` | The date the answer must hold on |
| `signed_on` | The signing date of a lease, when the rule that applies depends on it |
| `lease_id` | The synthetic lease a lease-check item reads |
| `source_type`, `source_note` | `official_faq`, `forum` or `synthetic`, and where the question came from, in the author's words |
| `split` | `dev` or `test` |
| `verification` | How a human checked the item against the official text: the quoted passage, a second source, the date and who |
| `added_in` | The version that added the item |

Scoring matches an article by `jurisdiction:law:article`, so a paragraph or an edition does not change a match.

```python
import json

with open("golden_v1.jsonl", encoding="utf-8") as file:
    items = [json.loads(line) for line in file]
test = [item for item in items if item["split"] == "test"]
```

## Categories

- **single_article**: answered from one article.
- **multi_article**: needs two or more articles of one place.
- **cross_jurisdiction**: compares two or more places; the gold references come from each.
- **numeric_date**: needs an amount or a date worked out from the article text (code does that in the system under test, never the model), such as a rent ceiling, a notice deadline or the date a restriction ends.
- **out_of_scope**: the corpus cannot answer it: another place, another branch of law, a prediction, or a request that is not a question of law. The right behaviour is to abstain.
- **partial**: the corpus answers one part and not another, for example a rule of state law whose local ordinance is not indexed. The right behaviour is to answer the part and say what is missing.
- **lease_check**: asks whether a stated clause of one of the synthetic leases is lawful. The question carries the lease's signing date, and the gold references are the articles the lease's planted violations or lawful look-alikes depend on.

## Splits

Every item has a `split`: `dev` or `test`, in a ratio of two to one. It is assigned once, when a version is frozen, by `plumbline.corpus.split` in the repository: seeded, stratified by category, then place, then language, and decided by a hash of the seed and the item's id, so it does not depend on line order or machine. Use `dev` to build and tune and `test` to report. Items about the same lease or the same article can fall on both sides, so tuning on `dev` with knowledge of a lease or an article leaks some of `test`.

## How the items were made

- Questions are in the author's words. Real questions from official FAQs (the Florida Bar's consumer pamphlet, Spain's Ministerio de Vivienda, Bogotá's Secretaría del Hábitat, the Dubai Land Department) and public forum threads seeded some; none is copied. Where real questions leave a gap, a language model drafted a candidate, marked `synthetic`; see [AI_USAGE.md](../../AI_USAGE.md). `source_note` records the source and what was read of it.
- Reference answers are written from the pinned article text. Amounts and dates in them were worked out and checked with code.
- Every gold reference is checked mechanically against the pinned source file (the article exists, in that edition, in that place's law), and every lease-check item against the expected findings of its lease. A human then verifies each item against the official text and a second source, and records it in `verification`.
- Spanish articles are read as they stood on an item's `signed_on` or `as_of` date, using the BOE's version history, so several items test point-in-time law.
- The ten synthetic leases (three each for Florida and Spain, two each for Colombia and Dubai) plant clauses that conflict with the pinned statutes and include lawful look-alikes the checker must leave alone. Their names, addresses and amounts are invented.

## Sources and licences

The dataset contains no statutes. An item names a law, an edition and an article; `corpus_manifest.json` in the published folder gives the URL, the dates and the sha256 of every edition, so the same text can be fetched and checked. The repository's `DATA_LICENSES.md` records each publisher's terms; the position, in short:

| Law | Publisher | Terms |
| --- | --- | --- |
| Florida Statutes 2026, ch. 83 part II and ss. 718.110, 718.112, 718.116 | The Florida Legislature | Public domain (government edicts doctrine) |
| Ley 29/1994 (arrendamientos urbanos) and Ley 49/1960 (propiedad horizontal), consolidated | Agencia Estatal Boletín Oficial del Estado | BOE conditions of reuse: cite the source and the update date, do not distort, label consolidated text as informative. Fuente de los datos: Agencia Estatal Boletín Oficial del Estado |
| Law No. (26) of 2007 and Law No. (33) of 2008 (English translations); the Dubai Land Department's Tenancy Guide, which carries Decree No. (43) of 2013 | Dubai Legislation Portal; Dubai Land Department | Personal and research use only, no redistribution: not included, and fetched on the user's machine |
| Ley 820 de 2003 and Ley 675 de 2001 | Secretaría General del Senado (compilation by Avance Jurídico) | The law text is free to reproduce under Ley 23 de 1982, art. 41; the compilation's notes are protected and are not included |

Consequently `verification.quoted_text`, the passage a reviewer copied from the official text, is published only for items whose gold references are all in sources this repository redistributes; for the others it is replaced by a statement that it is withheld. The Dubai reference answers restate the provisions and cite the article; they are not a substitute for the Dubai Legislation Portal's text, whose Arabic original prevails over its English translation.

**The dataset's own licence is CC BY 4.0** for the questions, reference answers, verification records, the synthetic leases and their expected findings. Cite it as shown at the end.

## Limitations

- **Small.** The test split is small, so a difference between two systems needs an interval, not a point; the smallest categories (partial answers above all) hold a handful of items.
- **One author and one reviewer.** There is no inter-annotator agreement. Difficulty is a judgement. Several reference answers apply a rule to an assumed fact, and the lawful look-alikes in the leases are the author's reading of the statute, not a second source's.
- **Mostly synthetic.** Most items are synthetic, including all comparisons, lease checks and out-of-scope questions; `source_type` says which.
- **Law moves.** The editions are those of October 2026. Spain's Ley de Arrendamientos Urbanos was amended by decree-laws that month, one of which Congress had not yet validated when the text was pinned; items about the changed articles carry dates before the change, and may need revisiting. The `added_in` and edition fields let a later version say what changed.
- **Coverage.** Only the pinned laws: no case law, no regional or local law (Spain's autonomous communities, Florida's counties and cities), no court procedure, tax, immigration, labour or criminal law, no Colombian Civil Code, and not Dubai's Law No. (4) of 2026 or the UAE Civil Transactions Law, which the corpus does not have yet. Arabic text is not used; the Dubai English translations are not authoritative.
- **Relative to the corpus.** "Out of scope" and "partial" are defined against this corpus. A question that is out of scope here may be answerable with a wider one.
- **English questions only.** Results do not carry over to questions in Spanish.
- **Contamination.** The set is public. A system trained or tuned on it will look better than it is; say which split a number comes from.

## Statistics

<!-- statistics -->

## Changelog

Each version's changes are in `CHANGELOG.md`, published with this card.

## Citation

```bibtex
@misc{plumbline_golden_set,
  title        = {Plumbline tenancy-law golden set},
  year         = {2026},
  howpublished = {\url{https://github.com/alined-labs/plumbline}},
  note         = {CC BY 4.0}
}
```
