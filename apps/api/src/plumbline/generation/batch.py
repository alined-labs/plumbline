"""Gemini's Batch API, through the cache: many requests as one job, at half the price.

The Batch API reads an inline request differently from a plain call: it ignores
response_json_schema (measured on 2026-10-20: the replies came back in keys of the model's
own choosing) and honours response_schema, OpenAPI's subset of JSON Schema. So a batch
sends `batch_payload`, the plain payload with its schema moved into response_schema, and
records under that payload: a batch recording replays for the same batch, never for a
plain call, whose request differs. Only the misses go into the job. A recording carries
what the batch cost (half the standard price, as Google bills it), so the spend tally sums
what was paid.

A job usually finishes in minutes and may take up to a day. The runner polls until it
ends, records every answer that came back, then raises BatchIncomplete if any request
failed: running the same requests again submits only those.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final

from google.genai import types as genai_types

from plumbline.cache import Cached, CacheMiss, Fresh, Json, ResponseCache
from plumbline.core.types import CacheMode
from plumbline.generation.llm import (
    GeminiClient,
    LLMRequest,
    LLMResult,
    _gemini_stop,
    _gemini_usage,
    _result,
    price_for,
)

BATCH_DISCOUNT: Final = 0.5  # ai.google.dev/gemini-api/docs/batch-mode, checked 2026-10-20
_ENDED: Final = frozenset(
    {
        genai_types.JobState.JOB_STATE_SUCCEEDED,
        genai_types.JobState.JOB_STATE_PARTIALLY_SUCCEEDED,
        genai_types.JobState.JOB_STATE_FAILED,
        genai_types.JobState.JOB_STATE_CANCELLED,
        genai_types.JobState.JOB_STATE_EXPIRED,
    }
)


class BatchIncomplete(RuntimeError):
    """Some requests got no answer; the answers that came back are recorded."""

    def __init__(self, failed: Sequence[int], detail: str) -> None:
        super().__init__(f"{len(failed)} batch requests failed: {detail}")
        self.failed = list(failed)


@dataclass(frozen=True)
class BatchRun:
    results: list[LLMResult]
    submitted: int  # requests sent in this run; the rest replayed
    job: str | None  # the job's name, when one was submitted


class GeminiBatch:
    def __init__(
        self,
        client: GeminiClient,
        *,
        poll_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = lambda line: print(line, file=sys.stderr),
    ) -> None:
        self.client = client
        self.poll_s = poll_s
        self._sleep = sleep
        self._log = log

    @property
    def cache(self) -> ResponseCache:
        return self.client.cache

    def run(self, requests: Sequence[LLMRequest], name: str = "plumbline") -> BatchRun:
        """Every request's result, in order; the misses answered by one batch job."""
        if len({r.model for r in requests}) > 1:
            raise ValueError("a batch job runs one model")
        keyed = [self.client.cache_request(batch_payload(self.client.payload(r))) for r in requests]
        hits = [self.cache.get("llm", k) for k in keyed]
        missing = [i for i, hit in enumerate(hits) if hit is None]
        if missing and self.cache.mode is CacheMode.REPLAY:
            raise CacheMiss(
                f"{len(missing)} llm recordings missing for {requests[0].model}; "
                "record them with CACHE_MODE=record"
            )
        job = self._submit(requests, keyed, missing, hits, name) if missing else None
        failed = [i for i in missing if hits[i] is None]
        if failed:
            raise BatchIncomplete(failed, f"job {job}")
        return BatchRun([_result(h) for h in hits if h is not None], len(missing), job)

    def _submit(
        self,
        requests: Sequence[LLMRequest],
        keyed: Sequence[dict[str, Json]],
        missing: Sequence[int],
        hits: list[Cached | None],
        name: str,
    ) -> str:
        sdk = self.client._client()
        model = requests[0].model
        src: list[genai_types.InlinedRequestDict] = [
            {
                "contents": keyed[i]["contents"],
                "config": keyed[i]["config"],
                "metadata": {"index": str(i)},
            }
            for i in missing
        ]
        start = time.perf_counter()
        job = sdk.batches.create(model=model, src=src, config={"display_name": name})
        job_name = str(job.name)
        self._log(f"batch {job_name}: {len(src)} requests to {model}")
        while job.state not in _ENDED:
            self._sleep(self.poll_s)
            job = sdk.batches.get(name=job_name)
            self._log(f"batch {job_name}: {job.state}")
        responses = list(job.dest.inlined_responses or []) if job.dest else []
        latency = round((time.perf_counter() - start) * 1000) // max(len(src), 1)
        price = price_for(model, datetime.now(UTC).date())
        for position, answer in enumerate(responses):
            # Responses come back in the order sent; the metadata says so where it is echoed.
            index = int((answer.metadata or {}).get("index", missing[position]))
            if answer.error is not None or answer.response is None:
                self._log(f"batch {job_name}: request {index} failed: {answer.error}")
                continue
            usage = _gemini_usage(answer.response)
            fresh = Fresh(
                response={"text": answer.response.text or "", "usage": asdict(usage)},
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=price.cost(usage) * BATCH_DISCOUNT,
                stop_reason=_gemini_stop(answer.response),
            )
            hits[index] = self.cache.put("llm", keyed[index], fresh, latency_ms=latency)
        return job_name


def batch_payload(payload: dict[str, Json]) -> dict[str, Json]:
    """A plain call's payload as the Batch API must receive it."""
    config = dict(payload["config"])
    if "response_json_schema" in config:
        config["response_schema"] = openapi_schema(config.pop("response_json_schema"))
    return {**payload, "config": config}


def openapi_schema(schema: Json) -> Json:
    """A portable JSON Schema (generation.schema) as the OpenAPI subset of response_schema,
    the only structured-output field the Batch API honours for inline requests: a
    ["string", "null"] type becomes nullable, additionalProperties goes, and the order of
    the properties is kept explicitly (a reason written before its verdict)."""
    if isinstance(schema, list):
        return [openapi_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Json] = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if key == "type" and isinstance(value, list):
            kinds = [kind for kind in value if kind != "null"]
            out["type"] = kinds[0]
            if len(kinds) < len(value):
                out["nullable"] = True
        elif key == "properties":
            out["properties"] = {name: openapi_schema(sub) for name, sub in value.items()}
            out["propertyOrdering"] = list(value)
        else:
            out[key] = openapi_schema(value)
    return out
