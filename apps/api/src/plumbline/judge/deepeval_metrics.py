"""DeepEval metrics that wrap Plumbline's judge, and the runner the evaluation uses.

The metrics are DeepEval BaseMetrics, so they plug into deepeval.evaluate and its tooling.
Their score is the calibrated judge's verdict (1.0 pass, 0.0 fail), never DeepEval's own
faithfulness score, an uncalibrated ratio of claims a model extracted. The runner awaits
the metrics itself rather than through deepeval.evaluate, which prints, writes files and
keeps global state that a reproducible evaluation has no use for.

Import DeepEval through this module only. On import DeepEval loads .env, which holds the
provider keys, from the working directory into the environment, unless told not to; the
two switches below must be set before its first import. Under pytest, DeepEval's own
plugin imports it before any test module, so the test configuration must turn that
plugin off (-p no:deepeval) for the switches to hold there too.
"""

from __future__ import annotations

import os

os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from plumbline.judge.judge import Criterion, Judge, JudgeError, Judgement

__all__ = ["CorrectnessMetric", "FaithfulnessMetric", "LLMTestCase", "judge_cases"]


class _JudgeMetric(BaseMetric):  # type: ignore[no-untyped-call]  # DeepEval's __init_subclass__
    criterion: Criterion

    def __init__(self, judge: Judge) -> None:
        self.judge = judge
        self.threshold = 1.0  # a binary verdict: only a pass succeeds
        self.evaluation_model = judge.model
        self.include_reason = True
        self.async_mode = True
        self.strict_mode = True
        self.score: float | None = None
        self.success: bool | None = None
        self.reason: str | None = None
        self.error: str | None = None
        self.evaluation_cost: float | None = None
        self.judgement: Judgement | None = None

    @property
    def __name__(self) -> str:
        return f"Plumbline {self.criterion.value}"

    def applies_to(self, case: LLMTestCase) -> bool:
        raise NotImplementedError

    async def _verdict(self, case: LLMTestCase) -> Judgement:
        raise NotImplementedError

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return asyncio.run(self.a_measure(test_case))

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        try:
            self.judgement = await self._verdict(test_case)
        except JudgeError as exc:
            self.error = str(exc)
            raise
        self.score = 1.0 if self.judgement.passed else 0.0
        self.success = self.judgement.passed
        self.reason = self.judgement.reasoning
        self.evaluation_cost = self.judgement.cost_usd
        return self.score

    def is_successful(self) -> bool:
        return bool(self.success)


class FaithfulnessMetric(_JudgeMetric):  # type: ignore[no-untyped-call]
    """Needs the answer and the source texts it was written from (retrieval_context)."""

    criterion = Criterion.FAITHFULNESS

    def applies_to(self, case: LLMTestCase) -> bool:
        return bool(case.actual_output and case.retrieval_context)

    async def _verdict(self, case: LLMTestCase) -> Judgement:
        sources = [str(text) for text in case.retrieval_context or []]
        return await self.judge.faithfulness(case.input, case.actual_output or "", sources)


class CorrectnessMetric(_JudgeMetric):  # type: ignore[no-untyped-call]
    """Needs the answer and the gold reference answer (expected_output)."""

    criterion = Criterion.CORRECTNESS

    def applies_to(self, case: LLMTestCase) -> bool:
        return bool(case.actual_output and case.expected_output)

    async def _verdict(self, case: LLMTestCase) -> Judgement:
        return await self.judge.correctness(
            case.input, case.actual_output or "", case.expected_output or ""
        )


async def judge_cases(
    judge: Judge,
    cases: Mapping[str, LLMTestCase],
    *,
    metrics: Sequence[type[_JudgeMetric]] = (FaithfulnessMetric, CorrectnessMetric),
    concurrency: int = 4,
) -> dict[str, dict[str, float | None]]:
    """Each case's verdicts by criterion, as EvalResult.metrics holds them: 1.0 pass, 0.0
    fail, None when the case lacks what the criterion needs or the judge's reply could not
    be read. A fresh metric per case and criterion, since a DeepEval metric keeps state."""
    limit = asyncio.Semaphore(concurrency)

    async def one(case: LLMTestCase, metric: _JudgeMetric) -> float | None:
        if not metric.applies_to(case):
            return None
        async with limit:
            try:
                return await metric.a_measure(case)
            except JudgeError:
                return None

    keys = [(case_id, kind) for case_id in cases for kind in metrics]
    scores = await asyncio.gather(*(one(cases[case_id], kind(judge)) for case_id, kind in keys))
    out: dict[str, dict[str, float | None]] = {case_id: {} for case_id in cases}
    for (case_id, kind), score in zip(keys, scores, strict=True):
        out[case_id][kind.criterion.value] = score
    return out
