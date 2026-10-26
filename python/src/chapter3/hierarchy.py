"""Hierarchical aggregation for the Camuffo arm, with explicit missingness.

STATUS: researcher approved. The rule is recorded in the experiment definition
under ``aggregation``.

The single rule, applied identically at all three levels:

* at least **two** valid contributions are required;
* with three valid contributions, the majority decides;
* with two valid contributions that agree, their label decides;
* with two valid contributions that disagree, the result is ``None``;
* with one or zero valid contributions, the result is ``None``;
* parse errors and missing outputs are never substituted;
* every aggregate records ``n_valid``, ``n_expected``, the 0 and 1 counts,
  ``tied``, ``complete`` and, when the result is null, the reason.

Why a minimum of two: a single surviving call is not a majority of anything.
Letting it decide would make the annotation of the worst-covered cells rest on
whichever call happened to return a parseable answer, which is exactly the
selection the retry contract refuses elsewhere. Propagating ``None`` keeps the
gap visible in the downstream fit instead of hiding it behind a lone vote.

The primary hierarchy is S, then P, then M. The pooled majority over all 27
outputs is a secondary robustness check, never the primary annotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


#: Status of this rule in the design.
AGGREGATION_STATUS = "researcher_approved"

#: Fewer valid contributions than this yields a null, never a label.
MINIMUM_VALID_CONTRIBUTIONS = 2

#: Only a success carries a label into an aggregate.
VALID_STATUS = "success"

#: Why an aggregate came out null. ``None`` when it did not.
NULL_NO_VALID = "no_valid_contributions"
NULL_TOO_FEW = "below_minimum_valid_contributions"
NULL_TIED = "valid_contributions_tied"


@dataclass(frozen=True)
class Aggregate:
    """One aggregated value plus the accounting that produced it."""

    label: int | None
    n_valid: int
    n_expected: int
    votes_1: int
    votes_0: int
    tied: bool
    null_reason: str | None

    @property
    def positive_votes(self) -> int:
        return self.votes_1

    def as_record(self) -> dict[str, Any]:
        return {
            "aggregated_label": self.label,
            "n_valid": self.n_valid,
            "n_expected": self.n_expected,
            "votes_1": self.votes_1,
            "votes_0": self.votes_0,
            "positive_votes": self.votes_1,
            "tied": self.tied,
            "complete": self.n_valid == self.n_expected,
            "null_reason": self.null_reason,
        }


def majority(labels: Sequence[int | None], n_expected: int | None = None) -> Aggregate:
    """Majority among the valid labels, under a two-contribution minimum.

    ``None`` entries are missing, not votes. They are counted in ``n_expected``
    and excluded from the vote, never imputed. Fewer than two valid votes, or
    two that disagree, yields ``None`` with the reason recorded.
    """

    valid = [int(label) for label in labels if label is not None]
    expected = len(labels) if n_expected is None else int(n_expected)
    votes_1 = sum(valid)
    votes_0 = len(valid) - votes_1
    tied = bool(valid) and votes_1 == votes_0

    label: int | None
    reason: str | None
    if not valid:
        label, reason = None, NULL_NO_VALID
    elif len(valid) < MINIMUM_VALID_CONTRIBUTIONS:
        # A lone surviving call is not a majority of anything.
        label, reason = None, NULL_TOO_FEW
    elif tied:
        label, reason = None, NULL_TIED
    else:
        label, reason = (1 if votes_1 > votes_0 else 0), None

    return Aggregate(
        label=label,
        n_valid=len(valid),
        n_expected=expected,
        votes_1=votes_1,
        votes_0=votes_0,
        tied=tied,
        null_reason=reason,
    )


def valid_label(record: Mapping[str, Any]) -> int | None:
    """The record's label, or ``None`` when it did not produce a valid one.

    A ``parse_error`` reaches here as ``None``: it occupied its sample slot and
    contributed no label. It is never replaced.
    """

    if record.get("status") != VALID_STATUS:
        return None
    label = record.get("parsed_label")
    return int(label) if label in (0, 1) else None


def _group(records: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> dict[tuple, list]:
    grouped: dict[tuple, list] = {}
    for record in records:
        grouped.setdefault(tuple(str(record[key]) for key in keys), []).append(record)
    return grouped


def aggregate_samples(
    records: Iterable[Mapping[str, Any]],
    expected_samples: int = 3,
) -> list[dict[str, Any]]:
    """Level 1: majority over S, within each item-variant-model cell."""

    output: list[dict[str, Any]] = []
    grouped = _group(records, ("item_id", "model_id", "template_id"))
    for (item_id, model_id, template_id), rows in sorted(grouped.items()):
        labels = [valid_label(row) for row in rows]
        aggregate = majority(labels, n_expected=max(expected_samples, len(rows)))
        output.append(
            {
                "item_id": item_id,
                "model_id": model_id,
                "template_id": template_id,
                "camuffo_variant_id": rows[0].get("camuffo_variant_id"),
                "label_orders": sorted(
                    {row.get("label_order") for row in rows if row.get("label_order")}
                ),
                **aggregate.as_record(),
            }
        )
    return output


def aggregate_prompts(
    sample_aggregates: Iterable[Mapping[str, Any]],
    expected_prompts: int = 3,
) -> list[dict[str, Any]]:
    """Level 2: majority over P, within each item-model pair."""

    output: list[dict[str, Any]] = []
    grouped = _group(sample_aggregates, ("item_id", "model_id"))
    for (item_id, model_id), rows in sorted(grouped.items()):
        labels = [row["aggregated_label"] for row in rows]
        aggregate = majority(labels, n_expected=max(expected_prompts, len(rows)))
        output.append(
            {
                "item_id": item_id,
                "model_id": model_id,
                "n_prompts_present": len(rows),
                **aggregate.as_record(),
            }
        )
    return output


def aggregate_models(
    prompt_aggregates: Iterable[Mapping[str, Any]],
    expected_models: int = 3,
) -> list[dict[str, Any]]:
    """Level 3: majority over M, yielding the final annotation per item."""

    output: list[dict[str, Any]] = []
    grouped = _group(prompt_aggregates, ("item_id",))
    for (item_id,), rows in sorted(grouped.items()):
        labels = [row["aggregated_label"] for row in rows]
        aggregate = majority(labels, n_expected=max(expected_models, len(rows)))
        record = {"item_id": item_id, "n_models_present": len(rows), **aggregate.as_record()}
        record["annotation"] = record.pop("aggregated_label")
        output.append(record)
    return output


def hierarchical_annotation(
    records: Iterable[Mapping[str, Any]],
    expected_samples: int = 3,
    expected_prompts: int = 3,
    expected_models: int = 3,
) -> dict[str, Any]:
    """Run the three levels in order and return every intermediate stage."""

    rows = list(records)
    samples = aggregate_samples(rows, expected_samples)
    prompts = aggregate_prompts(samples, expected_prompts)
    models = aggregate_models(prompts, expected_models)
    return {
        "status": AGGREGATION_STATUS,
        "by_sample": samples,
        "by_prompt": prompts,
        "by_model": models,
        "n_items": len(models),
        "n_null_annotations": sum(1 for row in models if row["annotation"] is None),
    }


def pooled_annotation(
    records: Iterable[Mapping[str, Any]],
    expected_calls: int = 27,
) -> list[dict[str, Any]]:
    """Secondary robustness check: one majority over all outputs per item.

    This is never the primary annotation. It weights a model that answered more
    often more heavily, which is exactly what the hierarchy avoids.
    """

    output: list[dict[str, Any]] = []
    grouped = _group(records, ("item_id",))
    for (item_id,), rows in sorted(grouped.items()):
        labels = [valid_label(row) for row in rows]
        aggregate = majority(labels, n_expected=max(expected_calls, len(rows)))
        output.append(
            {
                "item_id": item_id,
                "role": "robustness_check_secondary",
                **aggregate.as_record(),
            }
        )
    return output


__all__ = [
    "AGGREGATION_STATUS",
    "MINIMUM_VALID_CONTRIBUTIONS",
    "NULL_NO_VALID",
    "NULL_TIED",
    "NULL_TOO_FEW",
    "Aggregate",
    "aggregate_models",
    "aggregate_prompts",
    "aggregate_samples",
    "hierarchical_annotation",
    "majority",
    "pooled_annotation",
    "valid_label",
]
