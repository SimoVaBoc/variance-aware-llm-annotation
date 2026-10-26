"""Non-parametric cluster bootstrap with the item as the resampling unit.

Every annotation of a campaign — each prompt, each repeated sample, each model,
each Carlson strategy, each aggregate — belongs to that campaign. Resampling a
single call would break the dependence between them and understate the
uncertainty. So the unit is ``item_id``: a replication draws 250 item ids with
replacement and keeps everything attached to each drawn item together. An item
drawn twice contributes twice.

Mechanically that is a weighting. Every statistic the chapter uses is a ratio of
counts that are additive over items, so a replication is a weighted sum of
per-item contribution vectors rather than a rebuild of the dataset. The weights
are held in one integer matrix of shape ``(n_bootstrap, n_items)``, each row
summing to the number of draws, and each statistic is then a matrix product.
That is both faster and easier to check: the matrix shows on its face that no
call was resampled on its own, because calls never appear in it.

Nothing here decides what to do about an undefined statistic. A replication in
which a quantity is undefined is counted and reported with its reason; the
interval is computed on the defined replications only, and no threshold turns
that count into a pass or a fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

#: Version of the resampling procedure, recorded in every output.
BOOTSTRAP_VERSION = "chapter4_item_cluster_bootstrap_v1"

#: The only generator this module will use. Named so a future change is visible
#: in the configuration rather than hidden in a default.
SUPPORTED_GENERATOR = "PCG64"

UNDEFINED_ZERO_DENOMINATOR = "zero_denominator"
UNDEFINED_NO_VARIATION = "no_variation_in_one_labelling"
UNDEFINED_EMPTY_SUPPORT = "no_item_valid_for_both_measures"


class BootstrapError(RuntimeError):
    """The bootstrap was asked for something its specification does not allow."""


@dataclass(frozen=True)
class BootstrapConfig:
    """The frozen resampling specification.

    ``n_draws_per_replication`` defaults to the number of items, which is what a
    cluster bootstrap does; it is explicit so that a departure would have to be
    written down rather than inferred.
    """

    n_bootstrap: int
    seed: int
    generator: str = SUPPORTED_GENERATOR
    resampling_unit: str = "item_id"
    ci_level: float = 0.95
    quantiles: tuple[float, float] = (0.025, 0.975)
    n_draws_per_replication: int | None = None

    def __post_init__(self) -> None:
        if self.n_bootstrap < 1:
            raise BootstrapError("n_bootstrap must be at least 1")
        if self.generator != SUPPORTED_GENERATOR:
            raise BootstrapError(
                f"generator {self.generator!r} is not supported; this module uses "
                f"{SUPPORTED_GENERATOR} so that a run is reproducible from the seed alone"
            )
        if self.resampling_unit != "item_id":
            raise BootstrapError(
                "the resampling unit is the item; resampling anything finer would "
                "break the dependence within a campaign"
            )
        low, high = self.quantiles
        if not 0 < low < high < 1:
            raise BootstrapError("quantiles must satisfy 0 < low < high < 1")
        if abs((high - low) - self.ci_level) > 1e-12:
            raise BootstrapError(
                f"quantiles {self.quantiles} do not span the declared ci_level "
                f"{self.ci_level}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "bootstrap_version": BOOTSTRAP_VERSION,
            "n_bootstrap": self.n_bootstrap,
            "seed": self.seed,
            "generator": self.generator,
            "resampling_unit": self.resampling_unit,
            "ci_level": self.ci_level,
            "quantiles": list(self.quantiles),
            "n_draws_per_replication": self.n_draws_per_replication,
        }


def make_generator(config: BootstrapConfig) -> np.random.Generator:
    """A generator pinned to the configured bit generator and seed."""

    return np.random.Generator(np.random.PCG64(config.seed))


def draw_item_indices(n_items: int, config: BootstrapConfig) -> np.ndarray:
    """The raw draws, one row per replication, each row a sample with replacement."""

    if n_items < 1:
        raise BootstrapError("at least one item is required")
    n_draws = config.n_draws_per_replication or n_items
    rng = make_generator(config)
    return rng.integers(0, n_items, size=(config.n_bootstrap, n_draws), dtype=np.int64)


def item_weight_matrix(n_items: int, config: BootstrapConfig) -> np.ndarray:
    """Counts of how often each item was drawn, one row per replication.

    The counts are the whole of the resampling. An item drawn three times has a
    weight of three, which is what "do not deduplicate" means in arithmetic, and
    every row sums to the number of draws.
    """

    draws = draw_item_indices(n_items, config)
    weights = np.empty((draws.shape[0], n_items), dtype=np.int64)
    for row in range(draws.shape[0]):
        weights[row] = np.bincount(draws[row], minlength=n_items)
    return weights


@dataclass(frozen=True)
class Statistic:
    """One quantity, expressed as additive per-item components plus a rule.

    ``components`` maps a name to a per-item vector. A replication sums each
    vector over the drawn items and ``combine`` turns those sums into the value,
    returning NaN where the quantity is undefined on that replication.
    """

    name: str
    group: str
    components: Mapping[str, np.ndarray]
    combine: Callable[[Mapping[str, np.ndarray]], np.ndarray]
    undefined_reason: str = UNDEFINED_ZERO_DENOMINATOR
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        lengths = {len(v) for v in self.components.values()}
        if len(lengths) != 1:
            raise BootstrapError(
                f"statistic {self.name!r} has components of different lengths: {lengths}"
            )

    @property
    def n_items(self) -> int:
        return len(next(iter(self.components.values())))

    def point_estimate(self) -> float | None:
        """The statistic on the observed sample, every item counted once."""

        sums = {k: np.asarray([v.sum()], dtype=float) for k, v in self.components.items()}
        value = np.asarray(self.combine(sums), dtype=float)
        return None if not np.isfinite(value[0]) else float(value[0])


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> Callable:
    """A ratio that is undefined, not zero, when its denominator vanishes."""

    def combine(sums: Mapping[str, np.ndarray]) -> np.ndarray:
        num = np.asarray(sums["numerator"], dtype=float)
        den = np.asarray(sums["denominator"], dtype=float)
        out = np.full(num.shape, np.nan, dtype=float)
        ok = den > 0
        out[ok] = num[ok] / den[ok]
        return out

    return combine


def ratio_statistic(name: str, group: str, numerator: np.ndarray,
                    denominator: np.ndarray, **detail: Any) -> Statistic:
    return Statistic(
        name=name, group=group,
        components={"numerator": np.asarray(numerator, dtype=float),
                    "denominator": np.asarray(denominator, dtype=float)},
        combine=ratio(numerator, denominator),
        undefined_reason=UNDEFINED_ZERO_DENOMINATOR,
        detail=detail,
    )


def kappa_from_counts(sums: Mapping[str, np.ndarray]) -> np.ndarray:
    """Cohen's kappa from the four cells of the table.

    Identical in form to metrics.classification_metrics, which computes it from
    the observed and expected agreement. Undefined when the expected agreement
    reaches one, which happens when both labellings are constant and equal.
    """

    tp = np.asarray(sums["tp"], dtype=float)
    tn = np.asarray(sums["tn"], dtype=float)
    fp = np.asarray(sums["fp"], dtype=float)
    fn = np.asarray(sums["fn"], dtype=float)
    n = tp + tn + fp + fn
    out = np.full(n.shape, np.nan, dtype=float)
    ok = n > 0
    observed = np.zeros_like(n)
    observed[ok] = (tp[ok] + tn[ok]) / n[ok]
    true_pos = np.zeros_like(n)
    pred_pos = np.zeros_like(n)
    true_pos[ok] = (tp[ok] + fn[ok]) / n[ok]
    pred_pos[ok] = (tp[ok] + fp[ok]) / n[ok]
    expected = true_pos * pred_pos + (1 - true_pos) * (1 - pred_pos)
    usable = ok & (np.abs(1 - expected) > 0)
    out[usable] = (observed[usable] - expected[usable]) / (1 - expected[usable])
    return out


def kappa_statistic(name: str, group: str, tp, tn, fp, fn, **detail: Any) -> Statistic:
    return Statistic(
        name=name, group=group,
        components={
            "tp": np.asarray(tp, dtype=float), "tn": np.asarray(tn, dtype=float),
            "fp": np.asarray(fp, dtype=float), "fn": np.asarray(fn, dtype=float),
        },
        combine=kappa_from_counts,
        undefined_reason=UNDEFINED_NO_VARIATION,
        detail=detail,
    )


def difference_statistic(name: str, group: str, left: Statistic, right: Statistic,
                         **detail: Any) -> Statistic:
    """The paired difference left minus right, evaluated on the same replication.

    Both sides are computed from the same drawn items, so the difference carries
    the pairing rather than treating the two as independent samples. It is
    undefined on any replication where either side is.
    """

    if left.n_items != right.n_items:
        raise BootstrapError("paired statistics must cover the same item index")
    components = {f"left::{k}": v for k, v in left.components.items()}
    components.update({f"right::{k}": v for k, v in right.components.items()})

    def combine(sums: Mapping[str, np.ndarray]) -> np.ndarray:
        a = left.combine({k.split("::", 1)[1]: v for k, v in sums.items()
                          if k.startswith("left::")})
        b = right.combine({k.split("::", 1)[1]: v for k, v in sums.items()
                           if k.startswith("right::")})
        return np.asarray(a, dtype=float) - np.asarray(b, dtype=float)

    return Statistic(
        name=name, group=group, components=components, combine=combine,
        undefined_reason=UNDEFINED_EMPTY_SUPPORT, detail=detail,
    )


def evaluate(statistic: Statistic, weights: np.ndarray,
             config: BootstrapConfig) -> dict[str, Any]:
    """Point estimate, percentile interval and the census of undefined replications."""

    if weights.shape[1] != statistic.n_items:
        raise BootstrapError(
            f"statistic {statistic.name!r} covers {statistic.n_items} items but the "
            f"weight matrix covers {weights.shape[1]}"
        )
    sums = {
        key: weights @ np.asarray(vector, dtype=float)
        for key, vector in statistic.components.items()
    }
    values = np.asarray(statistic.combine(sums), dtype=float)
    defined = np.isfinite(values)
    n_valid = int(defined.sum())
    n_requested = int(weights.shape[0])

    low = high = None
    if n_valid:
        low, high = (float(q) for q in np.quantile(values[defined], config.quantiles))

    return {
        "statistic": statistic.name,
        "group": statistic.group,
        "point_estimate": statistic.point_estimate(),
        "ci_low": low,
        "ci_high": high,
        "ci_level": config.ci_level,
        "quantiles": list(config.quantiles),
        "n_bootstrap_requested": n_requested,
        "n_bootstrap_valid": n_valid,
        "n_bootstrap_undefined": n_requested - n_valid,
        "undefined_share": (n_requested - n_valid) / n_requested,
        "undefined_reason_counts": (
            {statistic.undefined_reason: n_requested - n_valid}
            if n_requested - n_valid else {}
        ),
        "interval_computed_on": "defined replications only",
        **dict(statistic.detail),
    }


def run(statistics: Sequence[Statistic], weights: np.ndarray,
        config: BootstrapConfig) -> list[dict[str, Any]]:
    return [evaluate(statistic, weights, config) for statistic in statistics]


__all__ = [
    "BOOTSTRAP_VERSION",
    "SUPPORTED_GENERATOR",
    "UNDEFINED_EMPTY_SUPPORT",
    "UNDEFINED_NO_VARIATION",
    "UNDEFINED_ZERO_DENOMINATOR",
    "BootstrapConfig",
    "BootstrapError",
    "Statistic",
    "difference_statistic",
    "draw_item_indices",
    "evaluate",
    "item_weight_matrix",
    "kappa_from_counts",
    "kappa_statistic",
    "make_generator",
    "ratio_statistic",
    "run",
]
