import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from plumbline.cache import (
    CacheMiss,
    Fresh,
    ResponseCache,
    cache_key,
    decode_vector,
    encode_vector,
)
from plumbline.core.types import CacheMode

REQUEST = {"model": "m-1", "prompt": "What is the deposit cap?", "temperature": 0}


def test_replay_miss_raises(tmp_path: Path) -> None:
    cache = ResponseCache(CacheMode.REPLAY, tmp_path)
    with pytest.raises(CacheMiss, match="CACHE_MODE=record"):
        cache.call("llm", REQUEST, lambda: Fresh(response="never"))


def test_record_writes_one_sharded_file_then_replay_hits(tmp_path: Path) -> None:
    calls = []

    def fn() -> Fresh:
        calls.append(1)
        return Fresh(
            response={"text": "two months"}, input_tokens=12, output_tokens=3, cost_usd=0.001
        )

    recorded = ResponseCache(CacheMode.RECORD, tmp_path).call("llm", REQUEST, fn)
    assert not recorded.cached
    key = cache_key("llm", REQUEST)
    path = tmp_path / "llm" / key[:2] / f"{key}.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["request"] == REQUEST
    assert body["response"] == {"text": "two months"}

    replayed = ResponseCache(CacheMode.REPLAY, tmp_path).call("llm", REQUEST, fn)
    assert replayed.cached
    assert replayed.response == {"text": "two months"}
    assert replayed.input_tokens == 12
    assert calls == [1]


def test_live_calls_but_never_writes(tmp_path: Path) -> None:
    cache = ResponseCache(CacheMode.LIVE, tmp_path)
    result = cache.call("llm", REQUEST, lambda: Fresh(response="ok"))
    assert result.response == "ok"
    assert not any(tmp_path.rglob("*.json"))
    assert cache.call("llm", REQUEST, lambda: Fresh(response="again")).cached


def test_key_ignores_mapping_order_but_not_kind() -> None:
    reordered = dict(reversed(list(REQUEST.items())))
    assert cache_key("llm", reordered) == cache_key("llm", REQUEST)
    assert cache_key("embed", REQUEST) != cache_key("llm", REQUEST)


def test_batch_sends_only_the_misses_in_order(tmp_path: Path) -> None:
    cache = ResponseCache(CacheMode.RECORD, tmp_path)
    requests: list[dict[str, Any]] = [{"model": "e", "text": t} for t in ("a", "b", "c")]
    cache.call("embed", requests[1], lambda: Fresh(response="B"))
    seen: list[str] = []

    def fn(batch: Sequence[Mapping[str, Any]]) -> list[Fresh]:
        seen.extend(str(r["text"]) for r in batch)
        return [Fresh(response=str(r["text"]).upper()) for r in batch]

    results = cache.call_batch("embed", requests, fn)
    assert [r.response for r in results] == ["A", "B", "C"]
    assert seen == ["a", "c"]


def test_put_refuses_in_replay(tmp_path: Path) -> None:
    with pytest.raises(CacheMiss):
        ResponseCache(CacheMode.REPLAY, tmp_path).put(
            "llm", REQUEST, Fresh(response=1), latency_ms=1
        )


def test_vectors_round_trip_as_float32() -> None:
    vector = [0.25, -1.5, 3.0, 0.1]
    decoded = decode_vector(encode_vector(vector))
    assert decoded[:3] == [0.25, -1.5, 3.0]
    assert decoded[3] == pytest.approx(0.1, rel=1e-6)


@pytest.mark.anyio
async def test_acall_records_and_replays(tmp_path: Path) -> None:
    async def fn() -> Fresh:
        return Fresh(response="async")

    assert (
        await ResponseCache(CacheMode.RECORD, tmp_path).acall("llm", REQUEST, fn)
    ).response == "async"
    assert (await ResponseCache(CacheMode.REPLAY, tmp_path).acall("llm", REQUEST, fn)).cached


def _ask(n: int) -> dict[str, Any]:
    return {"model": "m-1", "prompt": f"question {n}"}


def test_memory_keeps_only_the_most_recently_used(tmp_path: Path) -> None:
    calls: list[int] = []
    cache = ResponseCache(CacheMode.LIVE, tmp_path, memory_entries=2)

    def answer(n: int) -> Fresh:
        calls.append(n)
        return Fresh(response=f"answer {n}")

    for n in (1, 2):
        cache.call("llm", _ask(n), lambda n=n: answer(n))
    assert cache.call("llm", _ask(1), lambda: answer(99)).cached  # 1 is now the most recent
    cache.call("llm", _ask(3), lambda: answer(3))  # evicts 2, the least recently used
    assert cache.call("llm", _ask(1), lambda: answer(99)).cached
    again = cache.call("llm", _ask(2), lambda: answer(2))
    assert not again.cached  # live mode keeps nothing on disk: an evicted request calls again
    assert calls == [1, 2, 3, 2]


def test_an_evicted_recording_is_read_from_disk_again(tmp_path: Path) -> None:
    recorder = ResponseCache(CacheMode.RECORD, tmp_path, memory_entries=1)
    for n in (1, 2):
        recorder.call("llm", _ask(n), lambda n=n: Fresh(response=f"answer {n}"))
    replay = ResponseCache(CacheMode.REPLAY, tmp_path, memory_entries=1)
    for n in (1, 2, 1):  # each read evicts the other; both still replay from disk
        assert replay.call("llm", _ask(n), lambda: Fresh(response="never")).response == (
            f"answer {n}"
        )
