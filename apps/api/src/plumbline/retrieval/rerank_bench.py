"""Time the local reranker on fixed requests.

    python -m plumbline.retrieval.rerank_bench REQUESTS [--out FILE] [--warmup N]

REQUESTS is JSON Lines, one {"query": ..., "texts": [...]} per line: the questions and the
candidates a retriever would hand the reranker. Every call reaches the server: the cache
is live and empty, so nothing is replayed and nothing recorded. The first calls are
dropped, as a fresh server pays for allocation on its first batches. The results file
holds the server's /info, each call's latency, p50 and p95, and the candidates' lengths in
the reranker's own tokens.

The plan's rule: a p95 above 1.5 s added per question means bge-reranker-base int8 or 10
candidates instead of 20.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode
from plumbline.retrieval.rerank import TeiReranker
from plumbline.settings import ROOT, get_settings
from rag_eval.schema import file_sha256
from rag_eval.stats import percentile

BUDGET_MS: Final = 1500.0
INFO_FIELDS: Final = (
    "model_id",
    "model_dtype",
    "version",
    "max_input_length",
    "max_batch_tokens",
    "max_client_batch_size",
    "auto_truncate",
)


def _summary(values: list[float]) -> dict[str, float | None]:
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "mean": round(statistics.fmean(values), 1),
        "max": max(values),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plumbline.retrieval.rerank_bench")
    parser.add_argument("requests", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "evals/results/rerank/benchmark.json")
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.requests.read_text(encoding="utf-8").splitlines()]
    settings = get_settings()
    url = settings.rerank_url.rstrip("/")
    with httpx.Client(timeout=120) as client, tempfile.TemporaryDirectory() as empty:
        info = client.get(f"{url}/info").json()
        reranker = TeiReranker(
            url, ResponseCache(CacheMode.LIVE, Path(empty)), settings.rerank_model, client
        )
        latencies: list[float] = []
        for n, row in enumerate(rows):
            start = time.perf_counter()
            reranker.scores(row["query"], row["texts"])
            if n >= args.warmup:
                latencies.append(round((time.perf_counter() - start) * 1000, 1))
        texts = [t for row in rows for t in row["texts"]]
        tokens = [
            len(ids)
            for start in range(0, len(texts), 32)
            for ids in client.post(
                f"{url}/tokenize", json={"inputs": texts[start : start + 32]}
            ).json()
        ]
    p95 = percentile(latencies, 95)
    result = {
        "benchmark": "rerank latency, one call per question",
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "server": {field: info.get(field) for field in INFO_FIELDS},
        "requests_file": args.requests.name,
        "requests_sha256": file_sha256(args.requests),
        "questions": len(rows),
        "warmup_dropped": args.warmup,
        "candidates_per_question": sorted({len(row["texts"]) for row in rows}),
        "candidate_tokens": _summary([float(t) for t in tokens]),
        "latency_ms": _summary(latencies),
        "budget_ms_p95": BUDGET_MS,
        "within_budget": p95 is not None and p95 <= BUDGET_MS,
        "latencies_ms": latencies,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: result[k] for k in ("server", "candidate_tokens", "latency_ms", "within_budget")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
