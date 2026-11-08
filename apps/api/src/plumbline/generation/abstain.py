"""Abstention and partial answers: when Plumbline declines, in whole or in part, and the
plain-English reason it gives the reader.

Reviewed line by line before merge. Declining is a result, not a failure: an answer the
indexed law does not support is worse than none. It is decided at three moments.

1. Before generation, with no model call (`before_generation`): none of the jurisdictions
   the question asks about is indexed, retrieval found nothing, or the best score of the
   kind the configuration names (`abstain_score`: the reranker's offline, the dense
   similarity online) is under its threshold.
2. After generation and verification (`after_generation`): the model's own abstention
   stands; an answer with no verified citation is withdrawn, because nothing in it could
   be checked against the law's text; and an answer that leaves out a jurisdiction the
   question asked about, because Plumbline does not hold it, is partial. A partial answer
   from the model, such as the preemption pattern (cite s. 83.425, decline on the text of a
   local ordinance, which is not indexed), stands only with a verified citation.
3. Offline (`tune_threshold`): the threshold is chosen on the dev split and never on test.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from plumbline.core.config import AbstainScore
from plumbline.core.types import AnswerStatus, GoldenItem, Jurisdiction, Retrieved
from rag_eval.schema import Split
from rag_eval.stats import wilson_interval


@dataclass(frozen=True)
class Decision:
    status: AnswerStatus
    reason: str | None = None  # plain English, shown to the reader; None when answered


def before_generation(
    asked: Collection[Jurisdiction],  # asked about or detected; empty when unknown
    indexed: Collection[Jurisdiction],
    retrieved: Sequence[Retrieved],
    threshold: float | None,  # the configuration's abstain_threshold
    score: AbstainScore = "rerank",  # the configuration's abstain_score: what the threshold reads
) -> Decision | None:
    """An abstention that needs no model call, or None to go on and generate."""
    if asked and not set(asked) & set(indexed):
        return _abstain(f"Plumbline does not hold the tenancy law of {names(asked)}.")
    if not retrieved:
        return _abstain("No provision of the law Plumbline holds matches this question.")
    top = top_score(retrieved, score)
    # The threshold is on the scale of the score it was tuned on. A list without that score
    # (a reranked configuration whose reranker did not run) has nothing to compare it with.
    if threshold is not None and top is not None and top < threshold:
        return _abstain(
            "No provision of the law Plumbline holds is close enough to this question to answer it."
        )
    return None


def after_generation(
    model_status: AnswerStatus,
    model_reason: str | None,
    verified: int,  # citations that passed the verifier
    missing: Collection[Jurisdiction],  # asked about but not indexed
) -> Decision:
    """The answer's final status, once its citations are verified."""
    if model_status is AnswerStatus.ABSTAINED:
        return _abstain(model_reason or "The law Plumbline holds does not answer this question.")
    if verified == 0:
        return _abstain(
            "None of the answer's quotations could be found in the law it cites, so it "
            "cannot be relied on."
        )
    reasons = []
    if model_status is AnswerStatus.PARTIAL:
        reasons.append(model_reason or "The law Plumbline holds answers only part of this.")
    if missing:
        reasons.append(f"Plumbline does not hold the tenancy law of {names(missing)}.")
    if reasons:
        return Decision(AnswerStatus.PARTIAL, " ".join(reasons))
    return Decision(AnswerStatus.ANSWERED)


def top_score(retrieved: Sequence[Retrieved], score: AbstainScore = "rerank") -> float | None:
    """The best score of this kind among the retrieved, or None when none carries it (in a
    hybrid list, a passage only BM25 found has no dense score)."""
    values = [v for r in retrieved if (v := getattr(r.scores, score)) is not None]
    return max(values, default=None)


def missing_jurisdictions(
    asked: Sequence[Jurisdiction], indexed: Collection[Jurisdiction]
) -> list[Jurisdiction]:
    return [j for j in dict.fromkeys(asked) if j not in indexed]


def names(jurisdictions: Collection[Jurisdiction]) -> str:
    """Names for a sentence: Dubai; Dubai or Spain; Dubai, Spain or Colombia."""
    words = [j.value.capitalize() for j in dict.fromkeys(jurisdictions)]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} or {words[-1]}"


@dataclass(frozen=True)
class Tuned:
    """A tuned threshold and how it does on the items it was tuned on, per class: an
    abstain side of about 17 dev items is uncertain by some twenty points, which the
    interval shows."""

    threshold: float
    balanced_accuracy: float
    caught: int  # items that should abstain and do
    should: int
    kept: int  # items that should answer and do
    should_not: int

    @property
    def caught_interval(self) -> tuple[float, float]:
        return wilson_interval(self.caught, self.should)

    @property
    def kept_interval(self) -> tuple[float, float]:
        return wilson_interval(self.kept, self.should_not)


def tune_threshold(items: Sequence[tuple[GoldenItem, float | None]]) -> float:
    return tune(items).threshold


def tune(items: Sequence[tuple[GoldenItem, float | None]]) -> Tuned:
    """The threshold with the best balanced accuracy on dev items, each paired with its top
    score of the kind the configuration names (`top_score`): an item abstains when its
    score is under the threshold, and it should when the golden set expects it to.

    Balanced accuracy weighs the items that should abstain (about one in seven) as much as
    the rest, so a threshold cannot win by never abstaining. The candidates are the scores
    themselves, which covers every distinct outcome; ties go to the lowest, the threshold
    that declines least. The threshold returned is then the midpoint between that score and
    the next lower one: the same decisions on these items, and not sitting exactly on the
    score of an item that should answer, where a new question scoring a hair lower would
    abstain. Items with no score cannot be thresholded and are left out.
    """
    for item, _ in items:
        if item.split is not Split.DEV:
            raise ValueError(f"{item.id} is in the {item.split.value} split: tune on dev only")
    scored = [(score, item.expected_abstain) for item, score in items if score is not None]
    should = sum(1 for _, abstain in scored if abstain)
    should_not = len(scored) - should
    if not should or not should_not:
        raise ValueError("tuning needs scored items that should and should not abstain")

    def outcome(threshold: float) -> tuple[int, int]:
        caught = sum(1 for s, abstain in scored if abstain and s < threshold)
        kept = sum(1 for s, abstain in scored if not abstain and s >= threshold)
        return caught, kept

    def balanced_accuracy(threshold: float) -> float:
        caught, kept = outcome(threshold)
        return (caught / should + kept / should_not) / 2

    best = max({s for s, _ in scored}, key=lambda t: (balanced_accuracy(t), -t))
    below = [s for s, _ in scored if s < best]
    threshold = (max(below) + best) / 2 if below else best
    caught, kept = outcome(threshold)
    return Tuned(threshold, balanced_accuracy(threshold), caught, should, kept, should_not)


def _abstain(reason: str) -> Decision:
    return Decision(AnswerStatus.ABSTAINED, reason)
