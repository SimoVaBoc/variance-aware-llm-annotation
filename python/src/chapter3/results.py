"""Strict parsing and validation for long-format annotation outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


RESULT_REQUIRED_FIELDS = {
    "task_id",
    "item_id",
    "model_id",
    "api_model_requested",
    "api_model_returned",
    "prompt_id",
    "replicate_id",
    "raw_response",
    "parsed_label",
    "status",
    "started_at_utc",
    "completed_at_utc",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "provider_request_id",
    "system_fingerprint",
    "attempt_count",
    "error_type",
    "error_message",
    "text_sha256",
    "prompt_sha256",
    "config_sha256",
}


def parse_binary_label(raw_response: str) -> int:
    """Parse an exact binary response without searching arbitrary digits."""

    normalized = str(raw_response).strip()
    if normalized == "0":
        return 0
    if normalized == "1":
        return 1
    raise ValueError(f"Expected an exact binary response, received {raw_response!r}")


def validate_result_records(
    records: Iterable[dict[str, Any]],
    expected_task_ids: set[str] | None = None,
) -> dict[str, Any]:
    rows = list(records)
    errors: list[str] = []
    task_ids: list[str] = []

    for index, row in enumerate(rows, start=1):
        missing = RESULT_REQUIRED_FIELDS - set(row)
        if missing:
            errors.append(f"Row {index} is missing fields: {sorted(missing)}")
            continue
        task_ids.append(str(row["task_id"]))
        if row["status"] == "success" and row["parsed_label"] not in (0, 1):
            errors.append(f"Row {index} has success status without a binary label")

    duplicates = sorted(task_id for task_id, count in Counter(task_ids).items() if count > 1)
    if duplicates:
        errors.append(f"Duplicate task IDs: {duplicates[:10]}")

    missing_tasks: list[str] = []
    unexpected_tasks: list[str] = []
    if expected_task_ids is not None:
        observed = set(task_ids)
        missing_tasks = sorted(expected_task_ids - observed)
        unexpected_tasks = sorted(observed - expected_task_ids)
        if missing_tasks:
            errors.append(f"Missing {len(missing_tasks)} expected tasks")
        if unexpected_tasks:
            errors.append(f"Found {len(unexpected_tasks)} unexpected tasks")

    return {
        "valid": not errors,
        "n_records": len(rows),
        "n_unique_tasks": len(set(task_ids)),
        "n_missing_tasks": len(missing_tasks),
        "n_unexpected_tasks": len(unexpected_tasks),
        "errors": errors,
    }
