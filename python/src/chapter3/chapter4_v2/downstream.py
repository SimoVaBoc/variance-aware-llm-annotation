"""Common downstream design on R, pre-fit checks and the separation diagnostic.

Python never estimates a regression here. It builds the one design every Firth
fit shares, checks it, and hands it to the R adapter (:mod:`.firth`):

    success ~ LABEL + lgoal + C(subcategory) + C(year), with intercept, on R.

* ``lgoal`` is the supplied field, as validated at the input boundary; it is
  not re-logged or rescaled.
* Subcategory and year levels are those observed on R, sorted as strings (code
  point order), the first being the reference. The control columns are built
  once and reused unchanged for every fit; only the LABEL column changes.
* Nothing is dropped: R is fixed before any fit, every value is checked finite
  first, and a formula library never sees the data.

Pre-fit checks, in order: both success classes, LABEL variation, N > p, full
rank. Rank uses the SVD of the full design in double precision with tolerance
``max(N, p) * eps * s_max``.

Separation (complete or quasi-complete) is diagnosed by linear programming on
``Z = diag(2y - 1) X`` with each coefficient direction boxed in [-1, 1]
(proposed D-FIRTH-04):

* separation exists if ``max sum(Z b)`` subject to ``Z b >= 0`` is positive;
* it is complete if ``max t`` subject to ``Z b >= t`` is positive;
* coefficient j would diverge without penalisation if ``b_j`` can be non-zero
  inside the cone ``Z b >= 0``.

Separation is recorded, never treated as a Firth failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linprog

from .inputs import TaskLevelInput

#: Optima below this are treated as zero in the separation programs (proposed D-FIRTH-04).
SEPARATION_TOLERANCE = 1e-7

REASON_OUTCOME_ONE_CLASS = "success_has_one_class"
REASON_LABEL_CONSTANT = "label_has_no_variation"
REASON_N_NOT_ABOVE_P = "n_not_greater_than_p"
REASON_RANK_DEFICIENT = "design_not_full_rank"


class DesignError(ValueError):
    """The fixed sample R cannot carry the common design."""


@dataclass(frozen=True)
class CommonDesign:
    items: tuple[str, ...]
    y: np.ndarray
    controls: np.ndarray
    control_names: tuple[str, ...]
    levels: Mapping[str, tuple[str, ...]]

    @property
    def n(self) -> int:
        return len(self.items)

    @property
    def p(self) -> int:
        return 2 + self.controls.shape[1]

    @property
    def column_names(self) -> tuple[str, ...]:
        return ("(Intercept)", "LABEL") + self.control_names

    def matrix(self, label: np.ndarray) -> np.ndarray:
        label = np.asarray(label, dtype=float).reshape(-1, 1)
        return np.hstack([np.ones((self.n, 1)), label, self.controls])

    def describe(self) -> dict[str, Any]:
        return {"n": self.n, "p": self.p, "columns": list(self.column_names),
                "reference_levels": {k: v[0] for k, v in self.levels.items() if v},
                "levels": {k: list(v) for k, v in self.levels.items()},
                "successes": int(self.y.sum()), "failures": int(self.n - self.y.sum())}


def build_common_design(data: TaskLevelInput, r_members: Sequence[str]) -> CommonDesign:
    items = tuple(sorted(r_members))
    if not items:
        raise DesignError("R is empty; the downstream comparison is not evaluable")
    problems = []
    for item in items:
        record = data.items[item]
        if record.success not in (0, 1) or record.lgoal is None or record.subcategory is None \
                or record.year is None:
            problems.append(f"{item}: incomplete covariates")
        elif not np.isfinite(record.lgoal):
            problems.append(f"{item}: lgoal is not finite")
    if problems:
        raise DesignError("R contains items the design cannot use: " + "; ".join(problems[:5]))

    y = np.array([data.items[i].success for i in items], dtype=np.int64)
    columns, names = [np.array([data.items[i].lgoal for i in items], dtype=float)], ["lgoal"]
    levels: dict[str, tuple[str, ...]] = {}
    for factor in ("subcategory", "year"):
        values = [str(getattr(data.items[i], factor)) for i in items]
        observed = tuple(sorted(set(values)))
        levels[factor] = observed
        for level in observed[1:]:
            columns.append(np.array([v == level for v in values], dtype=float))
            names.append(f"{factor}[{level}]")
    controls = np.column_stack(columns)
    if not np.isfinite(controls).all():
        raise DesignError("the control matrix has non-finite values")
    return CommonDesign(items, y, controls, tuple(names), levels)


def rank_check(x: np.ndarray) -> dict[str, Any]:
    singular = np.linalg.svd(np.asarray(x, dtype=np.float64), compute_uv=False)
    n, p = x.shape
    s_max = float(singular.max()) if singular.size else 0.0
    tolerance = max(n, p) * np.finfo(np.float64).eps * s_max
    rank = int((singular > tolerance).sum())
    return {"rank": rank, "p": p, "full_rank": rank == p, "tolerance": tolerance,
            "s_max": s_max, "s_min": float(singular.min()) if singular.size else 0.0}


def prefit_checks(design: CommonDesign, label: np.ndarray) -> dict[str, Any]:
    label = np.asarray(label)
    failures = []
    if len(set(design.y.tolist())) < 2:
        failures.append(REASON_OUTCOME_ONE_CLASS)
    if len(set(label.tolist())) < 2:
        failures.append(REASON_LABEL_CONSTANT)
    if not design.n > design.p:
        failures.append(REASON_N_NOT_ABOVE_P)
    rank = rank_check(design.matrix(label))
    if not rank["full_rank"]:
        failures.append(REASON_RANK_DEFICIENT)
    return {"failures": failures, "estimable": not failures, "rank": rank,
            "n": design.n, "p": design.p}


def _lp(c, a_ub, b_ub, bounds) -> float:
    result = linprog(c, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if result.status != 0:
        raise RuntimeError(f"separation program did not solve: {result.message}")
    return float(-result.fun)


def separation_diagnostic(x: np.ndarray, y: np.ndarray,
                          tolerance: float = SEPARATION_TOLERANCE) -> dict[str, Any]:
    x = np.asarray(x, dtype=float)
    z = x * (2 * np.asarray(y, dtype=float) - 1)[:, None]
    n, p = z.shape
    box = [(-1.0, 1.0)] * p
    cone = (-z, np.zeros(n))
    any_value = _lp(-z.sum(axis=0), *cone, box)
    # Complete separation: maximise t with Z b >= t, t in [0, 1].
    a = np.hstack([-z, np.ones((n, 1))])
    complete_value = _lp(np.r_[np.zeros(p), -1.0], a, np.zeros(n), box + [(0.0, 1.0)])
    diverging = []
    if any_value > tolerance:
        for j in range(p):
            unit = np.zeros(p)
            unit[j] = 1.0
            if max(_lp(-unit, *cone, box), _lp(unit, *cone, box)) > tolerance:
                diverging.append(j)
    separated = any_value > tolerance
    return {
        "separation": ("complete" if complete_value > tolerance else "quasi_complete")
        if separated else "none",
        "objective_any": any_value, "objective_complete": complete_value,
        "diverging_columns": diverging, "tolerance": tolerance,
        "method": "LP on Z = diag(2y-1) X with coefficients boxed in [-1, 1] (HiGHS)",
        "note": "Recorded only; separation is not a Firth failure.",
    }


@dataclass
class LabelSet:
    """The 35 LABEL columns, in registry order, on the items of the design."""

    names: list[str] = field(default_factory=list)
    values: dict[str, np.ndarray] = field(default_factory=dict)


def label_set(design: CommonDesign, data: TaskLevelInput, vectors: Mapping[str, Any],
              procedure_ids: Sequence[str], human_name: str = "HUMAN") -> LabelSet:
    labels = LabelSet()
    human = np.array([data.items[i].human for i in design.items], dtype=np.int64)
    labels.names.append(human_name)
    labels.values[human_name] = human
    for pid in procedure_ids:
        values = [vectors[pid].label(i) for i in design.items]
        if any(v is None for v in values):
            raise DesignError(f"{pid} has a missing label on R; R must exclude it")
        labels.names.append(pid)
        labels.values[pid] = np.array(values, dtype=np.int64)
    return labels


__all__ = [
    "REASON_LABEL_CONSTANT",
    "REASON_N_NOT_ABOVE_P",
    "REASON_OUTCOME_ONE_CLASS",
    "REASON_RANK_DEFICIENT",
    "SEPARATION_TOLERANCE",
    "CommonDesign",
    "DesignError",
    "LabelSet",
    "build_common_design",
    "label_set",
    "prefit_checks",
    "rank_check",
    "separation_diagnostic",
]
