"""The only place where analysis inputs are read from disk.

Private material enters through two explicit things: a data root, passed as an
argument, and an *input binding*, a small JSON file kept outside version
control that names, relative to that root, the dataset and the manifest and raw
logs bound to each design model. There is no default root and no search: a
missing argument is an error, not a guess. Frozen files are read, never
rewritten, and their embedded paths and hashes are never edited.

The binding declares its ``data_kind``. Assembling an empirical input requires
the caller to pass ``allow_empirical=True`` explicitly; nothing in the current
implementation stage does, because the empirical run is a separate, separately
authorised stage.

Example binding (paths relative to the data root)::

    {
      "binding_version": 1,
      "data_kind": "synthetic",
      "dataset": {"path": "data/items.csv", "encoding": "utf-8",
                  "item_id_prefix": "SYN", "expected_rows": 12},
      "collections": [
        {"model_key": "terra_5_6", "collection_model_id": "terra_5_6",
         "manifest": "runs/manifests/terra.csv", "raw_logs": ["runs/raw/terra.jsonl"]}
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..analysis import read_manifest_rows
from ..design import load_items, sha256_file
from .inputs import InputIntegrityError, TaskLevelInput, assemble_input
from .spec import AnalysisSpec

BINDING_VERSION = 1
DATA_KINDS = ("synthetic", "empirical")


class BoundaryError(ValueError):
    """A path or binding would let the analysis read something it should not."""


class EmpiricalInputNotAuthorised(PermissionError):
    """An empirical input was requested without explicit authorisation."""


def resolve(data_root: str | Path, relative: str) -> Path:
    """A path inside ``data_root``. Absolute paths and parent steps are refused."""

    if not relative or "\\" in relative:
        raise BoundaryError(f"binding paths are relative POSIX paths, got {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or ":" in pure.parts[0]:
        raise BoundaryError(f"binding path {relative!r} must stay inside the data root")
    root = Path(data_root).resolve()
    path = (root / Path(*pure.parts)).resolve()
    if root not in path.parents:
        raise BoundaryError(f"binding path {relative!r} escapes the data root")
    if not path.is_file():
        raise BoundaryError(f"binding path {relative!r} does not name a file under the root")
    return path


def load_binding(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        binding = json.load(handle)
    problems = []
    if binding.get("binding_version") != BINDING_VERSION:
        problems.append(f"binding_version must be {BINDING_VERSION}")
    if binding.get("data_kind") not in DATA_KINDS:
        problems.append("data_kind must be 'synthetic' or 'empirical'")
    dataset = binding.get("dataset") or {}
    for key in ("path", "encoding", "item_id_prefix", "expected_rows"):
        if key not in dataset:
            problems.append(f"dataset.{key} is required")
    collections = binding.get("collections") or []
    keys = [c.get("model_key") for c in collections]
    if len(keys) != len(set(keys)):
        problems.append("a design model is bound to more than one collection")
    for entry in collections:
        for key in ("model_key", "collection_model_id", "manifest", "raw_logs"):
            if key not in entry:
                problems.append(f"collection {entry.get('model_key')!r}: {key} is required")
    if problems:
        raise BoundaryError("Invalid input binding:\n- " + "\n- ".join(problems))
    return binding


def read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    """Every non-empty line must be one JSON object.

    The execution layer skips a malformed trailing line so that an interrupted
    run can resume; an analytical input cannot, because a lost line is a lost
    observation. Malformed lines are reported by line number only.
    """

    records, problems = [], []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"{path.name}: line {number} is not valid JSON")
                continue
            if not isinstance(value, dict):
                problems.append(f"{path.name}: line {number} is not a JSON object")
                continue
            records.append(value)
    if problems:
        raise InputIntegrityError(problems)
    return records


def read_item_rows(data_root: str | Path, dataset: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Items with the project's item-id convention; the campaign text is dropped here."""

    path = resolve(data_root, dataset["path"])
    config = {"dataset": {"path": path.name, "encoding": dataset["encoding"],
                          "expected_rows": int(dataset["expected_rows"]),
                          "item_id_prefix": dataset["item_id_prefix"]}}
    rows = load_items(config, path.parent)
    return [{k: v for k, v in row.items() if k != "text"} for row in rows]


def load_task_level_input(
    spec: AnalysisSpec,
    data_root: str | Path,
    binding_path: str | Path,
    *,
    allow_empirical: bool = False,
) -> TaskLevelInput:
    """Read the bound files and assemble the validated input."""

    if data_root is None or str(data_root).strip() == "":
        raise BoundaryError("an explicit data root is required")
    binding = load_binding(binding_path)
    if binding["data_kind"] == "empirical" and not allow_empirical:
        raise EmpiricalInputNotAuthorised(
            "This binding declares empirical data. Empirical execution is a separate, "
            "explicitly authorised stage and is not enabled here.")
    if binding["data_kind"] == "empirical":
        planned = spec.data["design"]["benchmark"]["planned_n_items"]
        if int(binding["dataset"]["expected_rows"]) != planned:
            raise BoundaryError(f"an empirical benchmark must have the planned {planned} items")

    files: dict[str, str] = {}
    dataset_path = resolve(data_root, binding["dataset"]["path"])
    files[binding["dataset"]["path"]] = sha256_file(dataset_path)
    item_rows = read_item_rows(data_root, binding["dataset"])

    manifests: dict[str, list[dict[str, str]]] = {}
    model_ids: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for entry in binding["collections"]:
        manifest_path = resolve(data_root, entry["manifest"])
        files[entry["manifest"]] = sha256_file(manifest_path)
        manifests[entry["model_key"]] = read_manifest_rows(manifest_path)
        model_ids[entry["model_key"]] = entry["collection_model_id"]
        for log in entry["raw_logs"]:
            log_path = resolve(data_root, log)
            files[log] = sha256_file(log_path)
            records.extend(read_jsonl_strict(log_path))

    provenance = {"input_binding_sha256": sha256_file(Path(binding_path)),
                  "input_files_sha256": dict(sorted(files.items()))}
    return assemble_input(spec, item_rows, manifests, model_ids, records,
                          data_kind=binding["data_kind"], provenance=provenance)


__all__ = [
    "BINDING_VERSION",
    "BoundaryError",
    "EmpiricalInputNotAuthorised",
    "load_binding",
    "load_task_level_input",
    "read_item_rows",
    "read_jsonl_strict",
    "resolve",
]
