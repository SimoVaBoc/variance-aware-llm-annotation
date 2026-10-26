"""An invented input for the worked example. Nothing here derives from campaign records.

Items are ``SYN001``, ``SYN002``, ...; texts are placeholders; hashes are digests of
the generator's own identifiers. Labels follow an invented HUMAN class with seeded
noise, and a few slots are made invalid, technically failed or unobserved so that
the missing-data paths show. The input is assembled through the same validated
adapter as any other input and is marked ``data_kind = "synthetic"``.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from .inputs import TaskLevelInput, assemble_input
from .spec import AnalysisSpec

HASH_FIELDS = ("text_sha256", "prompt_sha256", "system_prompt_sha256", "payload_sha256",
               "config_sha256")


def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()


def build_synthetic_input(spec: AnalysisSpec, n_items: int = 60, seed: int = 1,
                          noise: float = 0.12, missing: float = 0.01) -> TaskLevelInput:
    rng = random.Random(seed)
    width = len(str(n_items))
    items = []
    for i in range(1, n_items + 1):
        human = 1 if rng.random() < 0.25 else 0
        items.append({
            "item_id": f"SYN{i:0{width}d}", "text": f"synthetic placeholder campaign {i}",
            "HUMAN": str(human), "success": "1" if rng.random() < (0.6 if human else 0.3) else "0",
            "lgoal": f"{rng.uniform(7, 12):.4f}",
            "subcategory": rng.choice(["alpha", "beta", "gamma", "delta"]),
            "year": str(rng.choice([2010, 2011, 2012])),
        })
    truth = {row["item_id"]: int(row["HUMAN"]) for row in items}
    manifests: dict[str, list[dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    model_ids = {m: f"{m}_synthetic" for m in spec.model_keys}
    va = sorted(spec.va_template_ids)
    for model in spec.model_keys:
        rows = []
        for index, row in enumerate(items):
            item = row["item_id"]
            majority, minority = ("10", "01") if index % 2 else ("01", "10")
            odd = va[index % len(va)]
            plan = [("carlson", t, 1, "") for t in spec.cb_template_ids]
            plan += [("camuffo", t, s, minority if t == odd else majority)
                     for t in spec.va_template_ids for s in range(1, spec.va_generations + 1)]
            for arm, template, sample, order in plan:
                task = {"task_id": f"synthetic__{model}__{template}__s{sample:02d}__{item}",
                        "item_id": item, "model_id": model_ids[model], "arm": arm,
                        "template_id": template, "sample_index": str(sample),
                        "label_order": order, "is_remediation": "False"}
                for name in HASH_FIELDS:
                    task[name] = _digest(name, model, template, item, order)
                rows.append(task)
                record = {k: task[k] for k in ("task_id", "item_id", "model_id", "arm",
                                               "template_id")}
                record.update({"sample_index": sample, "label_order": order or None,
                               "is_remediation": False,
                               **{name: task[name] for name in HASH_FIELDS}})
                draw = rng.random()
                if draw < missing:
                    continue  # planned but unobserved
                if draw < 2 * missing:
                    records.append({**record, "status": "parse_error", "raw_response": "n/a",
                                    "parsed_label": None})
                    continue
                if draw < 3 * missing:
                    records.append({**record, "status": "api_error", "raw_response": None,
                                    "parsed_label": None})
                    continue
                label = truth[item] if rng.random() > noise else 1 - truth[item]
                records.append({**record, "status": "success", "raw_response": str(label),
                                "parsed_label": label})
        manifests[model] = rows
    return assemble_input(spec, items, manifests, model_ids, records, data_kind="synthetic",
                          provenance={"generator": "chapter4_v2.synthetic", "seed": seed,
                                      "n_items": n_items})


__all__ = ["build_synthetic_input"]
