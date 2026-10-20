# ADR-0005: Rerank offline only with bge-reranker-v2-m3, at 10 candidates; nothing reranks online

- Status: proposed
- Date: 2026-10-20

## Context

Configurations A3 to A6 rerank the hybrid retriever's candidates with a cross-encoder before generation; R1 was to swap in the Cohere Rerank API. The plan set a budget before any measurement: if the local reranker adds more than 1.5 s at p95, use bge-reranker-base in int8 or 10 candidates instead of 20.

What we measured on 2026-10-20, against MX3's TEI 1.9.4 CPU server serving BAAI/bge-reranker-v2-m3 in float32 (max input 4,096 tokens, auto-truncate on, 32 inputs per request), with `python -m plumbline.retrieval.rerank_bench`:

1. **20 candidates, 50 questions** (`evals/results/rerank/benchmark.json`): p50 33.4 s, p95 58.3 s, maximum 71.5 s per question. The candidates are real leaf chunks of the article-aware chunker, each question's 20 drawn from its own jurisdiction: Fla. Stat. ch. 83, the LAU and Ley 820 de 2003 read by the ingest HTML reader, and Dubai's Law No. 26 of 2007 from the Dubai Legislation Portal's page. In the reranker's tokens they run p50 95, p95 425, maximum 970. The requests file is not committed, as it holds Dubai's text; the results record its sha256.
2. **10 candidates, the same questions** (`evals/results/rerank/benchmark-10.json`): p50 16.1 s, p95 36.3 s, maximum 43.1 s: half the time of 20, as the cost per candidate predicts, and still 24 times the budget.
3. **Cost per candidate** (`evals/results/rerank/probe.json`). One short candidate (about 50 tokens with the question) took 0.48 to 0.52 s; 5 took 2.6 s; 20 took 10.0 s. Time is linear in tokens, with no gain from batching: about 110 GFLOP/s for a 568M-parameter model (2 × 0.568 × 10⁹ FLOP per token), which is what float32 matrix work on this CPU delivers. Contention from the other services on MX3 is not the main cost.

So the budget fits about three short candidates. The plan's fallbacks do not reach it on this hardware: halving the candidates halves the time, and bge-reranker-base has half the parameters, so 10 candidates on it would still take several seconds. The TEI image here serves float32 (its `/info` says so); int8 would mean a second serving stack, such as ONNX Runtime.

## Decision

1. **Offline only.** bge-reranker-v2-m3 reranks for the ablations (A3 to A6, and E1 if MX3 has room), with **10 candidates** (the configurations say 20 until the ablation run, A11, sets them, with Lane D's debug-route test): half the recording time of 20, and the median's 1.7 s a pair puts one configuration on the dev split (about 1,200 pairs) at some 35 minutes of MX3's CPU, once. Latency does not change a metric, the model reads both English and Spanish, and each (question, text) pair is recorded once (`cache/rerank/`, or the fetched cache for Dubai and Colombian text), so every later run replays free and configurations whose candidates overlap share their scores.
2. **Online, nothing reranks.** The answer pipeline serves the hybrid order (A2's behaviour) on every tier. No Cohere: configuration R1 is dropped (the human's decision of 2026-10-20), and `CohereReranker` stays in `retrieval/rerank.py` unused, so a later record can turn it on without new code.
3. **Abstention reads the search scores.** With no rerank score online, the abstention threshold (C4) is tuned on dev on the hybrid retriever's scores.
4. **No bge-reranker-base int8 server** unless A11 shows reranking matters by more than the noise (about 5 points); it would need a second serving stack and still miss the budget by our estimate.

## Consequences

- The answer pipeline's latency budget holds without a reranker; the evaluation still measures the one it would use if the hardware allowed.
- Online quality is A2's, not A3's. A11 reports the gap with a paired interval; if it is large, this record is replaced.
- The rerank ordering is one function shared by the retriever's metrics and the answer pipeline (Lane C's `reorder`), so offline numbers describe the order an answer would have seen.
- Recording runs are long: a configuration ties up MX3's CPU for over half an hour, so they run when the hub is idle.

## Alternatives considered

- **10 candidates with bge-reranker-v2-m3**: measured above; far over budget.
- **bge-reranker-base, float32 or int8**: about half the cost per token of v2-m3; still over budget at 10 candidates on this CPU, and int8 needs ONNX Runtime outside TEI.
- **An English-only cross-encoder** (MiniLM-class): fast, but half the corpus is Spanish and the questions are English, which is the case a multilingual model is for.
- **A GPU**: none of the four machines has one.
- **Cohere Rerank online (R1)**: no pay-as-you-go price we could confirm, and a spend the budget does not have; dropped.
- **No reranker anywhere**: gives up measuring A3 to A6, the comparison the ablation exists for.
