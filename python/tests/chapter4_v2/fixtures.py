"""Invented fixtures for the public suite. Nothing here derives from campaign records.

Items are ``SYN01``, ``SYN02``, ...; campaign texts are placeholders; hashes are
digests of the fixture's own identifiers. One design model is bound to a
collection ``model_id`` that differs from its design key, as happens with real
collections, so the binding is exercised rather than assumed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from _guard import PROJECT_ROOT  # noqa: F401  (installs the guard first)

from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.spec import AnalysisSpec

COLLECTION_MODEL_IDS = {
    "terra_5_6": "terra_5_6",
    "sonnet_5": "sonnet_5",
    "deepseek_v4_pro": "deepseek_v4_pro_synthetic_route",
}
HASH_FIELDS = ("text_sha256", "prompt_sha256", "system_prompt_sha256", "payload_sha256",
               "config_sha256")


def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()


def make_item_rows(n: int = 6, prefix: str = "SYN") -> list[dict[str, str]]:
    width = len(str(n))
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "item_id": f"{prefix}{i:0{width}d}",
            "text": f"synthetic placeholder campaign {i}",
            "HUMAN": str(i % 2),
            "success": str((i // 2) % 2),
            "lgoal": f"{8 + i / 4:.2f}",
            "subcategory": ("alpha", "beta", "gamma")[i % 3],
            "year": str(2010 + i % 2),
        })
    return rows


def label_orders_for(item_index: int, va_templates: tuple[str, ...]) -> dict[str, str]:
    """Two prompts share one order and the third takes the other, rotating the minority."""

    majority, minority = ("10", "01") if item_index % 2 else ("01", "10")
    odd = sorted(va_templates)[item_index % len(va_templates)]
    return {t: (minority if t == odd else majority) for t in va_templates}


def make_manifests(spec: AnalysisSpec, item_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    manifests: dict[str, list[dict[str, Any]]] = {}
    for model_key in spec.model_keys:
        model_id = COLLECTION_MODEL_IDS[model_key]
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(item_ids):
            orders = label_orders_for(index, spec.va_template_ids)
            plan = [("carlson", t, 1, "") for t in spec.cb_template_ids]
            plan += [("camuffo", t, s, orders[t]) for t in spec.va_template_ids
                     for s in range(1, spec.va_generations + 1)]
            for arm, template, sample, order in plan:
                task_id = f"synthetic__{model_id}__{template}__s{sample:02d}__{item}"
                row = {"task_id": task_id, "item_id": item, "model_id": model_id, "arm": arm,
                       "template_id": template, "sample_index": str(sample),
                       "label_order": order, "is_remediation": "False"}
                for name in HASH_FIELDS:
                    row[name] = _digest(name, model_id, template, item, order)
                rows.append(row)
        manifests[model_key] = rows
    return manifests


def key_of(row: Mapping[str, Any], model_key: str) -> SlotKey:
    return SlotKey(str(row["item_id"]), model_key, str(row["template_id"]),
                   int(row["sample_index"]))


def record(row: Mapping[str, Any], status: str = "success", label: int | None = 0,
           raw: str | None = None) -> dict[str, Any]:
    out = {k: row[k] for k in ("task_id", "item_id", "model_id", "arm", "template_id")}
    out["sample_index"] = int(row["sample_index"])
    out["label_order"] = row["label_order"] or None
    out.update({name: row[name] for name in HASH_FIELDS})
    out["is_remediation"] = False
    out["status"] = status
    if status == "success":
        out["raw_response"] = str(label) if raw is None else raw
        out["parsed_label"] = label
    elif status == "parse_error":
        out["raw_response"] = "not a label" if raw is None else raw
        out["parsed_label"] = None
    else:
        out["raw_response"] = None
        out["parsed_label"] = None
        out["error_type"] = "SyntheticConnectionError"
    return out


def make_records(manifests: Mapping[str, list[dict[str, Any]]],
                 label_of: Callable[[SlotKey], int] = lambda key: 0,
                 states: Mapping[SlotKey, str] | None = None) -> list[dict[str, Any]]:
    """One terminal success per task unless ``states`` says otherwise.

    ``states`` values: 'parse_error', 'api_error_only', 'api_error_then_success',
    'absent'.
    """

    states = dict(states or {})
    out: list[dict[str, Any]] = []
    for model_key, rows in manifests.items():
        for row in rows:
            key = key_of(row, model_key)
            state = states.get(key, "success")
            if state == "success":
                out.append(record(row, "success", label_of(key)))
            elif state == "parse_error":
                out.append(record(row, "parse_error"))
            elif state == "api_error_only":
                out.append(record(row, "api_error"))
            elif state == "api_error_then_success":
                out.append(record(row, "api_error"))
                out.append(record(row, "success", label_of(key)))
            elif state != "absent":
                raise ValueError(state)
    return out


def build_input(spec: AnalysisSpec, n_items: int = 4, *,
                label_of: Callable[[SlotKey], int] = lambda key: 0,
                states: Mapping[SlotKey, str] | None = None,
                item_rows: list[dict[str, str]] | None = None,
                mutate_manifests: Callable[[dict], None] | None = None):
    """A validated synthetic TaskLevelInput, assembled in memory."""

    from src.chapter3.chapter4_v2.inputs import assemble_input

    items = item_rows or make_item_rows(n_items)
    manifests = make_manifests(spec, [row["item_id"] for row in items])
    if mutate_manifests:
        mutate_manifests(manifests)
    records = make_records(manifests, label_of, states)
    return assemble_input(spec, items, manifests, COLLECTION_MODEL_IDS, records,
                          data_kind="synthetic")


def write_tree(root: Path, spec: AnalysisSpec, n_items: int = 6, *,
               data_kind: str = "synthetic",
               mutate_records: Callable[[list[dict]], list[dict]] | None = None) -> Path:
    """Write a complete synthetic input tree and its binding; return the binding path."""

    items = make_item_rows(n_items)
    (root / "data").mkdir(parents=True)
    with (root / "data/items.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[k for k in items[0] if k != "item_id"])
        writer.writeheader()
        writer.writerows({k: v for k, v in row.items() if k != "item_id"} for row in items)
    manifests = make_manifests(spec, [row["item_id"] for row in items])
    records = make_records(manifests)
    if mutate_records:
        records = mutate_records(records)
    collections = []
    (root / "runs/manifests").mkdir(parents=True)
    (root / "runs/raw").mkdir(parents=True)
    for model_key, rows in manifests.items():
        with (root / f"runs/manifests/{model_key}.csv").open("w", encoding="utf-8",
                                                             newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        model_id = COLLECTION_MODEL_IDS[model_key]
        with (root / f"runs/raw/{model_key}.jsonl").open("w", encoding="utf-8") as handle:
            for rec in records:
                if rec["model_id"] == model_id:
                    handle.write(json.dumps(rec) + "\n")
        collections.append({"model_key": model_key, "collection_model_id": model_id,
                            "manifest": f"runs/manifests/{model_key}.csv",
                            "raw_logs": [f"runs/raw/{model_key}.jsonl"]})
    binding = {"binding_version": 1, "data_kind": data_kind,
               "dataset": {"path": "data/items.csv", "encoding": "utf-8",
                           "item_id_prefix": "SYN", "expected_rows": n_items},
               "collections": collections}
    path = root / "input_binding.json"
    path.write_text(json.dumps(binding, indent=2), encoding="utf-8")
    return path
