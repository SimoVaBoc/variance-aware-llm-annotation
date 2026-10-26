"""Load, validate and identify the machine-readable analysis specification.

The specification is the single source of the plan's constants. Code reads
thresholds, counts and controls from it instead of restating them, and every
analysis output carries the specification's ID, version and SHA-256 so a result
can always be traced to the exact plan that produced it.

Validation checks the plan's internal arithmetic rather than trusting it: the
procedure counts must follow from the design, the minimum correct counts and
the shared-error sufficiency counts must follow from the thresholds and the
planned class sizes, and no module may be enabled while its decision is
pending. Thresholds are decimal strings, compared as exact fractions, so an
on-the-boundary value is never misclassified by floating-point rounding.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from ..design import canonical_json_hash

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SPEC_PATH = PROJECT_ROOT / "config/analysis/chapter4_analysis_spec_v2.json"

REQUIRED_SECTIONS = (
    "spec_id", "spec_version", "decision_register", "sources", "design", "procedures",
    "aggregation", "samples", "scores", "comparisons", "kappa", "framework_bootstrap",
    "robustness", "framework", "downstream", "modules", "reporting", "open_decision_ids",
)

#: The numeric thresholds, stored as decimal strings and read as exact fractions.
THRESHOLD_KEYS = ("a_plus_min", "a_minus_min", "ba_margin_min", "coefficient_distance_max")

#: Statuses a module may carry, and whether each allows ``enabled: true``.
MODULE_STATUSES = {
    "confirmed": True,
    "decision_pending": False,
    "outside_primary_plan": False,
}


class SpecError(ValueError):
    """The specification is incomplete or internally inconsistent."""


def exact(value: str | int) -> Fraction:
    """A threshold as an exact fraction. Floats are refused: they are already rounded."""

    if isinstance(value, float):
        raise SpecError(f"threshold {value!r} must be a decimal string, not a float")
    return Fraction(value)


@dataclass(frozen=True)
class AnalysisSpec:
    """A validated specification together with its identity."""

    data: Mapping[str, Any]
    sha256: str
    path: str | None = None

    @property
    def spec_id(self) -> str:
        return str(self.data["spec_id"])

    @property
    def version(self) -> str:
        return str(self.data["spec_version"])

    def identity(self) -> dict[str, str]:
        """What every output records about the plan that produced it."""

        return {"spec_id": self.spec_id, "spec_version": self.version, "spec_sha256": self.sha256}

    def threshold(self, name: str) -> Fraction:
        return exact(self.data["scores"]["thresholds"][name])

    @property
    def model_keys(self) -> tuple[str, ...]:
        return tuple(m["model_key"] for m in self.data["design"]["models"])

    @property
    def cb_template_ids(self) -> tuple[str, ...]:
        return tuple(t["template_id"] for t in self.data["design"]["cb_templates"])

    @property
    def va_template_ids(self) -> tuple[str, ...]:
        return tuple(t["template_id"] for t in self.data["design"]["va_templates"])

    @property
    def va_generations(self) -> int:
        return int(self.data["design"]["va_generations_per_cell"])

    def module(self, name: str) -> Mapping[str, Any]:
        return self.data["modules"][name]

    def module_enabled(self, name: str) -> bool:
        return bool(self.data["modules"][name]["enabled"])


def spec_problems(data: Mapping[str, Any]) -> list[str]:
    """Every inconsistency found, so a broken specification is reported in full."""

    problems = [f"missing section {key!r}" for key in REQUIRED_SECTIONS if key not in data]
    if problems:
        return problems

    design = data["design"]
    models = [m.get("model_key") for m in design["models"]]
    cb = [t.get("template_id") for t in design["cb_templates"]]
    va = [t.get("template_id") for t in design["va_templates"]]
    for name, ids in (("model_key", models), ("cb template_id", cb), ("va template_id", va)):
        if any(not i for i in ids):
            problems.append(f"every {name} must be non-empty")
        if len(ids) != len(set(ids)):
            problems.append(f"duplicate {name}")
    if set(cb) & set(va):
        problems.append("a template_id is assigned to both arms")

    s = design.get("va_generations_per_cell")
    if design.get("cb_generations_per_configuration") != 1:
        problems.append("CB configurations use exactly one designated generation")

    counts = data["procedures"]["primary_counts"]
    implied = {"cb": len(models) * len(cb), "va_post_s": len(models) * len(va), "g": 1}
    implied["total"] = sum(implied.values())
    for key, value in implied.items():
        if counts.get(key) != value:
            problems.append(f"primary_counts.{key} is {counts.get(key)!r}; the design implies {value}")
    if data["procedures"].get("h3_component_count") != len(models) * len(va) * (s or 0):
        problems.append("h3_component_count does not equal models x prompts x generations")
    if data["procedures"].get("h4_within_model_count") != len(models):
        problems.append("h4_within_model_count does not equal the number of models")
    if data["procedures"].get("deduplicate_coincident_vectors") is not False:
        problems.append("coincident procedure vectors must never be deduplicated")

    aggregation = data["aggregation"]
    if aggregation.get("va_post_s_required_valid_generations") != s:
        problems.append("a VA configuration must require all of its planned generations")
    if aggregation.get("g_required_valid_calls") != len(models) * len(va) * (s or 0):
        problems.append("G must require every planned VA call")
    if aggregation.get("pooled_majority_as_primary") is not False:
        problems.append("pooled majority cannot be the primary aggregation")

    bench = design["benchmark"]
    n_pos, n_neg = bench["planned_human_positives"], bench["planned_human_negatives"]
    if n_pos + n_neg != bench["planned_n_items"]:
        problems.append("planned class sizes do not add up to the planned benchmark")
    declared_thresholds = data["scores"]["thresholds"]
    missing = [k for k in THRESHOLD_KEYS if k not in declared_thresholds]
    if missing:
        return problems + [f"missing thresholds {missing}"]
    try:
        thresholds = {k: exact(declared_thresholds[k]) for k in THRESHOLD_KEYS}
    except (SpecError, ValueError) as error:
        return problems + [str(error)]
    min_pos = math.ceil(thresholds["a_plus_min"] * n_pos)
    min_neg = math.ceil(thresholds["a_minus_min"] * n_neg)
    declared = data["scores"]["planned_min_correct"]
    if (declared.get("positives"), declared.get("negatives")) != (min_pos, min_neg):
        problems.append(f"planned_min_correct must be ({min_pos}, {min_neg}) from the thresholds")
    sufficiency = data["scores"]["shared_error_sufficiency"]
    if (sufficiency.get("positives"), sufficiency.get("negatives")) != (
            n_pos - min_pos + 1, n_neg - min_neg + 1):
        problems.append("shared_error_sufficiency must equal the error budget plus one")

    boot = data["framework_bootstrap"]
    if boot.get("n_resamples") != 10000 or boot.get("seed") != 20261024:
        problems.append("framework bootstrap must use 10,000 resamples and seed 20261024")
    if [exact(q) for q in boot["interval"]["quantiles"]] != [Fraction(1, 40), Fraction(39, 40)]:
        problems.append("framework bootstrap quantiles must be 0.025 and 0.975")
    if boot.get("draw_order") != ["positives", "negatives"]:
        problems.append("framework bootstrap draws positives before negatives")

    fits = data["downstream"]["fits"]
    if fits.get("primary_procedures") != implied["total"] or fits.get("total") != (
            implied["total"] + 1 + len(models)):
        problems.append("downstream fit counts do not follow from the procedure registry")
    if data["downstream"]["estimator"].get("fallback") is not None:
        problems.append("the Firth estimator has no fallback")

    open_ids = set(data["open_decision_ids"])
    for name, module in data["modules"].items():
        status = module.get("methodological_status")
        if status not in MODULE_STATUSES:
            problems.append(f"module {name!r} has unknown status {status!r}")
            continue
        if module.get("enabled") and not MODULE_STATUSES[status]:
            problems.append(f"module {name!r} is enabled while its status is {status!r}")
        if status == "decision_pending" and not set(module.get("decision_ids", ())) & open_ids:
            problems.append(f"pending module {name!r} names no open decision")
    return problems


def validate_spec(data: Mapping[str, Any]) -> None:
    problems = spec_problems(data)
    if problems:
        raise SpecError("Invalid analysis specification:\n- " + "\n- ".join(problems))


def spec_from_mapping(data: Mapping[str, Any], path: str | None = None) -> AnalysisSpec:
    validate_spec(data)
    return AnalysisSpec(data=data, sha256=canonical_json_hash(data), path=path)


def load_spec(path: str | Path = DEFAULT_SPEC_PATH) -> AnalysisSpec:
    spec_path = Path(path)
    with spec_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return spec_from_mapping(data, path=str(spec_path))


__all__ = [
    "DEFAULT_SPEC_PATH",
    "AnalysisSpec",
    "SpecError",
    "exact",
    "load_spec",
    "spec_from_mapping",
    "spec_problems",
    "validate_spec",
]
