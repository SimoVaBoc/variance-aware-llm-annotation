"""Report assembly: an output catalogue keyed to analysis IDs, tiers, and pending modules.

Every output is labelled by the analysis identifiers it serves (A1-A6, B1-B4, H1-H4,
E1), never by a chapter or section number, so the labels survive any change of
chapter structure (D-CH4-STRUCT is only a proposal). Each output carries an
``output_tier``: ``main`` or ``appendix``. The tier follows SRC-BRIEF §10 where §10
says so (coverage, essential performance profiles, the three G margins, downstream
coefficients and diagnostics, concise H1-H4/E1 and the evidence-to-framework table
in the main report; all 465 pairs, extended matrices, full coefficients and
technical details in appendices); where §10 does not settle it, the basis says
"proposed".

The pending-status table keeps undecided modules visible with the decision they
wait on, and what is shown instead. A missing result is never rendered as zero,
a failed hypothesis or a passed criterion.

Nothing here computes an analysis; it only arranges results already computed.
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from .samples import SampleMembership
from .scores import fraction_record
from .spec import AnalysisSpec
from .thresholds import Conclusion

ANALYSIS_IDS = ("A1", "A2", "A3", "A4", "A5", "A6", "B1", "B2", "B3", "B4",
                "H1", "H2", "H3", "H4", "E1")
TIERS = ("main", "appendix")
A_ROWS = ("A1", "A2", "A3", "A4", "A5", "A6")
B_ROWS = ("B1", "B2", "B3", "B4")
BRIEF = "SRC-BRIEF §10"

#: (output_id, analysis IDs, tier, basis)
CATALOGUE: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("samples_and_coverage", A_ROWS + ("H3",), "main", f"{BRIEF}: coverage"),
    ("planned_benchmark_check", A_ROWS, "main", f"{BRIEF}: coverage; D-SAMP-02"),
    ("performance_profiles_B", ("A1", "A2", "A4", "A6"), "main",
     f"{BRIEF}: essential performance profiles"),
    ("annotation_adequacy", ("A1", "A2", "A4", "A6"), "main",
     f"{BRIEF}: evidence-to-framework table"),
    ("g_margins", ("A4",), "main", f"{BRIEF}: three G margins"),
    ("framework_bootstrap_intervals", ("A1", "A4"), "main",
     "SRC-MAP R2: three margins with the specified bootstrap intervals"),
    ("standalone_leader", ("A1",), "main", f"{BRIEF}: evidence-to-framework table"),
    ("robustness_minima", ("A1", "A4"), "main",
     "SRC-MAP R2: six and 250 checks with minimum margins and status"),
    ("g_omission_perturbations", ("A4",), "appendix", f"{BRIEF}: technical details"),
    ("leave_one_out_perturbations", ("A1",), "appendix", f"{BRIEF}: technical details"),
    ("shared_errors", ("A6",), "main",
     "proposed: SRC-CRITERIA lists the three-group table as a Chapter 4 product; §10 is silent"),
    ("directional_corrections", ("A3",), "appendix", f"{BRIEF}: extended matrices"),
    ("pairwise_465", ("A2", "A5"), "appendix", f"{BRIEF}: all 465 pairs"),
    ("kappa_vs_human", ("A1", "A4"), "appendix",
     "proposed: complementary measure, no adoption threshold; §10 is silent"),
    ("missing_by_procedure", A_ROWS, "appendix", f"{BRIEF}: technical details; D-SAMP-02"),
    ("evidence_to_framework_table", A_ROWS + B_ROWS, "main",
     f"{BRIEF}: evidence-to-framework table"),
    ("downstream_summary", ("B2", "A1", "A4"), "main",
     f"{BRIEF}: downstream coefficients and diagnostics"),
    ("downstream_full_fits", ("B2",), "appendix", f"{BRIEF}: full coefficients"),
    ("h1_cells", ("H1",), "main", f"{BRIEF}: concise H1-H4/E1"),
    ("h2_main_table", ("H2",), "main", f"{BRIEF}: concise H1-H4/E1"),
    ("h2_audit", ("H2",), "appendix", "proposed: SRC-H2 §10 audit table or appendix"),
    ("h3_point_contrast", ("H3",), "main", f"{BRIEF}: concise H1-H4/E1"),
    ("h3_component_ba", ("H3",), "appendix", f"{BRIEF}: technical details"),
    ("h4_dispersion", ("H4",), "main", f"{BRIEF}: concise H1-H4/E1"),
    ("e1_points", ("E1",), "main", f"{BRIEF}: concise H1-H4/E1"),
    ("pending_status_table", ANALYSIS_IDS, "main", f"{BRIEF}: mark pending modules visibly"),
    ("bootstrap_draws", ("A1", "A4"), "appendix", f"{BRIEF}: technical details"),
)

#: Modules or policies kept visible while their decision is open.
PENDING_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("H3 inference", "H3", "D-H3-02",
     "Point contrast only; the inference entry refuses to run."),
    ("H2 temporal sensitivity (W <= 300 s)", "H2", "D-H2-02", "Not run."),
    ("H2 appendix bootstrap and temporal Holm family", "H2", "D-H2-03", "Not run."),
    ("H2 P-S ANOVA candidate", "H2", "D-H2-05", "Outside the primary plan; not run."),
    ("Incomplete H2 Holm family", "H2", "D-H2-04",
     "Family reported as incomplete; no adjusted p-values are produced."),
    ("Firth convergence under the specified controls", "B2", "D-FIRTH-03",
     "Fits that do not certify are reported as failed; dependent conditions are not evaluable."),
)


def to_jsonable(value: Any, data: Any = None) -> Any:
    """JSON-ready copy: exact fractions as records, conclusions and samples as records."""

    if isinstance(value, Fraction):
        return fraction_record(value)
    if isinstance(value, Conclusion):
        return value.as_record()
    if isinstance(value, SampleMembership):
        return value.as_record(data)
    if hasattr(value, "as_record") and callable(value.as_record):
        try:
            return to_jsonable(value.as_record(), data)
        except TypeError:
            return to_jsonable(value.as_record(data), data)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name), data)
                for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v, data) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v, data) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(to_jsonable(v, data) for v in value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(value.item):  # numpy scalar
        return value.item()
    if hasattr(value, "tolist") and callable(value.tolist):  # numpy array
        return value.tolist()
    return value


def pending_status_table(spec: AnalysisSpec, register: Mapping[str, Any]) -> list[dict[str, Any]]:
    decisions = {d["id"]: d for d in register["decisions"]}
    rows = []
    for item, analysis_id, decision_id, shown in PENDING_ROWS:
        decision = decisions[decision_id]
        rows.append({"item": item, "analysis_id": analysis_id, "decision_id": decision_id,
                     "decision_status": decision["status"],
                     "implementation_status": decision["implementation_status"],
                     "shown_instead": shown})
    return rows


def awaiting_confirmation(register: Mapping[str, Any]) -> list[dict[str, str]]:
    """Proposed working rules in use, listed so a reader sees what is not yet adopted."""

    return [{"decision_id": d["id"], "title": d["title"], "status": d["status"]}
            for d in register["decisions"] if d["status"] == "proposed"]


def _entry(output_id: str, content: Any, data_kind: str) -> dict[str, Any]:
    _, analysis_ids, tier, basis = next(c for c in CATALOGUE if c[0] == output_id)
    return {"output_id": output_id, "analysis_ids": list(analysis_ids), "output_tier": tier,
            "tier_basis": basis, "data_kind": data_kind, "content": content}


def _not_run(reason: str) -> dict[str, str]:
    return {"status": "not_run", "reason": reason}


def build_report(spec: AnalysisSpec, register: Mapping[str, Any], data: Any,
                 framework: Mapping[str, Any], h1: Mapping[str, Any], h2: Mapping[str, Any],
                 h3: Mapping[str, Any], downstream: Any = None,
                 h4: Mapping[str, Any] | None = None, e1: Mapping[str, Any] | None = None,
                 downstream_reason: str | None = None) -> dict[str, Any]:
    """Arrange computed results into catalogue entries. Computes nothing new."""

    kind = data.data_kind
    j = lambda v: to_jsonable(v, data)  # noqa: E731
    boot = framework.get("bootstrap") or {}
    loo = framework.get("leave_one_out") or {}
    omissions = framework.get("g_omissions") or {}
    no_downstream = downstream_reason or "downstream evidence not supplied"
    contents = {
        "samples_and_coverage": j(framework["samples"]),
        "planned_benchmark_check": j(framework["planned_benchmark_check"]),
        "performance_profiles_B": j(framework["scores_B"]),
        "annotation_adequacy": j(framework["adequacy"]),
        "g_margins": j(framework["g_margins"]),
        "framework_bootstrap_intervals": j({"procedures": boot.get("procedures"),
                                            "margins": boot.get("margins")}) if boot
        else _not_run("bootstrap not requested"),
        "standalone_leader": j({"leader": framework["standalone_leader"],
                                "margin": framework["standalone_margin"]}),
        "robustness_minima": j({
            "g_six_omissions": {k: omissions.get(k) for k in
                                ("conclusion", "n_perturbations", "n_satisfied", "minimum_margin")},
            "leave_one_out": {k: loo.get(k) for k in
                              ("candidate", "conclusion", "n_perturbations", "n_satisfied",
                               "minimum_margin")}}),
        "g_omission_perturbations": j(omissions.get("perturbations")),
        "leave_one_out_perturbations": j(loo.get("perturbations")),
        "shared_errors": j(framework["shared_errors"]),
        "directional_corrections": j(framework["directional_corrections"]),
        "pairwise_465": j(framework["pairs"]),
        "kappa_vs_human": j(framework["kappa_vs_human_B"]),
        "missing_by_procedure": j(framework["missing_by_procedure_B"]),
        "evidence_to_framework_table": j(framework["evidence_table"]),
        "downstream_summary": j({
            "environment": downstream.environment,
            "design": downstream.design.describe(),
            "fits": {name: {k: f.as_record()[k] for k in
                            ("status", "reasons", "label_coefficient", "label_ci")}
                     for name, f in downstream.fits.items()},
            "proximity": framework["proximity"]}) if downstream is not None
        else _not_run(no_downstream),
        "downstream_full_fits": j({n: f.as_record() for n, f in downstream.fits.items()})
        if downstream is not None else _not_run(no_downstream),
        "h1_cells": j(h1),
        "h2_main_table": j([{k: t.get(k) for k in
                             ("model_key", "status", "N", "N_Q", "within_prompt_rate",
                              "between_prompt_rate", "Q_m", "p_value", "holm_adjusted_p", "flag",
                              "reason")} for t in h2["tests"]] + [{"holm_family":
                                                                   h2["holm_family"]}]),
        "h2_audit": j([{k: t.get(k) for k in ("model_key", "strata", "class_composition",
                                               "six_Q_m")} for t in h2["tests"]]),
        "h3_point_contrast": j({k: v for k, v in h3.items() if k != "component_ba"}),
        "h3_component_ba": j(h3.get("component_ba")),
        "h4_dispersion": j(h4) if h4 is not None else _not_run(no_downstream),
        "e1_points": j(e1) if e1 is not None else _not_run(no_downstream),
        "pending_status_table": pending_status_table(spec, register),
        "bootstrap_draws": j(boot.get("draws")) if boot else _not_run("bootstrap not requested"),
    }
    missing = [c[0] for c in CATALOGUE if c[0] not in contents]
    if missing:
        raise AssertionError(f"catalogue entries without content: {missing}")
    return {
        "header": j(framework["header"]),
        "data_kind": kind,
        "labels": "Outputs are keyed to analysis IDs (A1-A6, B1-B4, H1-H4, E1), never to "
                  "chapter or section numbers.",
        "pending_status_table": contents["pending_status_table"],
        "proposed_working_rules": awaiting_confirmation(register),
        "outputs": [_entry(output_id, contents[output_id], kind) for output_id, *_ in CATALOGUE],
    }


__all__ = [
    "ANALYSIS_IDS",
    "CATALOGUE",
    "PENDING_ROWS",
    "TIERS",
    "awaiting_confirmation",
    "build_report",
    "pending_status_table",
    "to_jsonable",
]
