"""Three-state conclusions and exact threshold comparisons.

Every framework conclusion carries its value, the rule applied, the sample, the
comparator where there is one, a status and a reason. The status is one of
``satisfied``, ``not_satisfied`` or ``not_evaluable``. They combine by one rule:
a known failure establishes ``not_satisfied`` even when another condition is
unavailable; otherwise anything unavailable leaves the whole ``not_evaluable``;
only when every condition is known and met is the whole ``satisfied``.

Comparisons are exact. Scores are already fractions; a float (a regression
coefficient, say) is compared at the exact value of the double it is, via
``Fraction(float)``, never after rounding. Minima use ``>=``, maxima ``<=``, and
the similarity bound on non-correspondence is strict, ``< 0.03``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable

from .scores import fraction_record

SATISFIED = "satisfied"
NOT_SATISFIED = "not_satisfied"
NOT_EVALUABLE = "not_evaluable"
STATUSES = (SATISFIED, NOT_SATISFIED, NOT_EVALUABLE)


def as_exact(value: Fraction | int | float | str) -> Fraction:
    """Exact rational value. Strings are decimals; floats are taken at their exact value."""

    if isinstance(value, bool):
        raise TypeError("a boolean is not a number here")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("a non-finite value cannot be compared with a threshold")
        return Fraction(value)
    return Fraction(value)


def at_least(value, threshold) -> bool:
    return as_exact(value) >= as_exact(threshold)


def at_most(value, threshold) -> bool:
    return as_exact(value) <= as_exact(threshold)


def strictly_below(value, threshold) -> bool:
    return as_exact(value) < as_exact(threshold)


@dataclass(frozen=True)
class Conclusion:
    """One framework conclusion. ``value`` is whatever the rule was applied to."""

    name: str
    value: Any
    rule: str
    sample: str
    status: str
    reason: str | None = None
    comparator: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")
        if self.status != SATISFIED and not self.reason:
            raise ValueError(f"{self.name}: a status other than satisfied needs a reason")

    def as_record(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, Fraction):
            value = fraction_record(value)
        elif isinstance(value, Conclusion):
            value = value.as_record()
        return {"name": self.name, "value": value, "rule": self.rule, "sample": self.sample,
                "comparator": self.comparator, "status": self.status, "reason": self.reason}


def combine(name: str, parts: Iterable[Conclusion], rule: str, sample: str) -> Conclusion:
    """Three-valued conjunction: a known failure wins over an unavailable part."""

    parts = list(parts)
    failed = [p.name for p in parts if p.status == NOT_SATISFIED]
    missing = [p.name for p in parts if p.status == NOT_EVALUABLE]
    if failed:
        status, reason = NOT_SATISFIED, "not satisfied: " + ", ".join(failed)
        if missing:
            reason += "; also not evaluable: " + ", ".join(missing)
    elif missing:
        status, reason = NOT_EVALUABLE, "not evaluable: " + ", ".join(missing)
    else:
        status, reason = SATISFIED, None
    return Conclusion(name, {p.name: p.status for p in parts}, rule, sample, status, reason)


def threshold_conclusion(name: str, value, threshold, *, kind: str, sample: str,
                         rule: str, comparator: str | None = None,
                         missing_reason: str | None = None) -> Conclusion:
    """Apply one threshold. ``kind``: 'at_least', 'at_most' or 'strictly_below'."""

    if value is None:
        return Conclusion(name, None, rule, sample, NOT_EVALUABLE,
                          missing_reason or "value not available", comparator)
    test = {"at_least": at_least, "at_most": at_most, "strictly_below": strictly_below}[kind]
    ok = test(value, threshold)
    return Conclusion(name, value, rule, sample, SATISFIED if ok else NOT_SATISFIED,
                      None if ok else f"{rule} not met", comparator)


__all__ = [
    "NOT_EVALUABLE",
    "NOT_SATISFIED",
    "SATISFIED",
    "STATUSES",
    "Conclusion",
    "as_exact",
    "at_least",
    "at_most",
    "combine",
    "strictly_below",
    "threshold_conclusion",
]
