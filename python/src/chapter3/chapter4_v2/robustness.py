"""Deterministic robustness checks: six panel omissions for G, leave-one-out for a leader.

**G omissions.** Each prompt is omitted from every model, and each model from
every prompt, leaving 18 calls. Only campaigns of the *original* I27 are scored;
a campaign that would become complete only after an omission is not recovered.
B, I27 and the original best-of-30 comparator stay fixed.

* Prompt omitted: within each model the two remaining post-S votes give that
  model's label if they agree, and the possibility set {0, 1} if they do not.
  Every combination of the three models' possibilities goes through the
  majority; the final label is determined only if every combination gives it,
  otherwise the result is a final tie.
* Model omitted: the two remaining models' within-model labels decide if they
  agree; otherwise a final tie. Uncertain votes are never dropped.

Credit is 1 for a determined correct label, 0 for a determined incorrect one,
1/2 for a final tie and 0 outside the original I27. The 1/2 exists only inside
this score: no label vector here ever holds it, and nothing here feeds a
regression.

**Leave-one-out.** The standalone candidate is fixed. For each campaign of B,
that campaign is removed, the class denominators shrink accordingly, and the
strongest of the other 30 primary procedures is recomputed. The margin must
reach the threshold in every omission; the minimum is reported.

The two checks assess different objects and are not placed on one scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Any, Mapping, Sequence

from .aggregation import LabelVector
from .inputs import TaskLevelInput
from .procedures import Registry
from .scores import fraction_record
from .spec import AnalysisSpec
from .thresholds import NOT_EVALUABLE, NOT_SATISFIED, SATISFIED, Conclusion, at_least

UNDETERMINED = frozenset({0, 1})
TIE = "tie"
TIE_CREDIT = Fraction(1, 2)


def two_votes(a: int, b: int) -> frozenset[int]:
    return frozenset({a}) if a == b else UNDETERMINED


def majority_of_possibilities(sets: Sequence[frozenset[int]]) -> int | str:
    """The majority if every allowed combination agrees on it; otherwise a tie."""

    outcomes = {1 if 2 * sum(combo) > len(combo) else 0 for combo in product(*sets)}
    return outcomes.pop() if len(outcomes) == 1 else TIE


def credit(outcome: int | str, human: int) -> Fraction:
    if outcome == TIE:
        return TIE_CREDIT
    return Fraction(int(outcome == human))


@dataclass(frozen=True)
class Omission:
    kind: str
    omitted: str

    @property
    def name(self) -> str:
        return f"omit_{self.kind}::{self.omitted}"


def omissions(spec: AnalysisSpec) -> tuple[Omission, ...]:
    return tuple(Omission("prompt", t) for t in spec.va_template_ids) + tuple(
        Omission("model", m) for m in spec.model_keys)


def reduced_outcome(omission: Omission, item: str, spec: AnalysisSpec,
                    vectors: Mapping[str, LabelVector]) -> int | str:
    """Final label or tie on a reduced panel. ``item`` must be in the original I27."""

    scheme = spec.data["procedures"]["id_scheme"]
    if omission.kind == "prompt":
        sets = []
        for m in spec.model_keys:
            kept = [t for t in spec.va_template_ids if t != omission.omitted]
            a, b = (vectors[scheme["va_post_s"].format(model_key=m, template_id=t)].label(item)
                    for t in kept)
            sets.append(two_votes(a, b))
        return majority_of_possibilities(sets)
    kept = [m for m in spec.model_keys if m != omission.omitted]
    a, b = (vectors[scheme["va_post_sp"].format(model_key=m)].label(item) for m in kept)
    return a if a == b else TIE


def g_omission_checks(spec: AnalysisSpec, data: TaskLevelInput,
                      vectors: Mapping[str, LabelVector], b_members: Sequence[str],
                      i27_members: Sequence[str], comparator_id: str,
                      comparator_ba: Fraction) -> dict[str, Any]:
    threshold = spec.data["scores"]["thresholds"]["ba_margin_min"]
    in_i27 = set(i27_members)
    positives = [i for i in b_members if data.items[i].human == 1]
    negatives = [i for i in b_members if data.items[i].human == 0]
    results, conclusions = [], []
    for omission in omissions(spec):
        sums = {1: Fraction(0), 0: Fraction(0)}
        ties = 0
        for item in b_members:
            human = data.items[item].human
            if item not in in_i27:
                continue
            outcome = reduced_outcome(omission, item, spec, vectors)
            ties += outcome == TIE
            sums[human] += credit(outcome, human)
        if not positives or not negatives:
            margin, status, reason = None, NOT_EVALUABLE, "a HUMAN class is absent from B"
        else:
            ba = (sums[1] / len(positives) + sums[0] / len(negatives)) / 2
            margin = ba - comparator_ba
            ok = at_least(margin, threshold)
            status, reason = (SATISFIED, None) if ok else (NOT_SATISFIED, "margin below threshold")
        results.append({"omission": omission.name, "final_ties": ties,
                        "margin": fraction_record(margin), "status": status})
        conclusions.append(Conclusion(omission.name, margin, f"margin >= {threshold}", "B",
                                      status, reason, comparator_id))
    return _summarise("g_six_omissions", conclusions, results, threshold, comparator_id)


def leave_one_out(candidate: str, spec: AnalysisSpec, registry: Registry,
                  data: TaskLevelInput, vectors: Mapping[str, LabelVector],
                  b_members: Sequence[str]) -> dict[str, Any]:
    threshold = spec.data["scores"]["thresholds"]["ba_margin_min"]
    primary = [p.procedure_id for p in registry.primary]
    human = {i: data.items[i].human for i in b_members}
    n = {1: sum(1 for h in human.values() if h == 1), 0: sum(1 for h in human.values() if h == 0)}
    correct = {pid: {c: sum(1 for i in b_members if human[i] == c
                            and vectors[pid].label(i) == c) for c in (0, 1)}
               for pid in primary}
    results, conclusions = [], []
    for item in sorted(b_members):
        c = human[item]
        n_left = dict(n)
        n_left[c] -= 1
        name = f"omit_campaign::{item}"
        if n_left[0] == 0 or n_left[1] == 0:
            conclusions.append(Conclusion(name, None, f"margin >= {threshold}", "B minus one",
                                          NOT_EVALUABLE, "a HUMAN class becomes empty"))
            results.append({"omitted": item, "margin": None, "comparator": None,
                            "status": NOT_EVALUABLE})
            continue
        ba = {}
        for pid in primary:
            hits = dict(correct[pid])
            hits[c] -= int(vectors[pid].label(item) == c)
            ba[pid] = (Fraction(hits[1], n_left[1]) + Fraction(hits[0], n_left[0])) / 2
        others = sorted((pid for pid in primary if pid != candidate), key=lambda p: (-ba[p], p))
        best = others[0]
        margin = ba[candidate] - ba[best]
        ok = at_least(margin, threshold)
        status = SATISFIED if ok else NOT_SATISFIED
        conclusions.append(Conclusion(name, margin, f"margin >= {threshold}", "B minus one",
                                      status, None if ok else "margin below threshold", best))
        results.append({"omitted": item, "margin": fraction_record(margin), "comparator": best,
                        "status": status})
    summary = _summarise(f"leave_one_out::{candidate}", conclusions, results, threshold, None)
    summary["candidate"] = candidate
    return summary


def _summarise(name: str, conclusions: list[Conclusion], results: list[dict], threshold: str,
               comparator: str | None) -> dict[str, Any]:
    margins = [c.value for c in conclusions if c.value is not None]
    statuses = [c.status for c in conclusions]
    if NOT_SATISFIED in statuses:
        status = NOT_SATISFIED
    elif NOT_EVALUABLE in statuses or not statuses:
        status = NOT_EVALUABLE
    else:
        status = SATISFIED
    minimum = min(margins) if margins else None
    overall = Conclusion(name, minimum, f"margin >= {threshold} in every perturbation", "B",
                         status, None if status == SATISFIED else
                         f"{statuses.count(NOT_SATISFIED)} below threshold, "
                         f"{statuses.count(NOT_EVALUABLE)} not evaluable", comparator)
    return {"conclusion": overall, "n_perturbations": len(conclusions),
            "n_satisfied": statuses.count(SATISFIED), "minimum_margin": fraction_record(minimum),
            "perturbations": results}


__all__ = [
    "TIE",
    "TIE_CREDIT",
    "UNDETERMINED",
    "Omission",
    "credit",
    "g_omission_checks",
    "leave_one_out",
    "majority_of_possibilities",
    "omissions",
    "reduced_outcome",
    "two_votes",
]
