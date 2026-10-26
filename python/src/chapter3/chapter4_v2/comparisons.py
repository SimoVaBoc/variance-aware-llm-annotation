"""Observed best comparators and the declared margins on B.

The comparator search runs over the whole declared set, adequate or not. Among
comparators with exactly equal BA the reported identity is the smallest
procedure ID in ascending lexicographic order (D-REG-03); this names the
comparator and never changes the margin.

* G: three margins, against the best CB, the best post-S VA and the best of all
  30 configurations. The third equals the minimum of the first two; this is an
  identity of the point estimates and is checked, not assumed.
* A standalone configuration: its BA minus the best BA among the other 30
  primary procedures, G included.

An observed best comparator is an in-sample benchmark. Intervals computed with
it held fixed are conditional on that choice and do not validate a winner.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping

from .procedures import KIND_CB, KIND_VA_POST_S, Registry
from .scores import AnnotationScores
from .spec import AnalysisSpec
from .thresholds import NOT_EVALUABLE, Conclusion, threshold_conclusion

MARGIN_RULE = "BA margin >= {threshold} (inclusive, exact)"
G_MARGINS = ("g_minus_best_cb", "g_minus_best_va_post_s", "g_minus_best_all_30")


@dataclass(frozen=True)
class Comparator:
    procedure_id: str
    ba: Fraction
    tied_ids: tuple[str, ...]


def best_of(scores: Mapping[str, AnnotationScores], ids: Iterable[str]) -> Comparator | None:
    """Highest BA among ``ids``; ties named by the smallest ID. None if no BA is evaluable."""

    evaluable = [(scores[i].ba, i) for i in ids if scores[i].ba is not None]
    if not evaluable:
        return None
    top = max(ba for ba, _ in evaluable)
    tied = tuple(sorted(i for ba, i in evaluable if ba == top))
    return Comparator(tied[0], top, tied)


def comparator_sets(registry: Registry) -> dict[str, tuple[str, ...]]:
    cb = tuple(p.procedure_id for p in registry.primary_of_kind(KIND_CB))
    va = tuple(p.procedure_id for p in registry.primary_of_kind(KIND_VA_POST_S))
    return {"g_minus_best_cb": cb, "g_minus_best_va_post_s": va, "g_minus_best_all_30": cb + va}


def g_comparators(registry: Registry,
                  scores: Mapping[str, AnnotationScores]) -> dict[str, Comparator | None]:
    return {name: best_of(scores, ids) for name, ids in comparator_sets(registry).items()}


def margin_conclusion(name: str, candidate_ba: Fraction | None, comparator: Comparator | None,
                      spec: AnalysisSpec, sample: str = "B") -> Conclusion:
    threshold = spec.data["scores"]["thresholds"]["ba_margin_min"]
    rule = MARGIN_RULE.format(threshold=threshold)
    if candidate_ba is None or comparator is None:
        return Conclusion(name, None, rule, sample, NOT_EVALUABLE,
                          "candidate or comparator BA not evaluable",
                          comparator.procedure_id if comparator else None)
    return threshold_conclusion(name, candidate_ba - comparator.ba, threshold, kind="at_least",
                                sample=sample, rule=rule, comparator=comparator.procedure_id)


def g_margins(spec: AnalysisSpec, registry: Registry,
              scores: Mapping[str, AnnotationScores]) -> dict[str, Conclusion]:
    comparators = g_comparators(registry, scores)
    g_ba = scores[registry.g.procedure_id].ba
    out = {name: margin_conclusion(name, g_ba, comparators[name], spec) for name in G_MARGINS}
    first, second, third = (out[n].value for n in G_MARGINS)
    if None not in (first, second, third) and third != min(first, second):
        raise AssertionError("the best-of-30 margin must equal the minimum of the other two")
    return out


def configuration_ids(registry: Registry) -> tuple[str, ...]:
    return comparator_sets(registry)["g_minus_best_all_30"]


def standalone_leader(registry: Registry,
                      scores: Mapping[str, AnnotationScores]) -> Comparator | None:
    """The configuration with the highest BA on the full benchmark (proposed D-ROB-03)."""

    return best_of(scores, configuration_ids(registry))


def standalone_comparator(candidate: str, registry: Registry,
                          scores: Mapping[str, AnnotationScores]) -> Comparator | None:
    others = [p.procedure_id for p in registry.primary if p.procedure_id != candidate]
    return best_of(scores, others)


def standalone_margin(candidate: str, spec: AnalysisSpec, registry: Registry,
                      scores: Mapping[str, AnnotationScores]) -> Conclusion:
    return margin_conclusion(f"standalone_margin::{candidate}", scores[candidate].ba,
                             standalone_comparator(candidate, registry, scores), spec)


__all__ = [
    "G_MARGINS",
    "Comparator",
    "best_of",
    "comparator_sets",
    "configuration_ids",
    "g_comparators",
    "g_margins",
    "margin_conclusion",
    "standalone_comparator",
    "standalone_leader",
    "standalone_margin",
]
