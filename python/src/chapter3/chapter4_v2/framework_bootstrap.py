"""Paired, HUMAN-stratified campaign bootstrap for the framework annotation measures.

The resampling unit is the campaign, carrying every label and every missing
output it has. Each replication draws, with replacement and within class, as
many positives and negatives as B has, so class sizes are fixed and campaign
multiplicities are kept.

The random stream is specified, not incidental:

* generator ``numpy.random.Generator(numpy.random.PCG64(seed))``;
* positives and negatives each in ascending lexicographic ``item_id`` order;
* for each replication in turn, ``integers(0, n_pos, size=n_pos)`` for the
  positives, then ``integers(0, n_neg, size=n_neg)`` for the negatives.

The loop is written out on purpose. Drawing all replications at once would
consume the stream in a different order; the SHA-256 of the saved index matrix
changes with it, so such a change cannot pass unnoticed.

Statistics are evaluated on the weights the indices imply. Comparators are held
at their original identities, so margin intervals are conditional on that
choice. A two-sided percentile interval (``numpy.quantile``, linear
interpolation) is published only when every replicate is defined; otherwise
the defined share is reported and the interval is unavailable. Kappa uses the
historical ``kappa_from_counts`` on the declared valid paired support and is
never set to 1 when undefined.

Decisions use point estimates; nothing here carries a status.
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..bootstrap import kappa_from_counts
from .aggregation import LabelVector
from .comparisons import Comparator
from .inputs import TaskLevelInput
from .scores import fraction_record
from .spec import AnalysisSpec

GENERATOR = "numpy.random.Generator(numpy.random.PCG64(seed))"
DRAW_ORDER = ("for each replication: integers(0, n_pos, size=n_pos) over positives, then "
              "integers(0, n_neg, size=n_neg) over negatives; each class in ascending "
              "lexicographic item_id order")


class BootstrapError(RuntimeError):
    """The bootstrap cannot run as specified."""


@dataclass(frozen=True)
class BootstrapDraws:
    """The resample indices and everything needed to reproduce them."""

    item_order: tuple[str, ...]
    n_positive: int
    n_negative: int
    indices: np.ndarray
    seed: int

    @property
    def n_replications(self) -> int:
        return int(self.indices.shape[0])

    def sha256(self) -> str:
        data = np.ascontiguousarray(self.indices, dtype="<i8").tobytes()
        return hashlib.sha256(data).hexdigest()

    def weights(self) -> np.ndarray:
        """How often each campaign is drawn in each replication."""

        n = len(self.item_order)
        rows = np.arange(self.n_replications, dtype=np.int64)[:, None] * n
        counts = np.bincount((rows + self.indices).ravel(), minlength=self.n_replications * n)
        return counts.reshape(self.n_replications, n)

    def metadata(self) -> dict[str, Any]:
        return {
            "generator": GENERATOR, "seed": self.seed, "draw_order": DRAW_ORDER,
            "n_replications": self.n_replications, "n_positive": self.n_positive,
            "n_negative": self.n_negative, "item_order": list(self.item_order),
            "indices_dtype": "<i8", "indices_shape": list(self.indices.shape),
            "indices_sha256": self.sha256(),
            "software": {"python": platform.python_version(), "numpy": np.__version__},
        }

    def save(self, directory: str | Path) -> dict[str, Any]:
        """Write the index matrix and its metadata. Existing files are never replaced."""

        directory = Path(directory)
        npy, meta = directory / "bootstrap_indices.npy", directory / "bootstrap_draws.json"
        for path in (npy, meta):
            if path.exists():
                raise BootstrapError(f"refusing to overwrite {path}")
        directory.mkdir(parents=True, exist_ok=True)
        np.save(npy, np.ascontiguousarray(self.indices, dtype="<i8"), allow_pickle=False)
        record = {**self.metadata(), "indices_file": npy.name,
                  "indices_file_sha256": hashlib.sha256(npy.read_bytes()).hexdigest()}
        meta.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record


def draw_stratified(positives: Sequence[str], negatives: Sequence[str], seed: int,
                    n_replications: int) -> BootstrapDraws:
    if not positives or not negatives:
        raise BootstrapError("the stratified bootstrap needs both HUMAN classes")
    pos, neg = sorted(positives), sorted(negatives)
    n_pos, n_neg = len(pos), len(neg)
    rng = np.random.Generator(np.random.PCG64(seed))
    indices = np.empty((n_replications, n_pos + n_neg), dtype=np.int64)
    for r in range(n_replications):
        indices[r, :n_pos] = rng.integers(0, n_pos, size=n_pos, dtype=np.int64)
        indices[r, n_pos:] = n_pos + rng.integers(0, n_neg, size=n_neg, dtype=np.int64)
    return BootstrapDraws(tuple(pos + neg), n_pos, n_neg, indices, seed)


def draws_for(spec: AnalysisSpec, data: TaskLevelInput, members: Sequence[str]) -> BootstrapDraws:
    config = spec.data["framework_bootstrap"]
    humans = {i: data.items[i].human for i in members}
    return draw_stratified([i for i in members if humans[i] == 1],
                           [i for i in members if humans[i] == 0],
                           int(config["seed"]), int(config["n_resamples"]))


def percentile_interval(values: np.ndarray, quantiles: Sequence[float]) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    defined = np.isfinite(values)
    out: dict[str, Any] = {"n_replicates": int(values.size), "n_defined": int(defined.sum()),
                           "defined_share": float(defined.mean()) if values.size else 0.0}
    if values.size == 0 or not defined.all():
        return {**out, "available": False, "low": None, "high": None,
                "reason": "undefined in at least one replicate; no interval is published"}
    low, high = np.quantile(values, list(quantiles), method="linear")
    return {**out, "available": True, "low": float(low), "high": float(high), "reason": None}


class FrameworkReplicates:
    """Per-replicate values of the framework statistics on fixed draws."""

    def __init__(self, draws: BootstrapDraws, data: TaskLevelInput):
        self.draws = draws
        self.data = data
        self.weights = draws.weights().astype(float)
        order = draws.item_order
        self.human = np.array([data.items[i].human for i in order], dtype=float)
        self.n_pos, self.n_neg = draws.n_positive, draws.n_negative

    def _arrays(self, vector: LabelVector) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        labels = [vector.label(i) for i in self.draws.item_order]
        valid = np.array([lab is not None for lab in labels], dtype=float)
        label = np.array([-1 if lab is None else lab for lab in labels], dtype=float)
        correct = valid * (label == self.human)
        return valid, label, correct

    def scores(self, vector: LabelVector) -> dict[str, np.ndarray]:
        valid, _, correct = self._arrays(vector)
        w, p = self.weights, self.n_pos
        a_plus = w[:, :p] @ correct[:p] / self.n_pos
        a_minus = w[:, p:] @ correct[p:] / self.n_neg
        coverage = w @ valid / (self.n_pos + self.n_neg)
        return {"a_plus": a_plus, "a_minus": a_minus, "ba": (a_plus + a_minus) / 2,
                "coverage": coverage}

    def kappa(self, a: LabelVector, b: LabelVector | None = None,
              original: bool = False) -> np.ndarray:
        """Kappa of ``a`` against ``b`` (HUMAN when ``b`` is None) on valid paired support.

        With ``original`` the value on the observed sample (every campaign once).
        """

        valid_a, label_a, _ = self._arrays(a)
        if b is None:
            valid_b, label_b = np.ones_like(valid_a), self.human
        else:
            valid_b, label_b, _ = self._arrays(b)
        both = valid_a * valid_b
        cells = {
            "tp": both * (label_a == 1) * (label_b == 1),
            "tn": both * (label_a == 0) * (label_b == 0),
            "fp": both * (label_a == 1) * (label_b == 0),
            "fn": both * (label_a == 0) * (label_b == 1),
        }
        weights = np.ones((1, len(valid_a))) if original else self.weights
        return kappa_from_counts({k: weights @ v for k, v in cells.items()})


def _point(value: Fraction | float | None) -> dict[str, Any] | None:
    if isinstance(value, Fraction):
        return fraction_record(value)
    return None if value is None else {"value": float(value)}


def run_framework_bootstrap(
    spec: AnalysisSpec,
    data: TaskLevelInput,
    draws: BootstrapDraws,
    vectors: Mapping[str, LabelVector],
    primary_ids: Sequence[str],
    point_scores: Mapping[str, Any],
    margins: Mapping[str, tuple[str, Comparator | None]],
) -> dict[str, Any]:
    """Intervals for every primary procedure and for the declared paired margins.

    ``margins`` maps a margin name to (candidate procedure, fixed original
    comparator). The comparator is not searched again in any replicate.
    """

    quantiles = [float(q) for q in spec.data["framework_bootstrap"]["interval"]["quantiles"]]
    reps = FrameworkReplicates(draws, data)
    per_procedure: dict[str, Any] = {}
    replicate_ba: dict[str, np.ndarray] = {}
    for pid in primary_ids:
        values = reps.scores(vectors[pid])
        replicate_ba[pid] = values["ba"]
        point = point_scores[pid]
        per_procedure[pid] = {
            name: {"point_estimate": _point(getattr(point, name)),
                   "interval": percentile_interval(values[name], quantiles)}
            for name in ("a_plus", "a_minus", "ba", "coverage")
        }
        kappa_point = float(reps.kappa(vectors[pid], original=True)[0])
        per_procedure[pid]["kappa_vs_human"] = {
            "support": "campaigns with a valid label (HUMAN is valid on B)",
            "point_estimate": None if not np.isfinite(kappa_point) else {"value": kappa_point},
            "interval": percentile_interval(reps.kappa(vectors[pid]), quantiles)}

    margin_records: dict[str, Any] = {}
    for name, (candidate, comparator) in margins.items():
        if comparator is None or point_scores[candidate].ba is None:
            margin_records[name] = {"candidate": candidate, "comparator": None,
                                    "point_estimate": None,
                                    "interval": percentile_interval(np.array([]), quantiles)}
            continue
        values = replicate_ba[candidate] - replicate_ba[comparator.procedure_id]
        margin_records[name] = {
            "candidate": candidate, "comparator": comparator.procedure_id,
            "comparator_fixed_from_original_sample": True,
            "point_estimate": _point(point_scores[candidate].ba - comparator.ba),
            "interval": percentile_interval(values, quantiles),
        }
    return {"draws": draws.metadata(), "procedures": per_procedure, "margins": margin_records,
            "conditional_on_selected_comparators": True,
            "decisions_use_point_estimates": True}


__all__ = [
    "DRAW_ORDER",
    "GENERATOR",
    "BootstrapDraws",
    "BootstrapError",
    "FrameworkReplicates",
    "draw_stratified",
    "draws_for",
    "percentile_interval",
    "run_framework_bootstrap",
]
