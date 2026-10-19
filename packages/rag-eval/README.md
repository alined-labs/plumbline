# rag-eval

A benchmark harness for retrieval-augmented generation over tenancy law: the golden-set schema, retrieval and citation metrics, paired statistics and reports. It is developed inside Plumbline and will be published on PyPI, so anyone can score their own retriever against the benchmark.

```python
from rag_eval.schema import load_golden
from rag_eval.stats import paired_bootstrap, mcnemar_exact

items = load_golden(Path("data/golden/golden_v1.jsonl"))
```

```bash
rag-eval validate data/golden/golden_v1.jsonl
```

- `rag_eval.schema`: `GoldenItem`, `ArticleRef`, `Verification`, `RetrievedRef`, `EvalResult`, `EvalRun`, and the `Retriever` protocol a system implements to be scored.
- `rag_eval.stats`: Clopper-Pearson and Wilson intervals, the paired bootstrap, the exact McNemar test, nearest-rank percentiles. Standard library only.

Licence: Apache 2.0.
