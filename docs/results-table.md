# The results table

The README will open with Table 1. This page designs it before the system exists, so the build aims at filling it: every cell names the results file it comes from, and nothing below is a result yet.

## Rules every cell follows

- **Source.** A committed `evals/results/<config>/<split>.json` (an `EvalRun`, stamped with the configuration's hash, the git SHA and the golden file's sha256). The report generator (A13) fills the cells from the per-item results, joined to the golden file that hash pins, and `make reproduce` rebuilds every cell from recordings.
- **Definitions.** Each metric is defined in its docstring in [`rag_eval/metrics.py`](../packages/rag-eval/src/rag_eval/metrics.py). Retrieval is scored on articles: a hit is a retrieved text whose `ArticleRef.key` is gold, whatever its paragraph or edition. Answer correctness is the calibrated judge's binary pass (C9), shown with the judge's TPR and TNR on 100 hand labels.
- **Intervals.** 95% everywhere. Proportions (answer correctness, abstention) get a Wilson score interval; means of per-item fractions (recall, nDCG, citation precision) get a percentile bootstrap over items, 10,000 resamples, seed 0. Cells read `71 (62–79)`: percent, then the interval.
- **Comparisons are paired.** Two systems answer the same items, so differences use exact McNemar on 0/1 outcomes and a paired bootstrap of the mean difference otherwise ([`rag_eval/stats.py`](../packages/rag-eval/src/rag_eval/stats.py)). A difference counts as an effect only when its interval excludes zero and it is at least 5 points; anything smaller is reported as noise.
- **Dev explores, test confirms.** Dev (120 items) is where ten configurations are compared and the default is chosen, with no correction for multiple comparisons. Test (60 items) is run once, in Phase 13, with the configurations frozen first, for the three systems of Table 1 only (`--final-test-run`, which the runner refuses to repeat).
- **Which items.** The question-answering rows score the 152 items that are not lease checks (about 101 on dev and 51 on test); the 28 lease-check items are scored by the lease checker against each synthetic lease's expected findings, in a table of their own. Out-of-scope items are few (about 17 on dev, 8 on test), so their intervals are wide and say so; partial-answer items (2 to 5) are reported as counts, never as rates.

## Table 1: Plumbline against the two baselines (the README's opening)

Naive RAG is A0 (fixed 800-token chunks, dense retrieval). Long context is LC (no retrieval; the whole relevant law in one call to the stronger model). Plumbline is the default configuration A12 chooses.

| Metric, 95% interval | Naive RAG, dev | Naive RAG, test | Long context, dev | Long context, test | Plumbline, dev | Plumbline, test |
| --- | --- | --- | --- | --- | --- | --- |
| Answer correct (judged) | | | | | | |
| Recall@5 (articles) | | | — | — | | |
| Citation precision | | | | | | |
| Abstains when out of scope | | | | | | |
| Abstains when answerable (lower is better) | | | | | | |
| Cost per 1,000 queries | | | | | | |
| p95 latency, end to end | | | | | | |

Under the table, one line of provenance: golden set version and sha256, each configuration's hash, the git SHA, the judge's model and its TPR and TNR, and the command that rebuilds the table. Cost comes from the traces' `cost_usd`; latency from the run's traces and a k6 run at one request per second.

## Table 2: the differences, paired

| Plumbline minus | Split | Answer correct | Recall@5 | Citation precision | Abstains when out of scope |
| --- | --- | --- | --- | --- | --- |
| Naive RAG | dev | | | | |
| Naive RAG | test | | | | |
| Long context | dev | | — | | |
| Long context | test | | — | | |

Cells read `+12 (+5 to +19)` in points, with the McNemar p-value beside the 0/1 metrics.

## Table 3: Plumbline by jurisdiction and source language, dev

| Slice | n | Answer correct | Recall@5 | Citation precision |
| --- | --- | --- | --- | --- |
| Dubai (English sources) | | | | |
| Florida (English sources) | | | | |
| Spain (Spanish sources, cross-lingual) | | | | |
| Colombia (Spanish sources, cross-lingual) | | | | |
| All English-source items | | | | |
| All Spanish-source items | | | | |

A cross-jurisdiction item counts under each jurisdiction it names. Test numbers per jurisdiction (about 13 items each) go to the evaluation report, not here.

## Table 4: contextual retrieval, replicated or not

Anthropic's [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) (19 September 2024) reports the retrieval failure rate, 1 − recall@20 over the top 20 chunks, on codebases, fiction, ArXiv and science papers with Gemini Text 004 embeddings. Plumbline repeats the comparison on statutes in a second language and reports the result either way.

| Step | Anthropic | Plumbline, English sources | Plumbline, Spanish sources |
| --- | --- | --- | --- |
| No context (baseline) | 5.7% | | |
| Contextual embeddings | 3.7% (−35%) | — | — |
| Contextual embeddings and BM25 | 2.9% (−49%) | | |
| Plus reranking | 1.9% (−67%) | | |

What the comparison needs, so A10 and A11 build it:

- Our header goes into `text_for_search`, which is both embedded and indexed, so we measure the combined step (their −49%), not the embeddings-only one.
- The baseline is A2 (hybrid, no headers). The contextual row needs A2 with LLM headers alone (`headers: llm`, a retrieval-only configuration), so the comparison isolates the LLM header from our deterministic one; A5 keeps both.
- With `rerank_candidates: 20`, our reranker reorders the same 20 candidates and cannot change recall@20, so the reranking row needs a configuration that reranks a larger pool down to 20.
- Our recall counts articles and theirs counts chunks: relative reductions compare; absolute rates do not. Each Plumbline cell carries a paired bootstrap interval on the difference from its baseline row.

## Not in the README

The full ablation matrix (A0 to A6, E1, R1 and LC: retrieval metrics on all ten, judged generation on A0, A2, A3, the best and LC), nDCG@10, MRR, faithfulness, per-stage latency and the failure taxonomy live in the evaluation report (A11 and A12), built from the same results files.
