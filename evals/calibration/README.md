# Judge calibration

The judge ([`judge.py`](../../apps/api/src/plumbline/judge/judge.py), Claude Haiku) gives every answer a pass or a fail on two criteria, faithfulness and correctness. Its verdicts count as evidence only once they agree with a person's: both TPR (of the answers the person passed, the share the judge passes) and TNR (of those the person failed, the share the judge fails) must be at least 0.80, aiming for 0.90, each on at least 20 labels, and each is reported with its 95% Wilson interval ([`calibration.py`](../../apps/api/src/plumbline/judge/calibration.py)).

## The sheet

`to_label.jsonl` holds about 100 answers to dev questions, one JSON object per line, about half of them likely to pass and half likely to fail. Each line has the `question`, the `answer`, its `citations`, the `sources` it was written from (each source's label, then its text) and the `reference_answer`. The judge's own verdicts are not in the file, or anywhere else: they are asked for again, from the recordings, when the labels are scored.

The sheet is built by `plumbline.judge.calibrate.build_sheet` once retrieval and the frozen dev split exist. Dubai's and Colombia's text is fetch-only, so a question the pipeline may answer from it is answered and judged with recordings in the git-ignored fetched cache, and its row goes to a second sheet there, `data/corpus/fetched/calibration/to_label.jsonl` (`labels.write_sheets`), never to this directory.

The halves are chosen by a first run of the judge itself, so rates computed straight from this sheet lean towards the judge: in a simulation, a judge whose true rates are 0.90 and 0.70 measured 0.68 and 0.91. Before a rate from human labels is published, each half is weighted by its share of all answers, or the halves are drawn by a signal that does not come from the judge.

## How to label

For each line, set two fields to `"pass"` or `"fail"`, and save the file as `labelled.jsonl` beside it.

**`faithfulness`**: is every statement of law in the answer supported by its sources?

- Pass if every statement of law is supported. A source may be paraphrased, translated or summarized.
- Fail if any statement extends a source, contradicts it, or adds something no source says, even if it is true elsewhere.
- Statements that are not about the law (a greeting, an invitation to read the article, the disclaimer) do not count. An answer that declines part of the question is faithful when what it does state is supported.

**`correctness`**: does the answer state the same rule as the reference answer, on what the question asks?

- Pass if it states the same obligation, right, period, amount, condition or exception that the reference relies on. Extra correct detail is fine, and wording, order and length do not matter.
- Fail if it leaves out a condition or exception the reference treats as essential, or contradicts the reference.
- If the reference says part of the question cannot be answered from the law, the answer must leave that part open too.

Judge from the sources, the reference and the statute only. Leave a label `null` when you cannot decide: that row is then left out of that criterion's rates. Use `notes` for anything doubtful.

## Scoring

```
uv run python -m plumbline.judge.calibrate score evals/calibration/labelled.jsonl data/corpus/fetched/calibration/labelled.jsonl
```

The rows from the fetched sheet are judged again from the fetched cache.

This prints one table row per criterion. While a rate is under the bar, the judge's prompt changes in `judge.py`, `PROMPT_VERSION` goes up, the new verdicts are recorded (`CACHE_MODE=record`), and the labels are scored again. Every iteration keeps its row below.

## Constructed labels

Before any person labels, the judge is measured on answers whose verdict is known because they were built to have it: `constructed.jsonl`, 100 rows from dev gold items, made by `python -m plumbline.judge.constructed build` ([`constructed.py`](../../apps/api/src/plumbline/judge/constructed.py)).

- **50 correct answers**: each item's reference answer, rewritten by Claude Haiku as a Plumbline answer with a `[n]` after each statement of law, its gold articles as the sources.
- **50 answers with one planted error each**, on 50 other items:

| Kind | Rows | Faithfulness | Correctness | How it is built |
| --- | ---: | --- | --- | --- |
| wrong_article | 9 | fail | pass | the correct answer, with another article of the same law given as its source |
| wrong_number | 9 | fail | fail | one period, date, percentage or amount changed |
| wrong_jurisdiction | 8 | fail | fail | the answer replaced by another place's rule, on a one-place item |
| unsupported_claim | 8 | fail | not labelled | one plausible rule added that no source states (Florida and Spain items) |
| invented_quote | 8 | fail | not labelled | a sentence of the cited Florida paragraph with its modal turned ("shall" to "shall not"), quoted as the law, made in code |
| answered_out_of_scope | 8 | fail | fail | an out-of-scope question answered from general knowledge |

Haiku declines to put invented words in a statute's mouth, so the invented quotes are made in code, and a row whose `change` says the writer declined is replaced from the next eligible item (2 of 102 were). Haiku never sees Dubai's or Colombian text, and the file names each row's sources by article, so it quotes no restricted text; the faithfulness verdicts on rows citing those sources are recorded in the git-ignored fetched cache.

Every row was checked before scoring: each planted error read against its `change` note; each substituted article read against the rule it is made to cite (none supports it; repealed one-line stubs are passed over); the 50 correct rows compared with their references for every number (the only differences were dates written out and law-name numbers in citations).

Score them with `python -m plumbline.judge.constructed score [--model M] [--write]`; `--write` updates `agreement.json`, the file `/evals` reads.

## Results

| Labels | Prompt | Judge | Criterion | TPR [95% CI] (hits/n) | TNR [95% CI] (hits/n) | Bar (0.80) | Lower bounds at 0.80 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| constructed | v1 | claude-haiku-5-5 | faithfulness | 0.90 [0.79, 0.96] (45/50) | 0.98 [0.90, 1.00] (49/50) | meets the bar | TNR only |
| constructed | v1 | claude-haiku-5-5 | correctness | 1.00 [0.94, 1.00] (59/59) | 0.96 [0.80, 0.99] (24/25) | meets the bar | both |
| constructed | v1 | gemini-3.5-flash-lite | faithfulness | 0.96 [0.87, 0.99] (48/50) | 0.88 [0.76, 0.94] (44/50) | meets the bar | TPR only |
| constructed | v1 | gemini-3.5-flash-lite | correctness | 1.00 [0.94, 1.00] (59/59) | 0.96 [0.80, 0.99] (24/25) | meets the bar | both |

The bar is met on point estimates, as the plan sets it; the last column says which 95% lower bounds clear 0.80 as well (faithfulness TPR's is 0.786). Recorded on 2026-10-20; the 200 verdicts cost US$0.068, and building the rows US$0.03. Prompt v1 met the bar on the first run, so it was not tuned: with 100 rows drawn from the dev set, tuning the prompt to these rows would fit it to them.

**Where the judge and the labels disagree** (7 verdicts; the labels were left as constructed, not changed after reading the judge):

- Five correct rows failed on faithfulness. In four, the judge is right by its own criterion: the reference answer itself says something its gold articles do not (es-0009 states Ley 12/2023's rule; co-0021 says other articles were repealed too; xj-0011 says what Dubai's law does not contain, which one article cannot show; es-0010 adds an "only"). The fifth (du-0010) is a fair reading either way: the answer drops a proviso from its conclusion that it states in its premise. So the faithfulness TPR is, if anything, understated; the four references go back to the golden set's owner.
- One wrong_number row passed on both criteria: the number changed was a gap computed from the question's figures (6% for 4%), not a number of the law, and the conclusion did not change. On faithfulness, which counts statements of law, the pass is defensible; on correctness it is a miss.

**A second judge from another family.** Since 2026-10-20 the API answers on Claude, the judge's own family, which risks a judge favouring answers like its own. Gemini 3.5 Flash-Lite, with the same prompt v1 and through the Batch API (`score --model gemini-3.5-flash-lite`, US$0.075), meets the bar on the same rows, more lenient on faithfulness than Haiku (TNR 0.88 against 0.98) and as strict on correctness. On these 100 rows the two judges agree on 92 faithfulness verdicts (0.92 [0.85, 0.96]) and 98 correctness verdicts (0.98 [0.93, 0.99]). Their agreement on a sample of each judged configuration's real answers is the check on family bias; it is reported beside the judged scores.

No person has labelled real answers yet. When someone does, their rates go in this table beside these, and `agreement.json` gains a set with `"labels": "human"`.
