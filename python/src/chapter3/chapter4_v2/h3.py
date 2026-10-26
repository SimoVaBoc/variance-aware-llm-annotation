"""H3: the final VA aggregate against the mean of its 27 components, on I27 (point contrast).

On I27 every one of the 27 planned VA calls is valid, so G and all 27 component
vectors (one per model x prompt x generation, each a whole vector over the
campaigns) are scored on the same campaigns with the same class denominators:

    Delta_BA = BA(G) - (1/27) * sum_k BA(component_k)

The comparator is the uniform mean of the 27 component BAs, not the best
component, not the nine post-S means and not a pooled majority. If either HUMAN
class is absent from I27, BA and the contrast cannot be computed (status
``not_computable``; the brief calls this not evaluable). The framework
margin of 0.03 does not apply to H3. By linearity the contrast splits into a
sensitivity and a specificity contribution, each half the class-specific gap;
the two are reported and are checked to add up to Delta_BA.

This is a descriptive benchmark difference on I27. Inference to comparable
campaigns is a separate step whose procedure is undecided (D-H3-02): the entry
:func:`h3_inference` exists, stays disabled and cannot execute. The framework
bootstrap is not used here.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping

from .aggregation import LabelVector
from .inputs import TaskLevelInput
from .pending import refuse
from .procedures import Registry
from .samples import SampleMembership
from .scores import fraction_record, score_vector
from .spec import AnalysisSpec
from .analysis_status import COMPUTED, NOT_COMPUTABLE


def h3_point_contrast(data: TaskLevelInput, registry: Registry,
                      vectors: Mapping[str, LabelVector], b: SampleMembership,
                      i27: SampleMembership) -> dict[str, Any]:
    members = list(i27.members)
    g = score_vector(vectors[registry.g.procedure_id], data, members, "I27")
    components = [score_vector(vectors[p.procedure_id], data, members, "I27")
                  for p in registry.va_components]
    coverage = {
        "B": dict(b.class_counts), "I27": dict(i27.class_counts),
        "excluded_from_I27": len(i27.exclusions),
        "excluded_class_counts": dict(i27.excluded_class_counts),
        "exclusion_reason_counts": i27.reason_counts(data),
        "exclusion_reason_counts_overlap": True,
    }
    record: dict[str, Any] = {"analysis": "H3 point contrast", "sample": "I27",
                              "data_kind": data.data_kind, "n_components": len(components),
                              "coverage": coverage, "framework_margin_applied": False}
    if g.ba is None or any(c.ba is None for c in components):
        return {**record, "status": NOT_COMPUTABLE,
                "reason": g.not_evaluable_reason or "a HUMAN class is absent from I27",
                "delta_ba": None}
    if any(c.positive.missing or c.negative.missing for c in components) \
            or g.positive.missing or g.negative.missing:
        raise AssertionError("on I27 every component and G must be fully valid")
    n = len(components)
    mean = {key: sum((getattr(c, key) for c in components), Fraction(0)) / n
            for key in ("a_plus", "a_minus", "ba")}
    delta = g.ba - mean["ba"]
    sens = (g.a_plus - mean["a_plus"]) / 2
    spec_ = (g.a_minus - mean["a_minus"]) / 2
    if sens + spec_ != delta:
        raise AssertionError("class contributions must add up to Delta_BA")
    return {**record, "status": COMPUTED, "reason": None,
            "ba_g": fraction_record(g.ba), "mean_component_ba": fraction_record(mean["ba"]),
            "delta_ba": fraction_record(delta),
            "sensitivity_contribution": fraction_record(sens),
            "specificity_contribution": fraction_record(spec_),
            "g_class_scores": {"sensitivity": fraction_record(g.a_plus),
                               "specificity": fraction_record(g.a_minus)},
            "mean_component_class_scores": {"sensitivity": fraction_record(mean["a_plus"]),
                                            "specificity": fraction_record(mean["a_minus"])},
            "component_ba": {p.procedure_id: fraction_record(c.ba)
                             for p, c in zip(registry.va_components, components)},
            "note": "Descriptive benchmark difference on I27; the sign gives the direction. "
                    "The status says only whether the contrast was computed; no criterion "
                    "or margin is applied."}


def h3_inference(spec: AnalysisSpec, *args: Any, **kwargs: Any) -> None:
    """Disabled until D-H3-02 records one procedure. It never computes anything."""

    refuse(spec, "h3_inference")
    raise NotImplementedError("no H3 inference procedure is implemented")


__all__ = ["h3_inference", "h3_point_contrast"]
