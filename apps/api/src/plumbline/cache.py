"""The record/replay cache every model call goes through: generation, judging, embedding,
reranking and parsing. Frozen: a change needs a brain block.

A request is any JSON-serialisable mapping that fully determines the response (model,
prompt or inputs, parameters; never a key or a header). Its key is the sha256 of the kind
plus the request's canonical JSON, and its recording is one file:

    cache/<kind>/<key[:2]>/<key>.json

Modes (CacheMode): replay reads only and raises CacheMiss on a miss, which is how tests,
the hub and CI run with no keys and no network; record calls the model on a miss and
writes the recording; live calls on a miss and writes nothing, so production traffic
never lands in the repository. Recordings are committed, which is what lets every number
in the README rebuild at zero API cost.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal

from plumbline.core.types import CacheMode

Kind = Literal["llm", "embed", "rerank", "parse"]
KINDS: tuple[Kind, ...] = ("llm", "embed", "rerank", "parse")
Json = Any  # a JSON-serialisable value


class CacheMiss(LookupError):
    """Replay mode found no recording for this request."""


def canonical_json(value: Json) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def cache_key(kind: Kind, request: Mapping[str, Json]) -> str:
    return hashlib.sha256(f"{kind}\n{canonical_json(request)}".encode()).hexdigest()


def encode_vector(vector: Sequence[float]) -> str:
    """A float32 little-endian vector as base64: compact recordings for embeddings."""
    return base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode("ascii")


def decode_vector(data: str) -> list[float]:
    raw = base64.b64decode(data)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


@dataclass(frozen=True)
class Fresh:
    """What a real call hands back to the cache."""

    response: Json
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None


@dataclass(frozen=True)
class Cached:
    key: str
    kind: Kind
    model: str
    response: Json
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int  # of the original call
    stop_reason: str | None
    cached: bool  # True when this came from a recording


# How many results a process keeps in memory, the most recently used. An embedding held in
# memory is about 33 KB, so 2,000 entries is about 70 MB, well inside the production API's
# 2 GB (Lane P, 2026-10-20). An evicted result is read from disk again in record and replay
# mode; in live mode nothing is on disk, so a repeat of an evicted request calls the model.
MEMORY_ENTRIES: Final = 2000


class ResponseCache:
    def __init__(
        self, mode: CacheMode, directory: Path, *, memory_entries: int = MEMORY_ENTRIES
    ) -> None:
        self.mode = CacheMode(mode)
        self.directory = directory
        self._memory: OrderedDict[str, Cached] = OrderedDict()
        self._memory_entries = memory_entries
        self._lock = threading.Lock()

    def path(self, kind: Kind, key: str) -> Path:
        return self.directory / kind / key[:2] / f"{key}.json"

    def get(self, kind: Kind, request: Mapping[str, Json]) -> Cached | None:
        """The recording for this request, or None."""
        return self._get(kind, cache_key(kind, request))

    def put(
        self, kind: Kind, request: Mapping[str, Json], fresh: Fresh, *, latency_ms: int
    ) -> Cached:
        """Store a response made outside `call` (a streamed generation, say). Replay mode
        refuses: nothing records while replaying."""
        if self.mode is CacheMode.REPLAY:
            raise CacheMiss("replay mode never records")
        key = cache_key(kind, request)
        result = self._result(kind, key, request, fresh, latency_ms)
        if self.mode is CacheMode.RECORD:
            self._write(kind, key, request, result)
        self._remember(result)
        return result

    def call(self, kind: Kind, request: Mapping[str, Json], fn: Callable[[], Fresh]) -> Cached:
        """The recording for this request or, outside replay mode, a real call."""
        key = cache_key(kind, request)
        hit = self._get(kind, key)
        if hit is not None:
            return hit
        self._refuse_in_replay(kind, key, request)
        start = time.perf_counter()
        fresh = fn()
        return self.put(kind, request, fresh, latency_ms=_since(start))

    async def acall(
        self, kind: Kind, request: Mapping[str, Json], fn: Callable[[], Awaitable[Fresh]]
    ) -> Cached:
        """`call` for async model clients."""
        key = cache_key(kind, request)
        hit = self._get(kind, key)
        if hit is not None:
            return hit
        self._refuse_in_replay(kind, key, request)
        start = time.perf_counter()
        fresh = await fn()
        return self.put(kind, request, fresh, latency_ms=_since(start))

    def call_batch(
        self,
        kind: Kind,
        requests: Sequence[Mapping[str, Json]],
        fn: Callable[[Sequence[Mapping[str, Json]]], Sequence[Fresh]],
    ) -> list[Cached]:
        """One recording per request; the misses go to the model in a single batch call
        (embedding and reranking endpoints take batches), in their original order."""
        results: list[Cached | None] = [self.get(kind, r) for r in requests]
        missing = [i for i, hit in enumerate(results) if hit is None]
        if missing:
            for i in missing:
                self._refuse_in_replay(kind, cache_key(kind, requests[i]), requests[i])
            start = time.perf_counter()
            fresh = fn([requests[i] for i in missing])
            if len(fresh) != len(missing):
                raise ValueError(f"batch call returned {len(fresh)} results for {len(missing)}")
            per_item = _since(start) // len(missing)
            for i, f in zip(missing, fresh, strict=True):
                results[i] = self.put(kind, requests[i], f, latency_ms=per_item)
        return [r for r in results if r is not None]

    def _get(self, kind: Kind, key: str) -> Cached | None:
        with self._lock:
            hit = self._memory.get(key)
            if hit is not None:
                self._memory.move_to_end(key)  # the most recently used is evicted last
        if hit is not None:
            return hit
        try:
            raw = json.loads(self.path(kind, key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        hit = Cached(
            key=key,
            kind=kind,
            model=str(raw.get("model", "")),
            response=raw["response"],
            input_tokens=int(raw.get("input_tokens", 0)),
            output_tokens=int(raw.get("output_tokens", 0)),
            cost_usd=float(raw.get("cost_usd", 0.0)),
            latency_ms=int(raw.get("latency_ms", 0)),
            stop_reason=raw.get("stop_reason"),
            cached=True,
        )
        self._remember(hit)
        return hit

    def _refuse_in_replay(self, kind: Kind, key: str, request: Mapping[str, Json]) -> None:
        if self.mode is CacheMode.REPLAY:
            model = request.get("model", "?")
            raise CacheMiss(
                f"no {kind} recording for {model} (key {key[:12]}); record it with CACHE_MODE=record"
            )

    def _result(
        self, kind: Kind, key: str, request: Mapping[str, Json], fresh: Fresh, latency_ms: int
    ) -> Cached:
        return Cached(
            key=key,
            kind=kind,
            model=str(request.get("model", "")),
            response=fresh.response,
            input_tokens=fresh.input_tokens,
            output_tokens=fresh.output_tokens,
            cost_usd=fresh.cost_usd,
            latency_ms=latency_ms,
            stop_reason=fresh.stop_reason,
            cached=False,
        )

    def _remember(self, result: Cached) -> None:
        with self._lock:
            self._memory[result.key] = replace(result, cached=True)
            self._memory.move_to_end(result.key)
            while len(self._memory) > self._memory_entries:
                self._memory.popitem(last=False)

    def _write(self, kind: Kind, key: str, request: Mapping[str, Json], result: Cached) -> None:
        body = {
            "key": key,
            "kind": kind,
            "model": result.model,
            "request": request,
            "response": result.response,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "stop_reason": result.stop_reason,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path = self.path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)


def _since(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


_caches: dict[tuple[CacheMode, Path], ResponseCache] = {}
_caches_lock = threading.Lock()


def get_cache(mode: CacheMode | None = None, directory: Path | None = None) -> ResponseCache:
    """One cache per mode and directory; both default to the settings."""
    if mode is None or directory is None:
        from plumbline.settings import get_settings

        settings = get_settings()
        mode = settings.cache_mode if mode is None else mode
        directory = settings.cache_dir if directory is None else directory
    with _caches_lock:
        key = (CacheMode(mode), directory)
        if key not in _caches:
            _caches[key] = ResponseCache(key[0], directory)
        return _caches[key]
