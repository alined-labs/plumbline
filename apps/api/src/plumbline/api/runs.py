"""Checks in flight (Lane D, task D7): a check runs in a background task, and its events are
kept in memory for the reader to follow, to resume after a dropped connection and to read
back after a reload.

A run holds the events of a check (its stages, its findings, its end) and never the file
that was uploaded, and nothing here touches the disk. The only things logged are a run's id
and the type of an unexpected error: an error's message can quote the text it choked on.

- A run belongs to the visitor who started it; anyone else is told it does not exist.
- A run is forgotten TTL_S after it ends, and a run that takes longer than TIMEOUT_S is
  stopped, so every run ends, and ends with an event that says how.
- At most `max_running` runs go at once, and `max_per_owner` for one visitor: a check is
  many model calls, and a busy server says so (Busy) instead of queueing without bound.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel

log = logging.getLogger(__name__)

TTL_S: Final = 30 * 60
TIMEOUT_S: Final = 10 * 60
RETRY_AFTER_S: Final = 30


class Busy(Exception):
    def __init__(self) -> None:
        super().__init__("Too many checks are running.")
        self.retry_after = RETRY_AFTER_S


@dataclass(frozen=True)
class RunEvent:
    id: int  # 1, 2, 3 ...: what a reader sends back as Last-Event-ID to resume
    name: str
    data: BaseModel


@dataclass
class Run:
    id: str
    owner: str
    clock: Callable[[], float] = time.monotonic
    events: list[RunEvent] = field(default_factory=list)
    ended_at: float | None = None
    _waiters: set[asyncio.Event] = field(default_factory=set)

    @property
    def ended(self) -> bool:
        return self.ended_at is not None

    def emit(self, name: str, data: BaseModel) -> None:
        if self.ended:  # nothing follows a run's last event
            return
        self.events.append(RunEvent(len(self.events) + 1, name, data))
        for waiter in self._waiters:
            waiter.set()

    def end(self, name: str, data: BaseModel) -> None:
        """Add the run's last event; readers stop after it."""
        self.emit(name, data)
        if self.ended_at is None:
            self.ended_at = self.clock()

    async def wait(self, after: int) -> None:
        """Return once there is an event after `after`, or the run has ended."""
        if len(self.events) > after or self.ended:
            return
        waiter = asyncio.Event()
        self._waiters.add(waiter)
        try:
            await waiter.wait()
        finally:
            self._waiters.discard(waiter)


Work = Callable[[Run], Awaitable[None]]
Failure = Callable[[str, str], tuple[str, BaseModel]]


class Runs:
    def __init__(
        self,
        failure: Failure,
        *,
        max_running: int = 4,
        max_per_owner: int = 1,
        ttl_s: float = TTL_S,
        timeout_s: float = TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure = failure  # (code, message) -> the event that ends a run that failed
        self._max_running = max_running
        self._max_per_owner = max_per_owner
        self._ttl_s = ttl_s
        self._timeout_s = timeout_s
        self._clock = clock
        self._runs: dict[str, Run] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def check_room(self, owner: str) -> None:
        """Raise Busy unless a run for `owner` could start now."""
        going = [run for run in self._runs.values() if not run.ended]
        if len(going) >= self._max_running:
            raise Busy
        if sum(run.owner == owner for run in going) >= self._max_per_owner:
            raise Busy

    def start(self, owner: str, work: Work) -> Run:
        self._forget_old()
        self.check_room(owner)
        run = Run(id=secrets.token_urlsafe(16), owner=owner, clock=self._clock)
        self._runs[run.id] = run
        task = asyncio.create_task(self._drive(run, work))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    def get(self, run_id: str, owner: str | None) -> Run | None:
        self._forget_old()
        run = self._runs.get(run_id)
        return run if run is not None and run.owner == owner else None

    async def close(self) -> None:
        """Stop the runs still going; each ends with an event that says it was interrupted."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _drive(self, run: Run, work: Work) -> None:
        try:
            async with asyncio.timeout(self._timeout_s):
                await work(run)
            if not run.ended:  # the work returned without saying how it ended
                self._fail(run, "internal", "The check ended without a result.")
        except TimeoutError:
            self._fail(run, "timed_out", "The check took too long and was stopped.")
        except asyncio.CancelledError:
            self._fail(run, "interrupted", "The check was interrupted.")
            raise
        except Exception as exc:
            log.error("check %s failed: %s", run.id, type(exc).__name__)
            self._fail(run, "internal", "The check failed on our side. Please try again.")

    def _fail(self, run: Run, code: str, message: str) -> None:
        run.end(*self._failure(code, message))

    def _forget_old(self) -> None:
        now = self._clock()
        for run_id, run in list(self._runs.items()):
            if run.ended_at is not None and now - run.ended_at > self._ttl_s:
                del self._runs[run_id]
