"""Execution for the two-arm comparative manifest.

This is a separate path from :func:`src.chapter3.execution.run_manifest`, which
keeps serving the frozen single-arm design and is not touched. The two schemas
are genuinely different, and translating one into the other silently is exactly
the kind of quiet coercion the design forbids:

* the two-arm manifest names ``arm``, ``template_id`` and ``sample_index``;
* the single-arm manifest names ``prompt_id`` and ``replicate_id``.

No implicit conversion is performed in either direction. A row that does not
carry the two-arm columns is refused.

Everything is verified before a single call leaves the process: approval gates,
referenced-file hashes, the catalogue, and each row's own prompt, system-prompt,
text and payload hashes. If anything has drifted, the run refuses to start
rather than spending money against a manifest that no longer describes what is
on disk.

Per-call settings come from the row, because the two arms differ: the Camuffo
arm caps output at one token and asks for temperature 1, the Carlson arm caps at
sixteen and asks for temperature 0.
"""

from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .catalog import (
    LABEL_ORDERS,
    CatalogEntry,
    build_catalog,
    load_json,
    render_system_prompt,
    require_approved,
    selectable_templates,
    verify_approval_consistency,
    verify_reference_hashes,
)
from .design import canonical_json_hash, load_items, sha256_bytes
from .execution import (
    SLOT_CONSUMING_STATUSES,
    STATUS_DRY_RUN,
    STATUS_PARSE_ERROR,
    STATUS_SUCCESS,
    BudgetExceeded,
    BudgetPolicy,
    ExecutionBlocked,
    RetryPolicy,
    RunSummary,
    append_record,
    collect_blockers,
    execute_task,
    load_completed_task_ids,
    max_output_tokens_for,
    read_manifest,
    reasoning_config_from,
    requested_provider_from,
    route_for,
    temperature_for,
    utc_now_iso,
)
from .manifest import assemble_payload
from .providers import ProviderAdapter, ProviderRequest, temperature_on_the_wire


#: Columns that identify a two-arm manifest. A manifest missing any of them is
#: not one, and is refused rather than coerced.
TWO_ARM_COLUMNS = frozenset(
    {
        "task_id",
        "arm",
        "template_id",
        "sample_index",
        "label_order",
        "max_output_tokens",
        "temperature_requested",
        "prompt_sha256",
        "system_prompt_sha256",
        "payload_sha256",
        "text_sha256",
        "config_sha256",
    }
)

#: Columns that belong to the single-arm schema and must never appear here.
LEGACY_ONLY_COLUMNS = frozenset({"prompt_id", "replicate_id"})

ARMS = frozenset({"camuffo", "carlson"})


class ManifestSchemaError(ExecutionBlocked):
    """The manifest is not a two-arm manifest."""


class ManifestDrift(ExecutionBlocked):
    """A manifest row no longer matches the configuration it was built from."""


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def verify_schema(rows: Sequence[Mapping[str, Any]]) -> None:
    """Refuse anything that is not a two-arm manifest, without converting."""

    if not rows:
        raise ManifestSchemaError("The manifest contains no rows")

    columns = set(rows[0])
    missing = TWO_ARM_COLUMNS - columns
    if missing:
        raise ManifestSchemaError(
            "This is not a two-arm manifest; it is missing "
            f"{sorted(missing)}. The single-arm design is served by "
            "src.chapter3.execution.run_manifest, and the two schemas are never "
            "translated into each other."
        )
    legacy = LEGACY_ONLY_COLUMNS & columns
    if legacy:
        raise ManifestSchemaError(
            f"This manifest carries single-arm columns {sorted(legacy)}. "
            "Mixing the two schemas is refused."
        )

    problems: list[str] = []
    for row in rows:
        if row["arm"] not in ARMS:
            problems.append(f"{row['task_id']}: unknown arm {row['arm']!r}")
        if row["arm"] == "camuffo" and row["label_order"] not in LABEL_ORDERS:
            problems.append(f"{row['task_id']}: camuffo row without a label order")
        if row["arm"] == "carlson" and not _blank(row["label_order"]):
            problems.append(f"{row['task_id']}: carlson row carries a label order")
        try:
            int(row["sample_index"])
        except (TypeError, ValueError):
            problems.append(f"{row['task_id']}: sample_index {row['sample_index']!r}")
    if problems:
        raise ManifestSchemaError("Invalid two-arm rows:\n- " + "\n- ".join(problems))


def verify_rows_against_config(
    rows: Sequence[Mapping[str, Any]],
    experiment: Mapping[str, Any],
    project_root: str | Path = ".",
) -> dict[str, CatalogEntry]:
    """Re-derive every hash in the manifest and refuse any drift.

    This is what stands between a stale manifest and a paid run. Each row is
    checked against the catalogue built from the current configuration, and
    against the dataset as it is on disk right now.
    """

    root = Path(project_root)
    require_approved(experiment)
    verify_reference_hashes(experiment, root)
    verify_approval_consistency(experiment, root)

    catalog = {entry.template_id: entry for entry in selectable_templates(
        build_catalog(experiment, root)
    )}
    camuffo = load_json(root / experiment["references"]["camuffo_prompts"]["file"])
    renderings = {order: render_system_prompt(camuffo, order) for order in LABEL_ORDERS}
    system_hashes = {
        order: sha256_bytes(text.encode("utf-8")) for order, text in renderings.items()
    }
    delimiter = camuffo["assembly"]["delimiter"]

    items = {row["item_id"]: row for row in load_items(dict(experiment), root)}
    text_column = experiment["dataset"]["text_column"]
    encoding = experiment["dataset"]["encoding"]
    config_hash = canonical_json_hash(experiment)

    problems: list[str] = []
    for row in rows:
        task_id = row["task_id"]
        if row["config_sha256"] != config_hash:
            problems.append(f"{task_id}: config hash has drifted")
            continue

        entry = catalog.get(row["template_id"])
        if entry is None:
            problems.append(f"{task_id}: template {row['template_id']!r} is not selectable")
            continue
        if entry.arm != row["arm"]:
            problems.append(f"{task_id}: template belongs to arm {entry.arm!r}")
            continue
        if entry.prompt_sha256 != row["prompt_sha256"]:
            problems.append(f"{task_id}: prompt text has changed since the manifest was built")
            continue

        item = items.get(row["item_id"])
        if item is None:
            problems.append(f"{task_id}: item {row['item_id']!r} is not in the dataset")
            continue
        text = str(item[text_column])
        if sha256_bytes(text.encode(encoding)) != row["text_sha256"]:
            problems.append(f"{task_id}: campaign text has changed")
            continue

        if row["arm"] == "camuffo":
            order = row["label_order"]
            if row["system_prompt_sha256"] != system_hashes[order]:
                problems.append(f"{task_id}: rendered system prompt has changed")
                continue
            system: str | None = renderings[order]
        else:
            if not _blank(row["system_prompt_sha256"]):
                problems.append(f"{task_id}: carlson row carries a system prompt hash")
                continue
            system = None

        payload = assemble_payload(entry, text, system, delimiter)
        if canonical_json_hash(payload) != row["payload_sha256"]:
            problems.append(f"{task_id}: payload hash does not reproduce")

    if problems:
        raise ManifestDrift(
            "The manifest no longer matches the configuration:\n- "
            + "\n- ".join(problems[:20])
            + ("\n- ..." if len(problems) > 20 else "")
            + "\nRefusing to run. Rebuild the manifest as a new version."
        )
    return catalog


def build_request(
    row: Mapping[str, Any],
    entry: CatalogEntry,
    model: Mapping[str, Any],
    text: str,
    system: str | None,
    delimiter: Mapping[str, str],
) -> ProviderRequest:
    """Compose one request, taking the per-call settings from the row."""

    settings = dict(model.get("request_settings") or {})
    messages = assemble_payload(entry, text, system, delimiter)
    return ProviderRequest(
        api_model=model["api_model"],
        system_prompt=messages["system"],
        user_prompt=messages["user"],
        max_output_tokens=max_output_tokens_for(row, settings),
        temperature=temperature_for(row, settings),
        settings=settings,
    )


def run_two_arm_manifest(
    *,
    experiment: Mapping[str, Any],
    manifest_path: str | Path,
    output_path: str | Path,
    project_root: str | Path = ".",
    live: bool = False,
    budget: BudgetPolicy | None = None,
    adapter_factory: Callable[[str], ProviderAdapter] | None = None,
    retry_policy: RetryPolicy | None = None,
    resume: bool = True,
    limit: int | None = None,
    model_ids: Iterable[str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter_source: Callable[[], float] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> RunSummary:
    """Execute a two-arm manifest, dry by default.

    ``live=False`` never constructs a client and never calls ``adapter_factory``.
    A live run additionally requires an explicit budget cap and a configuration
    whose gates are all clear.
    """

    retry_policy = retry_policy or RetryPolicy()
    jitter_source = jitter_source or random.random
    root = Path(project_root)
    summary = RunSummary(mode="two_arm", live=live, output_path=str(output_path))

    rows = read_manifest(manifest_path)
    verify_schema(rows)
    catalog = verify_rows_against_config(rows, experiment, root)

    if model_ids is not None:
        wanted = set(model_ids)
        unknown = wanted - {model["id"] for model in experiment["models"]}
        if unknown:
            raise ExecutionBlocked(f"Unknown model ids: {sorted(unknown)}")
        rows = [row for row in rows if row["model_id"] in wanted]
        if not rows:
            raise ExecutionBlocked(f"No manifest row matches model ids {sorted(wanted)}")

    summary.tasks_in_manifest = len(rows)
    blockers = collect_blockers(experiment, {row["model_id"] for row in rows})
    summary.blockers = list(blockers)

    if live:
        if budget is None:
            raise ExecutionBlocked(
                "A live run requires an explicit hard budget cap. Live execution "
                "is disabled by default."
            )
        if experiment.get("execution", {}).get("live_calls_enabled") is not False:
            raise ExecutionBlocked(
                "The configuration must keep live_calls_enabled false; the live "
                "flag is supplied per run, not stored in the design file."
            )
        if adapter_factory is None:
            raise ExecutionBlocked("A live run requires an adapter factory")
        if blockers:
            raise ExecutionBlocked(
                "Live execution is blocked by unresolved gates:\n- " + "\n- ".join(blockers)
            )

    completed_statuses = (
        SLOT_CONSUMING_STATUSES if live else SLOT_CONSUMING_STATUSES | {STATUS_DRY_RUN}
    )
    completed = load_completed_task_ids(output_path, completed_statuses) if resume else set()
    pending = [row for row in rows if row["task_id"] not in completed]
    summary.already_complete = len(rows) - len(pending)
    if limit is not None:
        pending = pending[:limit]

    if live and budget is not None and len(pending) > budget.max_calls:
        raise BudgetExceeded(
            f"This run would send {len(pending)} calls, exceeding the hard cap of "
            f"{budget.max_calls}."
        )

    camuffo = load_json(root / experiment["references"]["camuffo_prompts"]["file"])
    renderings = {order: render_system_prompt(camuffo, order) for order in LABEL_ORDERS}
    delimiter = camuffo["assembly"]["delimiter"]
    items = {row["item_id"]: row for row in load_items(dict(experiment), root)}
    models = {model["id"]: model for model in experiment["models"]}
    text_column = experiment["dataset"]["text_column"]

    adapters: dict[str, ProviderAdapter] = {}

    for row in pending:
        entry = catalog[row["template_id"]]
        model = models[row["model_id"]]
        text = str(items[row["item_id"]][text_column])
        system = renderings[row["label_order"]] if row["arm"] == "camuffo" else None
        request = build_request(row, entry, model, text, system, delimiter)
        route = route_for(model)

        if not live:
            started_at = utc_now_iso(clock)
            settings = dict(model.get("request_settings") or {})
            record = {
                "task_id": row["task_id"],
                "study_id": row.get("study_id"),
                "experiment_id": row.get("experiment_id"),
                "item_id": row["item_id"],
                "model_id": row["model_id"],
                "arm": row["arm"],
                "template_id": row["template_id"],
                "sample_index": int(row["sample_index"]),
                "label_order": row["label_order"] or None,
                "api_model_requested": row["api_model_requested"],
                "api_model_returned": None,
                "provider": row["provider"],
                "api_route": route,
                "requested_provider": requested_provider_from(settings),
                "upstream_provider": None,
                "status": STATUS_DRY_RUN,
                "parsed_label": None,
                "raw_response": None,
                "started_at_utc": started_at,
                "completed_at_utc": started_at,
                "latency_ms": 0,
                "attempt_count": 0,
                "retry_count": 0,
                "counts_as_sample": False,
                "slot_consumed": False,
                "is_remediation": False,
                "max_output_tokens": request.max_output_tokens,
                "temperature_requested": request.temperature,
                "temperature_parameter_sent": temperature_on_the_wire(request),
                "reasoning_config_sent": reasoning_config_from(settings),
                "finish_reason": None,
                "finish_reason_reported": False,
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "reasoning_tokens_reported": False,
                "cost": None,
                "cost_reported": False,
                "error_type": None,
                "error_message": None,
                # No request is made, so there is no transport status to record.
                "http_status": None,
                "text_sha256": row["text_sha256"],
                "prompt_sha256": row["prompt_sha256"],
                "system_prompt_sha256": row["system_prompt_sha256"] or None,
                "payload_sha256": row["payload_sha256"],
                "config_sha256": row["config_sha256"],
                "planned_request_body": self_describing_body(request, route),
                "blockers": blockers,
            }
            append_record(output_path, record)
            summary.dry_run_records += 1
            summary.attempted += 1
            continue

        if route not in adapters:
            adapters[route] = adapter_factory(route)  # type: ignore[misc]

        record = execute_task(
            row,
            adapters[route],
            request,
            retry_policy=retry_policy,
            sleep=sleep,
            jitter_source=jitter_source,
            clock=clock,
            base_record=two_arm_base_record(row, route),
        )
        append_record(output_path, record)

        summary.attempted += 1
        summary.provider_calls += int(record.get("attempt_count") or 0)
        summary.retries += int(record.get("retry_count") or 0)
        if record["status"] == STATUS_SUCCESS:
            summary.succeeded += 1
        elif record["status"] == STATUS_PARSE_ERROR:
            summary.parse_errors += 1
        else:
            summary.api_errors += 1

    return summary


def two_arm_base_record(row: Mapping[str, Any], route: str) -> dict[str, Any]:
    """Seed a result record from the two-arm columns.

    Deliberately spelled in the two-arm vocabulary. Nothing here is renamed into
    ``prompt_id`` or ``replicate_id``: the two manifests are different objects
    and are kept that way in the logs as well.
    """

    return {
        "task_id": row["task_id"],
        "study_id": row.get("study_id"),
        "experiment_id": row.get("experiment_id"),
        "item_id": row["item_id"],
        "model_id": row["model_id"],
        "arm": row["arm"],
        "template_id": row["template_id"],
        "sample_index": int(row["sample_index"]),
        "label_order": row["label_order"] or None,
        "carlson_strategy_id": row.get("carlson_strategy_id") or None,
        "camuffo_variant_id": row.get("camuffo_variant_id") or None,
        "api_model_requested": row["api_model_requested"],
        "provider": row["provider"],
        "api_route": route,
        "text_sha256": row["text_sha256"],
        "prompt_sha256": row["prompt_sha256"],
        "system_prompt_sha256": row["system_prompt_sha256"] or None,
        "payload_sha256": row["payload_sha256"],
        "config_sha256": row["config_sha256"],
        "response_contract": row.get("response_contract"),
        "is_remediation": False,
    }


def self_describing_body(request: ProviderRequest, route: str) -> dict[str, Any]:
    """The request body a dry run records, so the plan can be inspected.

    Only the shape is recorded, not the campaign text, which is already hashed
    in the row and would otherwise be duplicated across every log line.
    """

    return {
        "route": route,
        "model": request.api_model,
        "has_system_message": request.system_prompt is not None,
        "n_messages": 1 if request.system_prompt is None else 2,
        "max_tokens": request.max_output_tokens,
        "temperature": temperature_on_the_wire(request),
        "temperature_requested": request.temperature,
        "system_prompt_chars": len(request.system_prompt or ""),
        "user_prompt_chars": len(request.user_prompt),
    }


__all__ = [
    "ARMS",
    "LEGACY_ONLY_COLUMNS",
    "TWO_ARM_COLUMNS",
    "ManifestDrift",
    "ManifestSchemaError",
    "build_request",
    "run_two_arm_manifest",
    "self_describing_body",
    "two_arm_base_record",
    "verify_rows_against_config",
    "verify_schema",
]
