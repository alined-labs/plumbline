# ADR-0009: A binary judge, validated on constructed labels before any person labels

- Status: proposed
- Date: 2026-10-20

## Context

Plumbline reports faithfulness and correctness for every judged configuration. Both come from a model reading each answer ([`judge.py`](../../apps/api/src/plumbline/judge/judge.py)), and a model's verdict is evidence only to the extent it agrees with a careful person. The plan asked for about 100 answers labelled by the human; on 2026-10-20 there are none, and the launch is on 2026-10-22.

What we had and measured on 2026-10-20:

1. The judge gives pass or fail per criterion, reasoning first. A binary verdict can be scored against labels as two rates, TPR and TNR; a five-point score cannot be scored that way without a further threshold.
2. Dev gold items carry reference answers checked against the pinned statute, and Gemini's cross-check (C11) disputed 1 of 180 while catching 12 of 12 planted number errors.
3. Claude Haiku 5.5 costs US$0.10 in and US$0.50 out per million tokens; 200 verdicts cost US$0.068.

## Decision

1. The judge's verdicts are binary, per criterion, and its agreement is reported as TPR and TNR with 95% Wilson intervals, never as accuracy, which a judge that passes everything can make look good.
2. The bar is both point estimates at 0.80 or more, aiming for 0.90. A rate with no labels behind it fails.
3. Until a person labels real answers, the judge is validated on 100 constructed rows from dev gold items: 50 correct answers (the reference, rewritten as a Plumbline answer) and 50 with one planted error each, spread over six kinds (wrong article, wrong number, wrong jurisdiction, unsupported claim, invented quote, an out-of-scope question answered). Each kind fixes the label on the criteria it decides and leaves the other unlabelled.
4. Labels are fixed by construction and checked before scoring, never changed after reading the judge's verdicts; where the judge and a label disagree, the README says who is right and why.
5. Human labels, when they exist, are reported beside the constructed ones (`agreement.json` holds one set per label source), not instead of them.
6. Claude Haiku 5.5 is the judge, chosen as a different family from the Gemini models that wrote Plumbline's answers. Prompt v1 met the bar (faithfulness TPR 0.90 [0.79, 0.96], TNR 0.98 [0.90, 1.00]; correctness TPR 1.00 [0.94, 1.00], TNR 0.96 [0.80, 0.99]), so neither a second prompt nor Claude Sonnet was needed.
7. Since the human moved the served answers to Claude Sonnet on 2026-10-20, the judge shares the generator's family. A second judge from another family, Gemini 3.5 Flash-Lite with the same prompt, is validated on the same rows (it meets the bar: faithfulness TPR 0.96, TNR 0.88; correctness TPR 1.00, TNR 0.96) and re-judges a sample of each judged configuration's answers; the two judges' agreement is reported beside the judged scores. On the constructed rows they agree on 92 and 98 of 100 verdicts.

## Consequences

- Judged numbers can be published on launch day with a measured judge behind them, and the page says the labels were constructed.
- Constructed errors are cleaner than real ones: a planted wrong number is easier to see than a subtle misreading, so these rates likely overstate the judge on real answers' failures. Human labels on real answers are what would show that, and the sheet for them is ready (`labels.py`, `calibrate.py`).
- Four of the five correct rows the judge failed rest on reference answers that say more than their gold articles. The constructed TPR is therefore a floor in that respect, and those references go back to the golden set's owner.
- The rows come from the dev split, so the judge is never validated on a test item; Lane B keeps dev assignments fixed through the freeze.

## Alternatives considered

- Waiting for human labels: nothing judged could be published at launch.
- Scoring the judge on accuracy alone: hides a judge that leans to pass.
- Graded (1 to 5) verdicts: finer, but not scorable as TPR and TNR, and harder to label consistently.
- Letting the writer model plant every error: Haiku declines to put invented words in a statute's mouth, so invented quotes are made in code, and declined rows are replaced rather than kept under labels they do not earn.
- A Gemini judge for every verdict: the other family now, but it spends the scarce Gemini budget on hundreds of calls per run; a sample measures the family bias for a fraction of it.
