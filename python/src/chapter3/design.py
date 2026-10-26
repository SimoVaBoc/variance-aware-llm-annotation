"""Offline design and manifest utilities for the Chapter 3 experiment.

This module never calls an external model API. It validates the frozen design
and creates a deterministic task manifest that an execution layer can consume.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REQUIRED_DATA_COLUMNS = {
    "text",
    "HUMAN",
    "lgoal",
    "success",
    "subcategory",
    "year",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    errors: list[str] = []

    prompts = config.get("prompts", [])
    models = config.get("models", [])
    replicate_count = config.get("replicates", {}).get("count")
    expected_rows = config.get("dataset", {}).get("expected_rows")

    if len(prompts) != 4:
        errors.append(f"Expected four prompt types, found {len(prompts)}")
    if len(models) != 3:
        errors.append(f"Expected three models, found {len(models)}")
    if replicate_count != 3:
        errors.append(f"Expected three replicates, found {replicate_count!r}")
    if expected_rows != 250:
        errors.append(f"Expected 250 items, found {expected_rows!r}")

    for name, entries in (("prompt", prompts), ("model", models)):
        ids = [entry.get("id") for entry in entries]
        if any(not value for value in ids):
            errors.append(f"Every {name} requires a non-empty id")
        if len(ids) != len(set(ids)):
            errors.append(f"Duplicate {name} ids are not allowed")

    expected_calls = expected_rows * len(prompts) * len(models) * (replicate_count or 0)
    configured_calls = config.get("execution", {}).get("expected_full_calls")
    if configured_calls != expected_calls:
        errors.append(
            f"expected_full_calls is {configured_calls!r}, but the design implies "
            f"{expected_calls}"
        )

    if config.get("execution", {}).get("live_calls_enabled") is not False:
        errors.append("live_calls_enabled must remain false in the frozen design file")

    tie_policy = config.get("aggregation", {}).get("tie_policy")
    if tie_policy not in {"unresolved_fail_closed", "zero", "one", "nan"}:
        errors.append(f"Unsupported aggregation tie policy: {tie_policy!r}")

    if errors:
        raise ValueError("Invalid Chapter 3 configuration:\n- " + "\n- ".join(errors))


def load_items(config: dict[str, Any], project_root: str | Path = ".") -> list[dict[str, str]]:
    root = Path(project_root)
    data_config = config["dataset"]
    data_path = root / data_config["path"]
    encoding = data_config["encoding"]

    with data_path.open(encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_DATA_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"Dataset is missing columns: {sorted(missing)}")
        rows = list(reader)

    if len(rows) != data_config["expected_rows"]:
        raise ValueError(
            f"Expected {data_config['expected_rows']} rows, found {len(rows)}"
        )

    width = len(str(len(rows)))
    prefix = data_config["item_id_prefix"]
    for index, row in enumerate(rows, start=1):
        row["item_id"] = f"{prefix}{index:0{width}d}"

    return rows


def profile_dataset(config: dict[str, Any], project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    data_path = root / config["dataset"]["path"]
    items = load_items(config, root)

    text_column = config["dataset"]["text_column"]
    human_column = config["dataset"]["human_label_column"]
    outcome_column = config["dataset"]["outcome_column"]

    control_character_rows = 0
    control_character_count = 0
    for row in items:
        controls = [character for character in row[text_column] if 0x80 <= ord(character) <= 0x9F]
        if controls:
            control_character_rows += 1
            control_character_count += len(controls)

    subcategory_counts: dict[str, list[int]] = {}
    for row in items:
        subcategory_counts.setdefault(row["subcategory"], []).append(int(row[outcome_column]))

    separated_subcategories = sum(
        all(value == 0 for value in values) or all(value == 1 for value in values)
        for values in subcategory_counts.values()
    )

    return {
        "dataset_path": str(data_path),
        "dataset_sha256": sha256_file(data_path),
        "rows": len(items),
        "columns": list(items[0].keys()),
        "human_label_counts": dict(sorted(Counter(row[human_column] for row in items).items())),
        "outcome_counts": dict(sorted(Counter(row[outcome_column] for row in items).items())),
        "unique_texts": len({row[text_column] for row in items}),
        "unique_subcategories": len(subcategory_counts),
        "singleton_subcategories": sum(len(values) == 1 for values in subcategory_counts.values()),
        "outcome_separated_subcategories": separated_subcategories,
        "rows_with_c1_control_characters": control_character_rows,
        "c1_control_character_count": control_character_count,
    }


def _task_rows(config: dict[str, Any], items: Iterable[dict[str, str]]) -> Iterable[dict[str, Any]]:
    data_encoding = config["dataset"]["encoding"]
    text_column = config["dataset"]["text_column"]
    study_id = config["study"]["id"]
    config_hash = canonical_json_hash(config)

    for model, prompt, replicate, item in itertools.product(
        config["models"],
        config["prompts"],
        range(1, config["replicates"]["count"] + 1),
        items,
    ):
        item_id = item["item_id"]
        text_hash = sha256_bytes(item[text_column].encode(data_encoding))
        prompt_hash = sha256_bytes(prompt["text"].encode("utf-8"))
        task_id = "__".join(
            (
                study_id,
                model["id"],
                prompt["id"],
                f"s{replicate:02d}",
                item_id,
            )
        )
        yield {
            "task_id": task_id,
            "study_id": study_id,
            "item_id": item_id,
            "model_id": model["id"],
            "provider": model["provider"],
            "api_model_requested": model["api_model"],
            "prompt_id": prompt["id"],
            "prompt_family": prompt["family"],
            "replicate_id": replicate,
            "text_sha256": text_hash,
            "prompt_sha256": prompt_hash,
            "config_sha256": config_hash,
        }


def build_task_manifest(
    config: dict[str, Any],
    project_root: str | Path = ".",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(project_root)
    items = load_items(config, root)
    tasks = list(_task_rows(config, items))
    expected = config["execution"]["expected_full_calls"]

    if len(tasks) != expected:
        raise AssertionError(f"Expected {expected} tasks, generated {len(tasks)}")
    task_ids = [row["task_id"] for row in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise AssertionError("Task IDs are not unique")

    data_path = root / config["dataset"]["path"]
    metadata = {
        "study_id": config["study"]["id"],
        "schema_version": config["schema_version"],
        "config_sha256": canonical_json_hash(config),
        "dataset_sha256": sha256_file(data_path),
        "n_items": len(items),
        "n_prompts": len(config["prompts"]),
        "n_models": len(config["models"]),
        "n_replicates": config["replicates"]["count"],
        "n_tasks": len(tasks),
        "live_calls_enabled": config["execution"]["live_calls_enabled"],
    }
    return tasks, metadata


def select_pilot_tasks(
    tasks: list[dict[str, Any]],
    item_count: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select pilot items deterministically without using human labels."""

    if item_count < 1:
        raise ValueError("Pilot item count must be positive")

    item_keys: dict[str, str] = {}
    for task in tasks:
        item_id = str(task["item_id"])
        if item_id not in item_keys:
            item_keys[item_id] = sha256_bytes(
                f"{task['study_id']}:{item_id}:{task['text_sha256']}".encode("utf-8")
            )

    if item_count > len(item_keys):
        raise ValueError(
            f"Pilot requests {item_count} items, but only {len(item_keys)} are available"
        )

    selected_items = sorted(item_keys, key=lambda item_id: item_keys[item_id])[:item_count]
    selected_set = set(selected_items)
    pilot_tasks = [task for task in tasks if task["item_id"] in selected_set]
    return pilot_tasks, sorted(selected_items)


class ManifestExists(FileExistsError):
    """A manifest or its metadata already exists and was not overwritten."""


def write_manifest(
    tasks: list[dict[str, Any]],
    metadata: dict[str, Any],
    csv_path: str | Path,
    *,
    force: bool = False,
) -> tuple[Path, Path]:
    """Write a legacy single-arm manifest and its metadata.

    Refuses by default when either file exists, before anything is opened for
    writing: existing manifests are referenced by hash and must not change
    silently. ``force`` exists only for a deliberate, separately approved
    replacement.
    """

    target = Path(csv_path)
    metadata_path = target.with_suffix(".meta.json")
    if not force:
        existing = [str(path) for path in (target, metadata_path) if path.exists()]
        if existing:
            raise ManifestExists(
                f"Refusing to overwrite existing manifest file(s): {', '.join(existing)}. "
                "Write to a new path, or pass --force only for a deliberate, approved "
                "replacement."
            )
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tasks[0].keys()))
        writer.writeheader()
        writer.writerows(tasks)

    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return target, metadata_path
