"""Framework quantities on B and the evidence-to-framework status table.

Everything here is computed from label vectors on B and is exact. Downstream
(Firth) evidence enters as optional inputs: per-procedure HUMAN proximity
conclusions and pairwise coefficient distances. Until they exist, every
condition that needs them is ``not_evaluable``, never assumed.

* Annotation adequacy: A_+ >= 0.75 and A_- >= 0.925, inclusive.
* Pairs: for all 465 pairs of the 31 primary procedures, class-balanced
  non-correspondence, the mean over the two HUMAN classes of the share of
  campaigns where the two labels are not both valid and equal. Two missing
  labels count as non-correspondence. Valid disagreement and missingness are
  reported apart. Kappa on the valid paired support is complementary and
  undefined kappa is NA.
* Shared errors in the fixed groups S_CB (21), S_VA (9) and S_ALL (30); G is not
  a member. Per class: J, E, U, E/N, U/N, E/J when J > 0, and U - E. The
  sufficiency thresholds are derived from the class size and the adequacy
  threshold (N - ceil(a N) + 1, which is 9 and 17 on the planned B); they are
  consequences of adequacy, not adoption conditions.
* Directional corrections for the 36 pairs of post-S VA configurations, on the
  BA scale with B's class denominators.
* Practical similarity over the whole adequate-and-proximate group, unresolved
  differences over the 465 pairs, overall adequacy and the Table 3.4A/B rows.
"""

from __future__ import annotations

import math
from fractions import Fraction
from itertools import combinations
from typing import Any, Callable, Mapping, Sequence

from .aggregation import LabelVector
from .comparisons import Comparator
from .inputs import TaskLevelInput
from .procedures import KIND_CB, KIND_VA_POST_S, Registry
from .scores import AnnotationScores, fraction_record
from .spec import AnalysisSpec
from .thresholds import (
    NOT_EVALUABLE,
    NOT_SATISFIED,
    SATISFIED,
    Conclusion,
    at_least,
    at_most,
    combine,
    strictly_below,
    threshold_conclusion,
)

DOWNSTREAM_PENDING = "downstream Firth evidence not supplied"
CoefficientDistance = Callable[[str, str], "float | None"]


def _classes(data: TaskLevelInput, members: Sequence[str]) -> dict[int, list[str]]:
    return {c: sorted(i for i in members if data.items[i].human == c) for c in (1, 0)}


# --------------------------------------------------------------------------
# adequacy
# --------------------------------------------------------------------------


def annotation_adequacy(spec: AnalysisSpec,
                        scores: Mapping[str, AnnotationScores]) -> dict[str, Conclusion]:
    t = spec.data["scores"]["thresholds"]
    out = {}
    for pid, s in scores.items():
        parts = [
            threshold_conclusion("a_plus", s.a_plus, t["a_plus_min"], kind="at_least",
                                 sample="B", rule=f"A+ >= {t['a_plus_min']}",
                                 missing_reason=s.not_evaluable_reason),
            threshold_conclusion("a_minus", s.a_minus, t["a_minus_min"], kind="at_least",
                                 sample="B", rule=f"A- >= {t['a_minus_min']}",
                                 missing_reason=s.not_evaluable_reason),
        ]
        out[pid] = combine(f"annotation_adequacy::{pid}", parts,
                           "A+ and A- at or above their thresholds", "B")
    return out


def proximity_or_pending(registry: Registry,
                         proximity: Mapping[str, Conclusion] | None) -> dict[str, Conclusion]:
    out = {}
    for p in registry.primary:
        given = (proximity or {}).get(p.procedure_id)
        out[p.procedure_id] = given or Conclusion(
            f"human_proximity::{p.procedure_id}", None, "|beta_j - beta_HUMAN| <= 0.41", "R",
            NOT_EVALUABLE, DOWNSTREAM_PENDING)
    return out


# --------------------------------------------------------------------------
# pairs
# --------------------------------------------------------------------------


def kappa_exact(a: LabelVector, b: LabelVector | None, data: TaskLevelInput,
                members: Sequence[str]) -> tuple[Fraction | None, int]:
    """Kappa on the valid paired support, exactly; ``None`` when undefined."""

    pairs = []
    for i in members:
        x = a.label(i)
        y = data.items[i].human if b is None else b.label(i)
        if x is not None and y is not None:
            pairs.append((x, y))
    n = len(pairs)
    if n == 0:
        return None, 0
    po = Fraction(sum(x == y for x, y in pairs), n)
    px, py = Fraction(sum(x for x, _ in pairs), n), Fraction(sum(y for _, y in pairs), n)
    pe = px * py + (1 - px) * (1 - py)
    return (None if pe == 1 else (po - pe) / (1 - pe)), n


def noncorrespondence(a: LabelVector, b: LabelVector, data: TaskLevelInput,
                      members: Sequence[str]) -> dict[str, Any]:
    by_class = _classes(data, members)
    rates: dict[str, dict[str, Fraction | None]] = {}
    for c, name in ((1, "positive"), (0, "negative")):
        items = by_class[c]
        disagree = sum(1 for i in items if a.label(i) is not None and b.label(i) is not None
                       and a.label(i) != b.label(i))
        missing = sum(1 for i in items if a.label(i) is None or b.label(i) is None)
        n = len(items)
        rates[name] = {"total": Fraction(disagree + missing, n) if n else None,
                       "valid_disagreement": Fraction(disagree, n) if n else None,
                       "missingness": Fraction(missing, n) if n else None}
    balanced = {}
    for part in ("total", "valid_disagreement", "missingness"):
        p, q = rates["positive"][part], rates["negative"][part]
        balanced[part] = None if p is None or q is None else (p + q) / 2
    return {"by_class": rates, "balanced": balanced}


def pair_table(registry: Registry, vectors: Mapping[str, LabelVector], data: TaskLevelInput,
               members: Sequence[str]) -> list[dict[str, Any]]:
    """All 465 pairs of the 31 primary procedures, in a fixed order."""

    ids = sorted(p.procedure_id for p in registry.primary)
    out = []
    for x, y in combinations(ids, 2):
        nc = noncorrespondence(vectors[x], vectors[y], data, members)
        kappa, support = kappa_exact(vectors[x], vectors[y], data, members)
        out.append({"pair": (x, y), "noncorrespondence": nc, "kappa": kappa,
                    "kappa_support": support})
    return out


# --------------------------------------------------------------------------
# shared errors and corrections
# --------------------------------------------------------------------------


def error_groups(registry: Registry) -> dict[str, tuple[str, ...]]:
    cb = tuple(p.procedure_id for p in registry.primary_of_kind(KIND_CB))
    va = tuple(p.procedure_id for p in registry.primary_of_kind(KIND_VA_POST_S))
    return {"S_CB": cb, "S_VA": va, "S_ALL": cb + va}


def sufficiency_threshold(n_class: int, minimum) -> int:
    """Smallest shared-error count that rules out adequacy for every member."""

    return n_class - math.ceil(Fraction(minimum) * n_class) + 1


def shared_errors(spec: AnalysisSpec, registry: Registry, vectors: Mapping[str, LabelVector],
                  data: TaskLevelInput, members: Sequence[str]) -> dict[str, Any]:
    t = spec.data["scores"]["thresholds"]
    by_class = _classes(data, members)
    out = {}
    for group, ids in error_groups(registry).items():
        per_class = {}
        for c, name, minimum in ((1, "positive", t["a_plus_min"]),
                                 (0, "negative", t["a_minus_min"])):
            items, n = by_class[c], len(by_class[c])
            labels = [[vectors[pid].label(i) for pid in ids] for i in items]
            j = sum(1 for row in labels if all(v is not None for v in row))
            e = sum(1 for row in labels if all(v is not None and v != c for v in row))
            u = sum(1 for row in labels if all(v != c for v in row))
            threshold = sufficiency_threshold(n, minimum) if n else None
            per_class[name] = {
                "N": n, "J": j, "E": e, "U": u, "U_minus_E": u - e,
                "E_over_N": fraction_record(Fraction(e, n)) if n else None,
                "U_over_N": fraction_record(Fraction(u, n)) if n else None,
                "E_over_J": fraction_record(Fraction(e, j)) if j else None,
                "sufficiency_threshold": threshold,
                "E_sufficient_for_group_inadequacy": threshold is not None and e >= threshold,
                "U_sufficient_for_group_inadequacy": threshold is not None and u >= threshold,
            }
        out[group] = {
            "members": list(ids), "by_class": per_class,
            "note": ("Shared errors of the nine post-S VA configurations propagate through P "
                     "and M: G is also wrong on those campaigns." if group != "S_CB" else
                     "No implication for G is drawn from CB shared errors."),
        }
    return out


def directional_corrections(spec: AnalysisSpec, registry: Registry,
                            vectors: Mapping[str, LabelVector], data: TaskLevelInput,
                            members: Sequence[str]) -> dict[str, Any]:
    strong = spec.data["scores"]["thresholds"]["ba_margin_min"]
    by_class = _classes(data, members)
    n = {c: len(by_class[c]) for c in (1, 0)}
    ids = sorted(p.procedure_id for p in registry.primary_of_kind(KIND_VA_POST_S))

    def directed(k: str, j: str) -> dict[str, Any]:
        counts, support = {}, {}
        for c in (1, 0):
            both = [i for i in by_class[c]
                    if vectors[k].label(i) is not None and vectors[j].label(i) is not None]
            support[c] = len(both)
            counts[c] = sum(1 for i in both
                            if vectors[k].label(i) == c and vectors[j].label(i) != c)
        value = (Fraction(counts[1], n[1]) + Fraction(counts[0], n[0])) / 2 \
            if n[1] and n[0] else None
        return {"n_positive": counts[1], "n_negative": counts[0], "C": value,
                "valid_paired_support": {"positive": support[1], "negative": support[0]}}

    pairs = []
    for k, j in combinations(ids, 2):
        forward, backward = directed(k, j), directed(j, k)
        cf, cb = forward["C"], backward["C"]
        pairs.append({
            "pair": (k, j), f"{k}->{j}": forward, f"{j}->{k}": backward,
            "observed_correction": None if cf is None else (cf > 0 or cb > 0),
            "reciprocal": None if cf is None else (cf > 0 and cb > 0),
            "stronger_complementarity": None if cf is None else (
                at_least(cf, strong) and at_least(cb, strong)),
        })
    return {"n_pairs": len(pairs), "pairs": pairs,
            "any_observed": any(p["observed_correction"] for p in pairs),
            "any_reciprocal": any(p["reciprocal"] for p in pairs),
            "any_stronger": any(p["stronger_complementarity"] for p in pairs),
            "note": "Descriptive; none of these is an adoption gate."}


# --------------------------------------------------------------------------
# similarity, differences, overall adequacy
# --------------------------------------------------------------------------


def _pair_lookup(pairs: Sequence[Mapping[str, Any]]) -> dict[frozenset, Mapping[str, Any]]:
    return {frozenset(p["pair"]): p for p in pairs}


def _distance_conclusion(x: str, y: str, spec: AnalysisSpec,
                         distance: CoefficientDistance | None) -> Conclusion:
    limit = spec.data["scores"]["thresholds"]["coefficient_distance_max"]
    value = None if distance is None else distance(x, y)
    return threshold_conclusion(f"coefficient_distance::{x}|{y}", value, limit, kind="at_most",
                                sample="R", rule=f"|beta_x - beta_y| <= {limit}",
                                missing_reason=DOWNSTREAM_PENDING if distance is None
                                else "a fit is not usable")


def practical_similarity(spec: AnalysisSpec, adequacy: Mapping[str, Conclusion],
                         proximity: Mapping[str, Conclusion],
                         pairs: Sequence[Mapping[str, Any]],
                         distance: CoefficientDistance | None = None) -> Conclusion:
    """A2 over the entire group; no subgroup is ever chosen."""

    limit = spec.data["scores"]["thresholds"]["ba_margin_min"]
    rule = (f"all adequate and proximate procedures (>= 2): every pair with non-correspondence "
            f"< {limit} and coefficient distance <= "
            f"{spec.data['scores']['thresholds']['coefficient_distance_max']}")
    adequate = sorted(p for p, c in adequacy.items() if c.status == SATISFIED)
    if len(adequate) < 2:
        return Conclusion("A2_practical_similarity", {"adequate": adequate}, rule, "B and R",
                          NOT_SATISFIED, "fewer than two annotation-adequate procedures")
    known = [p for p in adequate if proximity[p].status == SATISFIED]
    unknown = [p for p in adequate if proximity[p].status == NOT_EVALUABLE]
    lookup = _pair_lookup(pairs)
    checks = []
    for x, y in combinations(known, 2):
        nc = lookup[frozenset((x, y))]["noncorrespondence"]["balanced"]["total"]
        checks.append(threshold_conclusion(f"noncorrespondence::{x}|{y}", nc, limit,
                                           kind="strictly_below", sample="B",
                                           rule=f"non-correspondence < {limit}"))
        checks.append(_distance_conclusion(x, y, spec, distance))
    value = {"adequate": adequate, "group_known_members": known, "proximity_unknown": unknown}
    failed = [c for c in checks if c.status == NOT_SATISFIED]
    if failed:
        return Conclusion("A2_practical_similarity", value, rule, "B and R", NOT_SATISFIED,
                          "a pair inside the group fails: " + failed[0].name)
    if unknown:
        return Conclusion("A2_practical_similarity", value, rule, "B and R", NOT_EVALUABLE,
                          "group membership depends on unavailable proximity evidence")
    if len(known) < 2:
        return Conclusion("A2_practical_similarity", value, rule, "B and R", NOT_SATISFIED,
                          "fewer than two adequate procedures within the proximity tolerance")
    result = combine("A2_practical_similarity", checks, rule, "B and R")
    return Conclusion(result.name, value, rule, "B and R", result.status, result.reason)


def differences(spec: AnalysisSpec, pairs: Sequence[Mapping[str, Any]],
                distance: CoefficientDistance | None = None) -> dict[str, Any]:
    t = spec.data["scores"]["thresholds"]
    annotation, downstream, unavailable = [], [], 0
    for p in pairs:
        x, y = p["pair"]
        nc = p["noncorrespondence"]["balanced"]
        if nc["total"] is not None and not strictly_below(nc["total"], t["ba_margin_min"]):
            annotation.append({"pair": [x, y], "noncorrespondence": fraction_record(nc["total"]),
                               "from_missingness": fraction_record(nc["missingness"])})
        value = None if distance is None else distance(x, y)
        if value is None:
            unavailable += 1
        elif not at_most(value, t["coefficient_distance_max"]):
            downstream.append({"pair": [x, y], "distance": value})
    return {"n_pairs": len(pairs), "annotation_differences": annotation,
            "downstream_differences": downstream, "downstream_distance_unavailable": unavailable,
            "note": "An unavailable or failed fit is not evidence of a substantive difference."}


def unresolved_differences(found: Mapping[str, Any],
                           preferences: Sequence[Conclusion]) -> Conclusion:
    rule = "no robust preference and at least one difference beyond the similarity criteria"
    statuses = [p.status for p in preferences]
    observed = bool(found["annotation_differences"] or found["downstream_differences"])
    value = {"preferences": {p.name: p.status for p in preferences},
             "n_annotation_differences": len(found["annotation_differences"]),
             "n_downstream_differences": len(found["downstream_differences"])}
    if SATISFIED in statuses:
        return Conclusion("A5_unresolved_differences", value, rule, "B and R", NOT_SATISFIED,
                          "a preference is established")
    if NOT_EVALUABLE in statuses:
        return Conclusion("A5_unresolved_differences", value, rule, "B and R", NOT_EVALUABLE,
                          "a preference is not evaluable")
    if observed:
        return Conclusion("A5_unresolved_differences", value, rule, "B and R", SATISFIED)
    if found["downstream_distance_unavailable"]:
        return Conclusion("A5_unresolved_differences", value, rule, "B and R", NOT_EVALUABLE,
                          "no annotation difference and downstream distances unavailable")
    return Conclusion("A5_unresolved_differences", value, rule, "B and R", NOT_SATISFIED,
                      "no difference beyond the similarity criteria")


def overall_adequacy(adequacy: Mapping[str, Conclusion],
                     proximity: Mapping[str, Conclusion]) -> dict[str, Any]:
    per = {pid: combine(f"overall_adequacy::{pid}", [adequacy[pid], proximity[pid]],
                        "annotation adequacy and HUMAN proximity", "B and R")
           for pid in adequacy}
    statuses = [c.status for c in per.values()]
    if SATISFIED in statuses:
        summary = "at_least_one_adequate"
    elif all(s == NOT_SATISFIED for s in statuses):
        summary = "none_adequate"
    else:
        summary = "unresolved"
    return {"per_procedure": per, "summary": summary}


# --------------------------------------------------------------------------
# evidence-to-framework table
# --------------------------------------------------------------------------

DOCUMENTARY_ROWS = {
    "B1_human_validation": "human-reference origin and individual coding evidence",
    "B2_downstream_sensitivity": "coefficients, distances, ranges, signs, intervals, H4 contrast",
    "B3_resources": "planned versus completed calls, retries, tokens, historical costs",
    "B4_inferential_stakes": "academic use and limits of the recommendation",
}


def evidence_table(*, leader: Comparator | None, adequacy: Mapping[str, Conclusion],
                   proximity: Mapping[str, Conclusion], standalone: Conclusion | None,
                   leave_one_out: Conclusion | None, g_id: str, g_margin_all_30: Conclusion,
                   g_omissions: Conclusion, similarity: Conclusion, corrections: Mapping[str, Any],
                   found_differences: Mapping[str, Any], shared: Mapping[str, Any],
                   overall: Mapping[str, Any]) -> dict[str, Conclusion]:
    """Rows of Tables 3.4A and 3.4B. A5 is derived here from A1 and A4."""

    rows: dict[str, Conclusion] = {}
    if leader is None:
        rows["A1_adequate_stable_leader"] = Conclusion(
            "A1_adequate_stable_leader", None, "leader criteria", "B and R", NOT_EVALUABLE,
            "no configuration with an evaluable BA")
    else:
        rows["A1_adequate_stable_leader"] = combine(
            "A1_adequate_stable_leader",
            [adequacy[leader.procedure_id], standalone, leave_one_out,
             proximity[leader.procedure_id]],
            "adequacy, margin >= 0.03, leave-one-out in every omission, HUMAN proximity",
            "B and R")
    rows["A2_adequate_similar_procedures"] = similarity
    rows["A3_compensating_errors"] = Conclusion(
        "A3_compensating_errors",
        {k: corrections[k] for k in ("any_observed", "any_reciprocal", "any_stronger")},
        "at least one observed directional correction (levels reported)", "B",
        SATISFIED if corrections["any_observed"] else NOT_SATISFIED,
        None if corrections["any_observed"] else "no directional correction observed")
    rows["A4_adequate_advantageous_aggregate"] = combine(
        "A4_adequate_advantageous_aggregate",
        [adequacy[g_id], g_margin_all_30, g_omissions, proximity[g_id]],
        "adequacy, margin over the best of 30 >= 0.03, six omissions, HUMAN proximity",
        "B and R")
    rows["A5_unresolved_differences"] = unresolved_differences(
        found_differences, [rows["A1_adequate_stable_leader"],
                            rows["A4_adequate_advantageous_aggregate"]])
    sufficient = [g for g, v in shared.items()
                  for c in v["by_class"].values()
                  if c["E_sufficient_for_group_inadequacy"] or c["U_sufficient_for_group_inadequacy"]]
    if sufficient or overall["summary"] == "none_adequate":
        a6 = Conclusion("A6_shared_errors_or_none_adequate",
                        {"groups_with_sufficient_shared_failure": sorted(set(sufficient)),
                         "overall": overall["summary"]},
                        "shared failures sufficient for group inadequacy, or no adequate procedure",
                        "B and R", SATISFIED)
    elif overall["summary"] == "unresolved":
        a6 = Conclusion("A6_shared_errors_or_none_adequate", {"overall": overall["summary"]},
                        "shared failures or no adequate procedure", "B and R", NOT_EVALUABLE,
                        "overall adequacy unresolved and no sufficient shared failure")
    else:
        a6 = Conclusion("A6_shared_errors_or_none_adequate", {"overall": overall["summary"]},
                        "shared failures or no adequate procedure", "B and R", NOT_SATISFIED,
                        "an adequate procedure exists and no group has sufficient shared failure")
    rows["A6_shared_errors_or_none_adequate"] = a6
    for name, evidence in DOCUMENTARY_ROWS.items():
        rows[name] = Conclusion(name, None, f"documentary evidence: {evidence}", "documents",
                                NOT_EVALUABLE, "assembled at the reporting stage (Table 3.4B)")
    return rows


__all__ = [
    "DOCUMENTARY_ROWS",
    "DOWNSTREAM_PENDING",
    "annotation_adequacy",
    "differences",
    "directional_corrections",
    "error_groups",
    "evidence_table",
    "kappa_exact",
    "noncorrespondence",
    "overall_adequacy",
    "pair_table",
    "practical_similarity",
    "proximity_or_pending",
    "shared_errors",
    "sufficiency_threshold",
    "unresolved_differences",
]
