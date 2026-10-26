"""Prespecified aggregation helpers for complete Chapter 3 result records."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .metrics import majority_vote


def aggregate_repeats(
    records: Iterable[dict[str, Any]],
    expected_replicates: int = 3,
) -> list[dict[str, Any]]:
    """Aggregate repeated calls within each item-prompt-model cell."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (
            str(record["item_id"]),
            str(record["model_id"]),
            str(record["prompt_id"]),
        )
        groups[key].append(record)

    aggregated: list[dict[str, Any]] = []
    for (item_id, model_id, prompt_id), rows in sorted(groups.items()):
        if len(rows) != expected_replicates:
            raise ValueError(
                f"{item_id}/{model_id}/{prompt_id} has {len(rows)} records; "
                f"expected {expected_replicates}"
            )
        replicate_ids = [int(row["replicate_id"]) for row in rows]
        if len(replicate_ids) != len(set(replicate_ids)):
            raise ValueError(f"Duplicate replicate in {item_id}/{model_id}/{prompt_id}")
        if any(row.get("status") != "success" for row in rows):
            raise ValueError(f"Unsuccessful record in {item_id}/{model_id}/{prompt_id}")

        labels = [int(row["parsed_label"]) for row in rows]
        label = majority_vote(labels)
        aggregated.append(
            {
                "item_id": item_id,
                "model_id": model_id,
                "prompt_id": prompt_id,
                "aggregated_label": label,
                "positive_votes": sum(labels),
                "n_votes": len(labels),
                "unanimous": len(set(labels)) == 1,
            }
        )
    return aggregated


def aggregate_configurations(
    repeat_aggregates: Iterable[dict[str, Any]],
    expected_cells: int = 12,
    tie_policy: str = "error",
) -> list[dict[str, Any]]:
    """Aggregate the repeat-level labels across prompt-model cells by item."""

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in repeat_aggregates:
        groups[str(record["item_id"])].append(record)

    output: list[dict[str, Any]] = []
    for item_id, rows in sorted(groups.items()):
        if len(rows) != expected_cells:
            raise ValueError(
                f"{item_id} has {len(rows)} prompt-model cells; expected {expected_cells}"
            )
        cells = [(str(row["model_id"]), str(row["prompt_id"])) for row in rows]
        if len(cells) != len(set(cells)):
            raise ValueError(f"Duplicate prompt-model cell for {item_id}")
        labels = [int(row["aggregated_label"]) for row in rows]
        positives = sum(labels)
        is_tied = positives * 2 == len(labels)
        label = majority_vote(labels, tie_policy=tie_policy)
        output.append(
            {
                "item_id": item_id,
                "aggregated_label": label,
                "positive_cells": positives,
                "n_cells": len(labels),
                "tied": is_tied,
            }
        )
    return output
