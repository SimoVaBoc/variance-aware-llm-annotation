"""Task-manifest generation for the two-arm comparative experiment.

The generator is deliberately fail-closed. Generating against the real dataset
is refused until every approval gate in the experiment definition is cleared and
every referenced file still hashes to what was recorded. Generation against a
synthetic fixture is allowed while gates are open, because it touches neither
the dataset nor any frozen path, and it is marked as non-definitive in the
metadata so it can never be mistaken for a real manifest.

Nothing here performs network I/O.

Task identity
-------------
``task_id`` joins study, model, template, sample index and item. It deliberately
excludes the analysis arm: the arm is a property of the template, recorded as a
separate field, and an immutable task identifier must not encode an analysis
choice that could later be revised.

What ``payload_sha256`` covers
------------------------------
It hashes the **experimental payload** only: the system message, when the arm
sends one, and the user message. That is the quantity the design cares about,
because it is what must be byte-identical across the S replicates of a cell.

It deliberately does not cover transport or observational fields, which carry no
experimental content and would make the hash change for reasons that have
nothing to do with the treatment. In particular ``usage: {"include": true}``,
which asks OpenRouter to return the credited cost, is accounting and not
generation: it leaves the sampling untouched and must leave the hash untouched
too. The same holds for the model identifier, the provider pin, the output cap
and the temperature, which are recorded as their own manifest columns and are
compared directly rather than through this hash.

Sample counts
-------------
The Carlson arm uses S = 1 by construction: its seven strategies are alternative
configurations, never repeated samples. The Camuffo arm uses the scope's
``camuffo_samples``, which is 3 everywhere except the smoke scope.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .catalog import (
    LABEL_ORDERS,
    CatalogEntry,
    FrozenArtifact,
    build_catalog,
    load_json,
    render_system_prompt,
    require_approved,
    selectable_templates,
    validate_labels,
    validate_rubric,
    verify_anchor_consistency,
    verify_label_order_equivalence,
    verify_qualifier_consistency,
    verify_reference_hashes,
)
from .design import canonical_json_hash, load_items, sha256_bytes, sha256_file


#: Scopes recognised by the generator, in increasing size.
SCOPES = ("smoke", "pilot_deepseek", "pilot_full", "full")

#: The Carlson arm never repeats a strategy. This is a design invariant, not a
#: configurable quantity.
CARLSON_SAMPLES = 1

FIXTURE_MARKER = "fixture"


class ScopeError(ValueError):
    """The requested scope is unknown or inconsistent with the definition."""


class CountMismatch(RuntimeError):
    """The generated manifest does not match the declared expected call count."""


class DefinitiveGenerationRefused(RuntimeError):
    """Real generation was attempted while it is not permitted."""


def _scope_config(experiment: Mapping[str, Any], scope: str) -> dict[str, Any]:
    if scope not in SCOPES:
        raise ScopeError(f"Unknown scope '{scope}'. Known scopes: {', '.join(SCOPES)}")
    scopes = experiment.get("scopes") or {}
    if scope not in scopes:
        raise ScopeError(f"The experiment definition declares no scope '{scope}'")
    return dict(scopes[scope])


def _expected_for_scope(experiment: Mapping[str, Any], scope: str) -> dict[str, int]:
    """Look the declared counts up, tolerating the smoke scope's longer key."""

    expected = experiment.get("expected_calls") or {}
    if scope in expected:
        return dict(expected[scope])
    if scope == "smoke" and "smoke_one_call_per_template" in expected:
        return dict(expected["smoke_one_call_per_template"])
    raise ScopeError(f"The experiment definition declares no expected_calls for '{scope}'")


def models_for_scope(experiment: Mapping[str, Any], scope: str) -> list[dict[str, Any]]:
    wanted = _scope_config(experiment, scope)["models"]
    by_id = {model["id"]: model for model in experiment["models"]}
    missing = [model_id for model_id in wanted if model_id not in by_id]
    if missing:
        raise ScopeError(f"Scope '{scope}' names unknown models: {missing}")
    return [by_id[model_id] for model_id in wanted]


def select_items(
    items: Sequence[Mapping[str, Any]],
    count: int,
    study_id: str,
    text_column: str,
    encoding: str,
) -> list[dict[str, Any]]:
    """Choose ``count`` items deterministically, without reading human labels.

    Selection is by SHA-256 of ``study_id:item_id:text_sha256``, the same rule
    used by the single-arm pipeline, so the two agree on which items are the
    pilot items.
    """

    if count < 1:
        raise ScopeError("An item count must be positive")
    if count > len(items):
        raise ScopeError(f"Scope requests {count} items, but only {len(items)} are available")

    keyed = []
    for item in items:
        text_hash = sha256_bytes(str(item[text_column]).encode(encoding))
        key = sha256_bytes(f"{study_id}:{item['item_id']}:{text_hash}".encode("utf-8"))
        keyed.append((key, dict(item)))
    keyed.sort(key=lambda pair: pair[0])
    chosen = [item for _, item in keyed[:count]]
    return sorted(chosen, key=lambda item: item["item_id"])


def _samples_for(entry: CatalogEntry, camuffo_samples: int) -> int:
    return CARLSON_SAMPLES if entry.arm == "carlson" else camuffo_samples


def _block_digest(study_id: str, model_id: str, item_id: str) -> str:
    """Stable identity of one item-model block, the unit of counterbalancing."""

    return sha256_bytes(f"{study_id}:{model_id}:{item_id}".encode("utf-8"))


def assign_label_orders(
    blocks: Sequence[tuple[str, str, str]],
    variants: Sequence[str],
) -> dict[tuple[str, str, str, str], str]:
    """Counterbalance the label order across cells, never inside one.

    S is a pure replicate: three independent calls with the same prompt, model,
    text and parameters. The label order is therefore a property of the cell
    ``item x model x template``, constant across its S samples, and the
    counterbalancing happens between cells.

    The unit is the block ``item x model``, which holds one cell per paraphrase.
    Blocks are ranked by SHA-256 digest. The first half take ``"10"`` as their
    majority order and the rest ``"01"``; within each block the minority order
    goes to the paraphrase at position ``rank % len(variants)``, so the minority
    rotates through P1, P2 and P3 as the rank advances.

    That rotation is what makes the design balanced in both directions. Over B
    blocks each paraphrase is the minority in exactly ``B / 3`` of them, split
    evenly between the two halves, so every paraphrase receives the two orders
    equally often across items and models. Over the scope the cell counts are
    ``B + D`` against ``2B - D`` with ``D = ceil(B / 2)``: equal for even B, and
    apart by one cell for odd B.
    """

    if len(variants) < 2:
        raise ScopeError("Counterbalancing needs at least two paraphrases")

    ranked = sorted(set(blocks), key=lambda block: _block_digest(*block))
    ordered_variants = sorted(variants)
    midpoint = (len(ranked) + 1) // 2

    assignment: dict[tuple[str, str, str, str], str] = {}
    for rank, (study_id, model_id, item_id) in enumerate(ranked):
        majority, minority = ("10", "01") if rank < midpoint else ("01", "10")
        minority_index = rank % len(ordered_variants)
        for index, template_id in enumerate(ordered_variants):
            order = minority if index == minority_index else majority
            assignment[(study_id, model_id, template_id, item_id)] = order
    return assignment


def label_order_balance(tasks: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count the two orders over the Camuffo tasks."""

    counts = {order: 0 for order in LABEL_ORDERS}
    for task in tasks:
        order = task.get("label_order")
        if order in counts:
            counts[order] += 1
    return counts


def assemble_payload(
    entry: CatalogEntry,
    text: str,
    system_instruction: str | None = None,
    delimiter: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Build the exact message pair that would be sent for this template.

    The Camuffo arm carries the shared system instruction and wraps the campaign
    text in the shared delimiter, because that text is untrusted third-party
    content that may contain imperative language. Delimiter and text position
    are identical across the three paraphrases, so neither is part of the P
    variation.

    The Carlson arm sends the published prompt as a single user message, with no
    system instruction and no delimiter: the paper's strategies carry their own
    framing, and adding either would alter the replication.
    """

    if entry.arm != "camuffo":
        return {"system": None, "user": f"{entry.text}\n\n{text}"}
    if not delimiter:
        raise ScopeError(
            "The Camuffo arm requires the shared campaign-text delimiter; "
            "assembling without it would send untrusted text unmarked."
        )
    body = f"{delimiter['open']}\n{text}\n{delimiter['close']}"
    return {"system": system_instruction, "user": f"{entry.text}\n\n{body}"}


def build_tasks(
    experiment: Mapping[str, Any],
    catalog: Sequence[CatalogEntry],
    items: Sequence[Mapping[str, Any]],
    scope: str,
    rendered_system_prompts: Mapping[str, Mapping[str, str]] | None = None,
    delimiters: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Produce one task record per planned call, in a deterministic order.

    ``rendered_system_prompts`` maps a prompt set to its two label-order
    renderings. The Camuffo arm draws from it; the Carlson arm sends no system
    prompt at all.
    """

    scope_config = _scope_config(experiment, scope)
    camuffo_samples = int(scope_config["camuffo_samples"])
    models = models_for_scope(experiment, scope)
    templates = selectable_templates(catalog)
    if not templates:
        raise ScopeError("The catalogue contains no selectable template")

    dataset = experiment["dataset"]
    text_column = dataset["text_column"]
    encoding = dataset["encoding"]
    study_id = experiment["study_id"]
    experiment_id = experiment["experiment_id"]
    config_hash = canonical_json_hash(experiment)
    renderings = dict(rendered_system_prompts or {})
    marks = dict(delimiters or {})
    caps = {arm: (spec or {}).get("max_output_tokens") for arm, spec in experiment["arms"].items()}
    temperature_status = (experiment.get("temperature_policy") or {}).get("primary", {}).get(
        "status"
    )

    # Counterbalance the label order over the Camuffo cells only, and between
    # cells rather than inside one, so that S stays a pure replicate. The seven
    # Carlson prompts are canonical transcriptions and are never reordered.
    camuffo_variants = sorted(
        entry.template_id for entry in templates if entry.arm == "camuffo"
    )
    camuffo_blocks = [
        (study_id, model["id"], str(item["item_id"]))
        for model in models
        for item in items
    ]
    orders = assign_label_orders(camuffo_blocks, camuffo_variants)
    temperatures = {
        arm: (spec or {}).get("temperature_requested")
        for arm, spec in experiment["arms"].items()
    }
    temperature_policy = (experiment.get("temperature_policy") or {}).get("primary", {})

    tasks: list[dict[str, Any]] = []
    for model in models:
        for entry in templates:
            for sample in range(1, _samples_for(entry, camuffo_samples) + 1):
                for item in items:
                    item_id = str(item["item_id"])
                    text = str(item[text_column])

                    if entry.arm == "camuffo":
                        # One order per cell, so every S replicate of this cell
                        # sends a byte-identical payload.
                        cell = (study_id, model["id"], entry.template_id, item_id)
                        label_order = orders[cell]
                        system = renderings[entry.prompt_set_id][label_order]
                        system_hash = sha256_bytes(system.encode("utf-8"))
                    else:
                        label_order = None
                        system = None
                        system_hash = None

                    payload = assemble_payload(
                        entry, text, system, marks.get(entry.prompt_set_id)
                    )
                    payload_hash = canonical_json_hash(payload)
                    task_id = "__".join(
                        (
                            study_id,
                            model["id"],
                            entry.template_id,
                            f"s{sample:02d}",
                            item_id,
                        )
                    )
                    tasks.append(
                        {
                            "task_id": task_id,
                            "study_id": study_id,
                            "experiment_id": experiment_id,
                            "scope": scope,
                            "item_id": item_id,
                            "model_id": model["id"],
                            "provider": model["provider"],
                            "api_route": model.get("api_route") or model["provider"],
                            "api_model_requested": model["api_model"],
                            "arm": entry.arm,
                            "prompt_set_id": entry.prompt_set_id,
                            "template_id": entry.template_id,
                            "carlson_strategy_id": entry.carlson_strategy_id,
                            "camuffo_variant_id": entry.camuffo_variant_id,
                            "sample_index": sample,
                            "label_order": label_order,
                            "text_sha256": sha256_bytes(text.encode(encoding)),
                            "prompt_sha256": entry.prompt_sha256,
                            "system_template_sha256": entry.system_template_sha256,
                            "system_prompt_sha256": system_hash,
                            "payload_sha256": payload_hash,
                            "config_sha256": config_hash,
                            "response_contract": entry.response_contract,
                            "max_output_tokens": caps.get(entry.arm),
                            # The primary policy is approach-faithful: the
                            # Carlson arm asks for 0 as the paper reports, the
                            # Camuffo arm for 1 so that the S replicates are
                            # informative. Where a provider does not allow the
                            # control, the runner omits the parameter rather
                            # than simulating it.
                            "temperature_requested": temperatures.get(entry.arm),
                            "temperature_policy": temperature_policy.get("id"),
                            "temperature_policy_status": temperature_status,
                            # Every manifest row is a planned primary
                            # observation. Marking it here means any later
                            # remediation record is distinguishable by
                            # construction rather than by convention.
                            "is_remediation": False,
                        }
                    )

    task_ids = [task["task_id"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise CountMismatch("Task IDs are not unique")
    return tasks


def verify_counterbalancing(
    tasks: Sequence[Mapping[str, Any]],
    camuffo_samples: int,
) -> dict[str, Any]:
    """Check every counterbalancing guarantee on a generated manifest.

    The first check is the one the design turns on: S must be a pure replicate,
    so the S calls of a cell must share one label order and one payload. The
    rest establish that the two orders are then balanced between cells, inside
    each item-model block, and across each paraphrase.
    """

    camuffo = [task for task in tasks if task["arm"] == "camuffo"]
    problems: list[str] = []

    for task in tasks:
        if task["arm"] == "carlson" and task["label_order"] is not None:
            problems.append(f"{task['task_id']} is a Carlson task carrying a label order")
        if task["arm"] == "camuffo" and task["label_order"] not in LABEL_ORDERS:
            problems.append(f"{task['task_id']} has label_order {task['label_order']!r}")

    # S is a pure replicate: one order and one payload per cell.
    cells: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for task in camuffo:
        key = (task["model_id"], task["template_id"], task["item_id"])
        cells.setdefault(key, []).append(task)
    for key, rows in sorted(cells.items()):
        if len({row["label_order"] for row in rows}) != 1:
            problems.append(f"cell {key} varies its label order across S")
        if len({row["payload_sha256"] for row in rows}) != 1:
            problems.append(f"cell {key} varies its payload across S")
        if len(rows) != camuffo_samples:
            problems.append(f"cell {key} has {len(rows)} samples, expected {camuffo_samples}")

    # Both orders appear inside each item-model block, across the paraphrases.
    blocks: dict[tuple[str, str], set[str]] = {}
    for key, rows in cells.items():
        model_id, _, item_id = key
        blocks.setdefault((model_id, item_id), set()).add(rows[0]["label_order"])
    variants = sorted({key[1] for key in cells})
    if len(variants) >= 2:
        for key, seen in sorted(blocks.items()):
            if seen != set(LABEL_ORDERS):
                problems.append(f"block {key} carries only {sorted(seen)} across its paraphrases")

    # Each paraphrase receives both orders evenly across items and models.
    per_variant: dict[str, dict[str, int]] = {
        variant: {order: 0 for order in LABEL_ORDERS} for variant in variants
    }
    for key, rows in cells.items():
        per_variant[key[1]][rows[0]["label_order"]] += 1
    n_blocks = len(blocks)
    variant_tolerance = 1 if n_blocks % len(variants or [1]) else 0
    for variant, counts in sorted(per_variant.items()):
        if abs(counts["10"] - counts["01"]) > max(variant_tolerance, n_blocks % 2):
            problems.append(f"paraphrase {variant} is skewed: {counts}")

    # Cell-level balance over the whole scope.
    cell_balance = {order: 0 for order in LABEL_ORDERS}
    for rows in cells.values():
        cell_balance[rows[0]["label_order"]] += 1
    cell_spread = abs(cell_balance["10"] - cell_balance["01"])
    if cell_spread > (1 if n_blocks % 2 else 0):
        problems.append(
            f"the two orders differ by {cell_spread} cells over {len(cells)}; "
            "the tolerance is one cell"
        )

    balance = label_order_balance(camuffo)
    if problems:
        raise CountMismatch("Counterbalancing is not satisfied:\n- " + "\n- ".join(problems))
    return {
        "balance": balance,
        "spread": abs(balance["10"] - balance["01"]),
        "cell_balance": cell_balance,
        "cell_spread": cell_spread,
        "n_cells": len(cells),
        "n_blocks": n_blocks,
        "per_variant": per_variant,
    }


def count_by_arm(tasks: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    total = 0
    for task in tasks:
        counts[task["arm"]] = counts.get(task["arm"], 0) + 1
        total += 1
    counts["total"] = total
    return counts


def verify_counts(experiment: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]], scope: str) -> dict[str, int]:
    """Check the generated manifest against the counts declared in the config."""

    expected = _expected_for_scope(experiment, scope)
    observed = count_by_arm(tasks)
    for arm in sorted(set(expected) | set(observed)):
        if expected.get(arm, 0) != observed.get(arm, 0):
            raise CountMismatch(
                f"Scope '{scope}' expected {expected} but generated {observed}"
            )
    return observed


def cross_arm_payload_collisions(tasks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Report payloads identical across the two arms, without acting on them.

    Sharing is disabled in the current design. A collision would be a candidate
    for sharing, never an automatic one, so this only reports.
    """

    seen: dict[str, set[str]] = {}
    for task in tasks:
        seen.setdefault(task["payload_sha256"], set()).add(task["arm"])
    return sorted(digest for digest, arms in seen.items() if len(arms) > 1)


def generate(
    experiment: Mapping[str, Any],
    scope: str,
    project_root: str | Path = ".",
    items: Sequence[Mapping[str, Any]] | None = None,
    definitive: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate a manifest for ``scope``.

    With ``definitive=False`` (the default) ``items`` must be supplied: this is
    fixture generation, permitted while approval gates are open. With
    ``definitive=True`` the real dataset is read, and every gate must be clear.
    """

    root = Path(project_root)
    scope_config = _scope_config(experiment, scope)

    if definitive:
        if items is not None:
            raise DefinitiveGenerationRefused(
                "Definitive generation reads the real dataset and refuses injected items."
            )
        require_approved(experiment)
        verify_reference_hashes(experiment, root)
        pool = load_items(dict(experiment), root)
        items = select_items(
            pool,
            int(scope_config["items"]),
            experiment["study_id"],
            experiment["dataset"]["text_column"],
            experiment["dataset"]["encoding"],
        )
    else:
        if items is None:
            raise ScopeError(
                "Fixture generation requires synthetic items. Pass items=..., or "
                "call with definitive=True once the approval gates are cleared."
            )
        if len(items) != int(scope_config["items"]):
            raise ScopeError(
                f"Scope '{scope}' plans {scope_config['items']} items, "
                f"but {len(items)} fixture items were supplied"
            )

    catalog = build_catalog(experiment, root, include_unapproved=not definitive)

    references = experiment["references"]
    rubric = load_json(root / references["rubric"]["file"])
    labels = load_json(root / references["labels"]["file"])
    camuffo = load_json(root / references["camuffo_prompts"]["file"])

    # The three files must agree before a single task is planned: one wording of
    # the construct, one set of anchors, and the corrected retry contract.
    validate_rubric(rubric)
    validate_labels(labels)
    verify_qualifier_consistency(rubric, labels, camuffo)
    verify_anchor_consistency(rubric, camuffo)

    verify_label_order_equivalence(camuffo)
    renderings = {
        camuffo["prompt_set_id"]: {
            order: render_system_prompt(camuffo, order) for order in LABEL_ORDERS
        }
    }
    delimiters = {camuffo["prompt_set_id"]: camuffo["assembly"]["delimiter"]}

    tasks = build_tasks(
        experiment,
        catalog,
        items,
        scope,
        rendered_system_prompts=renderings,
        delimiters=delimiters,
    )
    observed = verify_counts(experiment, tasks, scope)
    counterbalance = verify_counterbalancing(tasks, int(scope_config["camuffo_samples"]))
    temperature_policy = (experiment.get("temperature_policy") or {}).get("primary", {})

    metadata = {
        "experiment_id": experiment["experiment_id"],
        "study_id": experiment["study_id"],
        "scope": scope,
        "definitive": bool(definitive),
        "source": "real_dataset" if definitive else "synthetic_fixture",
        "config_sha256": canonical_json_hash(experiment),
        "n_items": len(items),
        "n_models": len(models_for_scope(experiment, scope)),
        "n_selectable_templates": len(selectable_templates(catalog)),
        "n_tasks": len(tasks),
        "counts_by_arm": observed,
        "expected_counts": _expected_for_scope(experiment, scope),
        "cross_arm_payload_collisions": cross_arm_payload_collisions(tasks),
        "live_calls_enabled": experiment["execution"]["live_calls_enabled"],
        "sharing_enabled": experiment["sharing"]["enabled"],
        # Manifest-level, not per row: these hold for every task, so repeating
        # them on 12,000 rows would add bulk without adding information.
        "camuffo_delimiter": dict(delimiters[camuffo["prompt_set_id"]]),
        "max_output_tokens_by_arm": {
            arm: (spec or {}).get("max_output_tokens") for arm, spec in experiment["arms"].items()
        },
        "temperature_policy": temperature_policy.get("id"),
        "temperature_policy_status": temperature_policy.get("status"),
        "counterbalancing": {
            "scope": "camuffo_arm_only",
            "unit": "cell (item x model x template); constant across S",
            "label_orders": list(LABEL_ORDERS),
            "calls_balance": counterbalance["balance"],
            "calls_spread": counterbalance["spread"],
            "cell_balance": counterbalance["cell_balance"],
            "cell_spread": counterbalance["cell_spread"],
            "n_cells": counterbalance["n_cells"],
            "n_blocks": counterbalance["n_blocks"],
            "per_variant": counterbalance["per_variant"],
            "s_is_a_pure_replicate": True,
            "both_orders_in_every_block": True,
            "system_prompt_sha256_by_order": {
                order: sha256_bytes(rendered.encode("utf-8"))
                for order, rendered in renderings[camuffo["prompt_set_id"]].items()
            },
        },
        "temperature_by_arm": {
            arm: (spec or {}).get("temperature_requested")
            for arm, spec in experiment["arms"].items()
        },
        "sample_slot_policy": {
            "one_planned_slot_per_task_id": True,
            "slot_consuming_statuses": labels["retry_policy_contract"]["slot_consuming_statuses"],
            "sample_bearing_statuses": labels["retry_policy_contract"]["sample_bearing_statuses"],
            "parse_error_is_retried_automatically": False,
            "parse_error_is_replaced_automatically": False,
            "note": "A parse_error occupies its planned slot and yields no label. "
            "The slot is never refilled by a new call.",
        },
    }
    if definitive:
        metadata["dataset_sha256"] = sha256_file(root / experiment["dataset"]["path"])
        metadata["selected_item_ids"] = [str(item["item_id"]) for item in items]
    else:
        metadata["warning"] = (
            "SYNTHETIC FIXTURE. Generated from invented items while approval gates "
            "are open. It is not a manifest of the experiment and must never be executed."
        )

    return tasks, metadata


def write_manifest(
    tasks: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    csv_path: str | Path,
) -> tuple[Path, Path]:
    """Write the manifest and its metadata, refusing to clobber either file.

    A non-definitive bundle must be written to a path whose name marks it as a
    fixture, so a synthetic manifest cannot end up occupying a real filename.
    """

    target = Path(csv_path)
    if not metadata.get("definitive") and FIXTURE_MARKER not in target.name.lower():
        raise DefinitiveGenerationRefused(
            f"A synthetic-fixture manifest must be written to a filename containing "
            f"'{FIXTURE_MARKER}'; refused for {target.name}."
        )
    metadata_path = target.with_suffix(".meta.json")
    for path in (target, metadata_path):
        if path.exists():
            raise FrozenArtifact(
                f"{path} already exists. Frozen artifacts are never overwritten; "
                "create a new version instead."
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tasks[0].keys()))
        writer.writeheader()
        writer.writerows(tasks)
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(metadata), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return target, metadata_path


__all__ = [
    "CARLSON_SAMPLES",
    "CountMismatch",
    "DefinitiveGenerationRefused",
    "SCOPES",
    "ScopeError",
    "assemble_payload",
    "assign_label_orders",
    "build_tasks",
    "count_by_arm",
    "cross_arm_payload_collisions",
    "generate",
    "label_order_balance",
    "models_for_scope",
    "select_items",
    "verify_counterbalancing",
    "verify_counts",
    "write_manifest",
]
