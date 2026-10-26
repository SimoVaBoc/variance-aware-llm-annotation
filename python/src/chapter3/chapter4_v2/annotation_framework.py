"""One call that evaluates the annotation-level framework on a validated input.

It wires the modules together in the order the plan fixes: registry, vectors,
samples, scores on B, comparators and margins, robustness, framework quantities,
the evidence table and, on request, the framework bootstrap. Downstream evidence
is optional; without it every condition that needs it is ``not_evaluable``.

Nothing is read from disk here; the input has already crossed the boundary.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .aggregation import build_vectors
from .comparisons import (
    G_MARGINS,
    g_comparators,
    g_margins,
    standalone_comparator,
    standalone_leader,
    standalone_margin,
)
from .framework import (
    CoefficientDistance,
    annotation_adequacy,
    differences,
    directional_corrections,
    evidence_table,
    kappa_exact,
    overall_adequacy,
    pair_table,
    practical_similarity,
    proximity_or_pending,
    shared_errors,
)
from .framework_bootstrap import draws_for, run_framework_bootstrap
from .inputs import TaskLevelInput
from .procedures import build_registry
from .provenance import output_header
from .robustness import g_omission_checks, leave_one_out
from .samples import (
    h1_supports,
    planned_benchmark_check,
    sample_b,
    sample_i27,
    sample_r,
)
from .scores import missing_by_procedure, score_vector
from .spec import AnalysisSpec
from .thresholds import NOT_EVALUABLE, Conclusion


def evaluate_annotation_framework(
    spec: AnalysisSpec,
    data: TaskLevelInput,
    *,
    proximity: Mapping[str, Conclusion] | None = None,
    distance: CoefficientDistance | None = None,
    downstream: Any = None,
    planned_item_ids: Sequence[str] | None = None,
    run_bootstrap: bool = True,
) -> dict[str, Any]:
    """``downstream`` (a ``firth.DownstreamResult``) supplies proximity and distances at once."""

    registry = build_registry(spec)
    if downstream is not None:
        if proximity is not None or distance is not None:
            raise ValueError("pass either downstream or proximity/distance, not both")
        proximity = downstream.proximity(spec, [p.procedure_id for p in registry.primary])
        distance = downstream.pairwise_distance
    vectors = build_vectors(data, registry)
    b = sample_b(data)
    i27 = sample_i27(data, b)
    r = sample_r(data, b, registry, vectors)
    bench = spec.data["design"]["benchmark"]
    planned_check = planned_benchmark_check(
        data, b, planned_item_ids=planned_item_ids,
        planned_counts={"n_items": bench["planned_n_items"],
                        "positives": bench["planned_human_positives"],
                        "negatives": bench["planned_human_negatives"]})

    primary = [p.procedure_id for p in registry.primary]
    scores = {pid: score_vector(vectors[pid], data, b.members, "B") for pid in primary}
    adequacy = annotation_adequacy(spec, scores)
    prox = proximity_or_pending(registry, proximity)

    comparators = g_comparators(registry, scores)
    margins = g_margins(spec, registry, scores)
    leader = standalone_leader(registry, scores)
    standalone = loo = None
    if leader is not None:
        standalone = standalone_margin(leader.procedure_id, spec, registry, scores)
        loo = leave_one_out(leader.procedure_id, spec, registry, data, vectors, b.members)

    best30 = comparators["g_minus_best_all_30"]
    if best30 is None:
        omissions = {"conclusion": Conclusion("g_six_omissions", None, "six omissions", "B",
                                              NOT_EVALUABLE, "no evaluable comparator")}
    else:
        omissions = g_omission_checks(spec, data, vectors, b.members, i27.members,
                                      best30.procedure_id, best30.ba)

    kappa_vs_human = {}
    for pid in primary:
        kappa, support = kappa_exact(vectors[pid], None, data, b.members)
        kappa_vs_human[pid] = {"kappa": kappa, "valid_paired_support": support,
                               "undefined_is": "NA (None), never 1"}
    pairs = pair_table(registry, vectors, data, b.members)
    shared = shared_errors(spec, registry, vectors, data, b.members)
    corrections = directional_corrections(spec, registry, vectors, data, b.members)
    similarity = practical_similarity(spec, adequacy, prox, pairs, distance)
    found = differences(spec, pairs, distance)
    overall = overall_adequacy(adequacy, prox)
    table = evidence_table(
        leader=leader, adequacy=adequacy, proximity=prox, standalone=standalone,
        leave_one_out=loo["conclusion"] if loo else None, g_id=registry.g.procedure_id,
        g_margin_all_30=margins["g_minus_best_all_30"], g_omissions=omissions["conclusion"],
        similarity=similarity, corrections=corrections, found_differences=found,
        shared=shared, overall=overall)

    result: dict[str, Any] = {
        "header": output_header(spec, synthetic=data.data_kind == "synthetic"),
        "samples": {"B": b, "I27": i27, "R": r}, "planned_benchmark_check": planned_check,
        "h1_supports": h1_supports(data), "vectors": vectors, "scores_B": scores,
        "missing_by_procedure_B": missing_by_procedure(vectors, data, b.members, "B"),
        "kappa_vs_human_B": kappa_vs_human,
        "adequacy": adequacy, "proximity": prox, "comparators": comparators,
        "g_margins": margins, "standalone_leader": leader, "standalone_margin": standalone,
        "leave_one_out": loo, "g_omissions": omissions, "pairs": pairs,
        "shared_errors": shared, "directional_corrections": corrections,
        "similarity": similarity, "differences": found, "overall_adequacy": overall,
        "evidence_table": table, "bootstrap": None,
    }
    if run_bootstrap:
        declared = {name: (registry.g.procedure_id, comparators[name]) for name in G_MARGINS}
        if leader is not None:
            declared[f"standalone_margin::{leader.procedure_id}"] = (
                leader.procedure_id,
                standalone_comparator(leader.procedure_id, registry, scores))
        draws = draws_for(spec, data, b.members)
        result["bootstrap"] = run_framework_bootstrap(spec, data, draws, vectors, primary,
                                                      scores, declared)
        result["bootstrap_draws"] = draws
    return result


__all__ = ["evaluate_annotation_framework"]
