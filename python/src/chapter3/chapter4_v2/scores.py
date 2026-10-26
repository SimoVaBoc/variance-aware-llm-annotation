"""Class-specific correctness with zero credit for missing outputs, and the balanced score.

For procedure j, human class c and a sample S (B for every framework decision):

    A_c(j) = valid correct labels of j in class c / all items of S in class c
    BA(j)  = (A_+(j) + A_-(j)) / 2

The denominator is every item of the class, so a missing label lowers the score
by earning zero. It is not a label: it is counted as *missing*, never as a false
positive or a false negative, and coverage is reported beside the score. These
are not conventional sensitivity and specificity, which condition on valid
responses; the names say so.

Scores are exact fractions, so thresholds are compared without rounding. With a
class absent from the sample its score, and BA, are not evaluable (``None`` with
a reason), never zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Mapping

from .aggregation import LabelVector
from .inputs import TaskLevelInput

CLASS_SCORE_NAME = "class-specific correctness score with zero credit for missing outputs"
BALANCED_SCORE_NAME = "balanced correctness score"
NOT_EVALUABLE_CLASS_ABSENT = "class_absent_from_sample"


def fraction_record(value: Fraction | None) -> dict[str, Any] | None:
    """Exact value for checking, float for reading. ``None`` stays ``None``."""

    if value is None:
        return None
    return {"exact": f"{value.numerator}/{value.denominator}", "value": float(value)}


@dataclass(frozen=True)
class ClassTally:
    n: int
    valid_correct: int
    valid_incorrect: int
    missing: int

    def __post_init__(self) -> None:
        if self.valid_correct + self.valid_incorrect + self.missing != self.n:
            raise ValueError("class tally does not add up to the class size")

    @property
    def score(self) -> Fraction | None:
        return Fraction(self.valid_correct, self.n) if self.n else None

    @property
    def coverage(self) -> Fraction | None:
        return Fraction(self.n - self.missing, self.n) if self.n else None

    def as_record(self) -> dict[str, Any]:
        return {"n": self.n, "valid_correct": self.valid_correct,
                "valid_incorrect": self.valid_incorrect, "missing": self.missing,
                "score": fraction_record(self.score), "coverage": fraction_record(self.coverage)}


@dataclass(frozen=True)
class AnnotationScores:
    procedure_id: str
    sample: str
    data_kind: str
    positive: ClassTally
    negative: ClassTally

    @property
    def a_plus(self) -> Fraction | None:
        return self.positive.score

    @property
    def a_minus(self) -> Fraction | None:
        return self.negative.score

    @property
    def ba(self) -> Fraction | None:
        if self.a_plus is None or self.a_minus is None:
            return None
        return (self.a_plus + self.a_minus) / 2

    @property
    def coverage(self) -> Fraction | None:
        n = self.positive.n + self.negative.n
        return Fraction(n - self.positive.missing - self.negative.missing, n) if n else None

    @property
    def not_evaluable_reason(self) -> str | None:
        absent = [c for c, t in (("positive", self.positive), ("negative", self.negative))
                  if t.n == 0]
        return f"{NOT_EVALUABLE_CLASS_ABSENT}:{'+'.join(absent)}" if absent else None

    def as_record(self) -> dict[str, Any]:
        return {
            "procedure_id": self.procedure_id, "sample": self.sample,
            "data_kind": self.data_kind,
            "class_score_name": CLASS_SCORE_NAME, "balanced_score_name": BALANCED_SCORE_NAME,
            "positive": self.positive.as_record(), "negative": self.negative.as_record(),
            "a_plus": fraction_record(self.a_plus), "a_minus": fraction_record(self.a_minus),
            "ba": fraction_record(self.ba), "coverage": fraction_record(self.coverage),
            "not_evaluable_reason": self.not_evaluable_reason,
        }


def _tally(vector: LabelVector, items: list[str], truth: int) -> ClassTally:
    correct = incorrect = missing = 0
    for item in items:
        label = vector.label(item)
        if label is None:
            missing += 1
        elif label == truth:
            correct += 1
        else:
            incorrect += 1
    return ClassTally(len(items), correct, incorrect, missing)


def score_vector(vector: LabelVector, data: TaskLevelInput, members: Iterable[str],
                 sample: str) -> AnnotationScores:
    """Scores of one vector on a sample, with that sample's actual class denominators."""

    members = list(members)
    humans = {i: data.items[i].human for i in members}
    if any(h not in (0, 1) for h in humans.values()):
        raise ValueError(f"sample {sample!r} contains items without a binary HUMAN class")
    positives = [i for i in members if humans[i] == 1]
    negatives = [i for i in members if humans[i] == 0]
    return AnnotationScores(vector.procedure_id, sample, data.data_kind,
                            _tally(vector, positives, 1), _tally(vector, negatives, 0))


def missing_by_procedure(vectors: Mapping[str, LabelVector], data: TaskLevelInput,
                         members: Iterable[str], sample: str) -> dict[str, dict[str, Any]]:
    """Secondary output for coverage tables: missing labels per procedure, by class and reason."""

    members = list(members)
    out = {}
    for pid, vector in vectors.items():
        by_class = {"positive": 0, "negative": 0}
        by_reason: dict[str, int] = {}
        for item in members:
            if vector.label(item) is None:
                human = data.items[item].human
                by_class["positive" if human == 1 else "negative"] += 1
                reason = vector.missing_reasons[item]
                by_reason[reason] = by_reason.get(reason, 0) + 1
        out[pid] = {"sample": sample, "data_kind": data.data_kind, "kind": vector.kind,
                    "n": len(members), "missing": sum(by_class.values()),
                    "missing_by_class": by_class, "missing_by_reason": dict(sorted(by_reason.items()))}
    return out


__all__ = [
    "BALANCED_SCORE_NAME",
    "CLASS_SCORE_NAME",
    "NOT_EVALUABLE_CLASS_ABSENT",
    "AnnotationScores",
    "ClassTally",
    "fraction_record",
    "missing_by_procedure",
    "score_vector",
]
