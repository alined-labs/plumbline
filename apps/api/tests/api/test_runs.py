"""Runs: events a reader can wait for and resume, the end every run comes to, who may see
a run, how many may go at once and how long one is kept."""

from __future__ import annotations

import asyncio
import logging

import pytest
from pydantic import BaseModel

from plumbline.api.runs import Busy, Run, Runs

pytestmark = pytest.mark.anyio


class Note(BaseModel):
    text: str = ""


def _failed(code: str, message: str) -> tuple[str, BaseModel]:
    return "failed", Note(text=f"{code}: {message}")


def _text(run: Run) -> str:
    return " ".join(f"{event.name}:{getattr(event.data, 'text', '')}" for event in run.events)


async def _ended(run: Run) -> None:
    while not run.ended:
        await asyncio.wait_for(run.wait(len(run.events)), 1)


async def _idle(run: Run) -> None:
    await asyncio.sleep(60)


async def test_events_are_numbered_from_one_and_a_waiting_reader_is_woken() -> None:
    release = asyncio.Event()

    async def work(run: Run) -> None:
        run.emit("stage", Note(text="a"))
        await release.wait()
        run.emit("stage", Note(text="b"))
        run.end("done", Note())

    run = Runs(_failed).start("v1", work)
    await asyncio.wait_for(run.wait(0), 1)
    assert [(e.id, e.name) for e in run.events] == [(1, "stage")]
    reader = asyncio.create_task(run.wait(1))
    await asyncio.sleep(0.01)
    assert not reader.done()  # nothing after event 1 yet
    release.set()
    await asyncio.wait_for(reader, 1)
    await _ended(run)
    assert [(e.id, e.name) for e in run.events] == [(1, "stage"), (2, "stage"), (3, "done")]


async def test_a_reader_stops_waiting_cleanly_when_it_gives_up() -> None:
    run = Run(id="r", owner="v1")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(run.wait(0), 0.01)
    assert run._waiters == set()  # a reader that left is not woken for nothing
    assert run.events == []
    assert not run.ended


async def test_nothing_follows_the_last_event() -> None:
    run = Run(id="r", owner="v1")
    run.end("done", Note(text="first"))
    run.emit("stage", Note(text="late"))
    run.end("failed", Note(text="late"))
    assert _text(run) == "done:first"
    assert run.ended


async def test_work_that_returns_without_an_end_is_a_failure() -> None:
    async def work(run: Run) -> None:
        run.emit("stage", Note())

    run = Runs(_failed).start("v1", work)
    await _ended(run)
    assert run.events[-1].name == "failed"
    assert "internal" in _text(run)


async def test_an_error_ends_the_run_and_its_message_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def work(run: Run) -> None:
        raise RuntimeError("clause 7: Jane Doe pays 900 EUR a month")

    with caplog.at_level(logging.DEBUG):
        run = Runs(_failed).start("v1", work)
        await _ended(run)
    assert "internal" in _text(run)
    assert "RuntimeError" in caplog.text  # the type is enough to find it
    assert "Jane Doe" not in caplog.text
    assert "Jane Doe" not in _text(run)


async def test_a_run_that_takes_too_long_is_stopped() -> None:
    run = Runs(_failed, timeout_s=0.05).start("v1", _idle)
    await _ended(run)
    assert "timed_out" in _text(run)


async def test_closing_interrupts_the_runs_that_are_going() -> None:
    runs = Runs(_failed)
    run = runs.start("v1", _idle)
    await asyncio.sleep(0.01)  # let it start
    await runs.close()
    assert run.ended
    assert "interrupted" in _text(run)


async def test_room_is_limited_in_all_and_for_one_visitor() -> None:
    gate = asyncio.Event()

    async def work(run: Run) -> None:
        await gate.wait()
        run.end("done", Note())

    runs = Runs(_failed, max_running=2, max_per_owner=1)
    first = runs.start("v1", work)
    with pytest.raises(Busy):
        runs.start("v1", work)  # one at a time for a visitor
    second = runs.start("v2", work)
    with pytest.raises(Busy) as busy:
        runs.start("v3", work)  # two in all
    assert busy.value.retry_after > 0
    gate.set()
    await _ended(first)
    await _ended(second)
    third = runs.start("v3", work)  # runs that have ended make room
    await _ended(third)


async def test_a_run_belongs_to_the_visitor_who_started_it() -> None:
    async def work(run: Run) -> None:
        run.end("done", Note())

    runs = Runs(_failed)
    run = runs.start("v1", work)
    assert runs.get(run.id, "v1") is run
    assert runs.get(run.id, "v2") is None
    assert runs.get(run.id, None) is None
    assert runs.get("unknown", "v1") is None


async def test_an_ended_run_is_forgotten_after_the_ttl_and_a_running_one_is_not() -> None:
    now = [0.0]

    async def quick(run: Run) -> None:
        run.end("done", Note())

    runs = Runs(_failed, ttl_s=100, clock=lambda: now[0])
    quick_run = runs.start("v1", quick)
    slow_run = runs.start("v2", _idle)
    await _ended(quick_run)
    now[0] = 99
    assert runs.get(quick_run.id, "v1") is quick_run
    now[0] = 10_000
    assert runs.get(quick_run.id, "v1") is None
    assert runs.get(slow_run.id, "v2") is slow_run
    await runs.close()
