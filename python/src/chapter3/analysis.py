"""Assemble analytic observations from an append-only two-arm run log.

The log is a technical record, not an analytic dataset. One ``task_id`` can
appear several times: a technical failure leaves an ``api_error`` record, and a
later resume appends the completion. This module turns that history into
exactly one analytic observation per planned task, and keeps the history in an
audit trail rather than discarding it.

Three rules govern the translation, and all three fail closed:

* **One terminal record per task.** Only a status that consumes the sample slot
  is an observation. An ``api_error`` is technical history; it is never an
  observation, and never a label. A task with no terminal record, or with more
  than one, raises rather than being silently resolved.
* **Nothing is substituted.** A ``parse_error`` carries no label and is not
  replaced. A missing label stays missing and propagates as ``None``. An error
  is never read as a negative label.
* **The manifest is the authority.** The terminal observations must correspond
  one-to-one with the manifest rows, and every recorded hash, routing field and
  per-call setting must match what was planned. Anything else is drift.

Nothing here is specific to one model or one scope. The same functions serve
the DeepSeek pilot, the three-model pilot and the full sample; what changes is
the manifest handed in.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .design import load_items
from .execution import SLOT_CONSUMING_STATUSES, STATUS_SUCCESS
from .hierarchy import (
    MINIMUM_VALID_CONTRIBUTIONS,
    aggregate_models,
    aggregate_prompts,
    aggregate_samples,
    valid_label,
)


#: Written into the metadata of every run, so a dataset states which rules
#: produced it. Bump it when the assembly rules change, never for a bug fix
#: that leaves the output identical.
PIPELINE_VERSION = "chapter3_analysis_v2"

#: The model level needs at least two valid model-level contributions. With one
#: model it is not a null, not a zero and not a missing value: it is a level
#: that does not exist yet, and it says so in its own words.
MODEL_LEVEL_UNAVAILABLE = "not_available_insufficient_models"

#: Record fields that must never reach a derived dataset. The raw log stays the
#: single audit source for them. ``error_message`` carries the provider's own
#: text, which has been observed to contain an upstream account identifier;
#: ``provider_request_id`` and ``system_fingerprint`` are transport identifiers
#: with no analytic content.
WITHHELD_FIELDS = frozenset(
    {
        "error_message",
        "provider_request_id",
        "system_fingerprint",
        "request_settings",
        "raw_response",
    }
)

#: Patterns that must not appear in any derived output. Checked, not assumed.
SENSITIVE_PATTERNS = (
    re.compile(r"\buser_[A-Za-z0-9]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\bgen-\d{6,}-[A-Za-z0-9]{6,}"),
    re.compile(r"OPENROUTER_API_KEY\s*=\s*\S+"),
)

#: Covariates carried into every analytic dataset. The campaign text itself is
#: not carried: it is large, it is already frozen in the dataset file, and its
#: digest identifies it exactly.
COVARIATES = ("HUMAN", "success", "lgoal", "subcategory", "year")

#: Manifest fields that must reproduce on the terminal record.
IDENTITY_FIELDS = ("arm", "item_id", "model_id", "template_id")
HASH_FIELDS = ("text_sha256", "prompt_sha256", "system_prompt_sha256", "payload_sha256",
               "config_sha256")


class AnalysisError(RuntimeError):
    """The log and the manifest do not describe the same run."""


class TerminalizationError(AnalysisError):
    """A task has no terminal observation, or more than one."""


class ManifestMismatch(AnalysisError):
    """The terminal observations do not correspond to the manifest."""


class LeakCheckFailed(AnalysisError):
    """A derived output carries something that must stay in the raw log."""


@dataclass
class Terminalization:
    """One analytic observation per task, plus the history behind it."""

    terminal: dict[str, dict[str, Any]]
    superseded: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 1. terminalization
# --------------------------------------------------------------------------


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def summarise_error(record: Mapping[str, Any]) -> dict[str, Any]:
    """Describe a technical failure without copying the provider's text.

    The provider's message has been observed to embed an upstream account
    identifier, so it is never carried out of the raw log. The HTTP status and
    the machine-readable reason code are extracted because they are what a
    reader of the audit actually needs.
    """

    message = str(record.get("error_message") or "")
    status = re.search(r"Error code:\s*(\d{3})", message)
    reason = re.search(r"'reason':\s*'([a-z0-9_]+)'", message)
    retry_after = re.search(r"'Retry-After':\s*'(\d+)'", message)
    return {
        "error_type": record.get("error_type"),
        "http_status": int(status.group(1)) if status else None,
        "reason_code": reason.group(1) if reason else None,
        "retry_after_seconds": int(retry_after.group(1)) if retry_after else None,
        "message_withheld": bool(message),
    }


def terminalize(records: Iterable[Mapping[str, Any]]) -> Terminalization:
    """Reduce an append-only log to one analytic observation per task.

    Raises when a task carries more than one slot-consuming record, which would
    mean the same planned sample was spent twice, and when a task carries only
    technical failures, which would mean the run is incomplete. Neither is
    repaired here: both are decisions for the researcher.
    """

    by_task: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        task_id = str(record["task_id"])
        by_task.setdefault(task_id, []).append(record)

    terminal: dict[str, dict[str, Any]] = {}
    superseded: list[dict[str, Any]] = []
    unresolved: list[str] = []
    duplicated: list[str] = []

    for task_id in sorted(by_task):
        history = by_task[task_id]
        finals = [r for r in history if r.get("status") in SLOT_CONSUMING_STATUSES]
        others = [r for r in history if r.get("status") not in SLOT_CONSUMING_STATUSES]

        if len(finals) > 1:
            duplicated.append(task_id)
            continue
        if not finals:
            unresolved.append(task_id)

        for failure in others:
            superseded.append(
                {
                    "task_id": task_id,
                    "status": failure.get("status"),
                    "attempt_count": failure.get("attempt_count"),
                    "retry_count": failure.get("retry_count"),
                    "started_at_utc": failure.get("started_at_utc"),
                    "completed_at_utc": failure.get("completed_at_utc"),
                    "slot_consumed": failure.get("slot_consumed"),
                    "superseded_by_terminal": bool(finals),
                    **summarise_error(failure),
                }
            )
        if finals:
            terminal[task_id] = dict(finals[0])

    if duplicated:
        raise TerminalizationError(
            f"{len(duplicated)} task(s) carry more than one slot-consuming record, so the "
            "same planned sample was spent twice: "
            f"{', '.join(duplicated[:5])}{' ...' if len(duplicated) > 5 else ''}. "
            "Refusing to pick one."
        )
    if unresolved:
        raise TerminalizationError(
            f"{len(unresolved)} task(s) never received a completion: "
            f"{', '.join(unresolved[:5])}{' ...' if len(unresolved) > 5 else ''}. "
            "A missing observation is never substituted; resume the run instead."
        )

    counts = {
        "log_records": sum(len(v) for v in by_task.values()),
        "distinct_task_ids": len(by_task),
        "terminal_observations": len(terminal),
        "superseded_records": len(superseded),
        "unresolved_tasks": len(unresolved),
        "terminal_by_status": _tally(r["status"] for r in terminal.values()),
        "terminal_by_arm": _tally(r["arm"] for r in terminal.values()),
        "superseded_by_reason": _tally(
            str(s.get("reason_code") or s.get("error_type")) for s in superseded
        ),
    }
    return Terminalization(terminal=terminal, superseded=superseded,
                           unresolved=unresolved, counts=counts)


def _tally(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------
# 2. verification against the manifest
# --------------------------------------------------------------------------


def read_manifest_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_against_manifest(
    terminal: Mapping[str, Mapping[str, Any]],
    manifest_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check the terminal observations against the plan, field by field.

    Everything the manifest fixed must reproduce on the record: identity, the
    four content hashes, the routing that was requested and the routing that
    served the call, and the per-call settings. A mismatch is drift and stops
    the pipeline; it is never reconciled in favour of either side.
    """

    planned = {str(row["task_id"]): row for row in manifest_rows}
    observed = set(terminal)
    missing = sorted(set(planned) - observed)
    extra = sorted(observed - set(planned))

    problems: list[str] = []
    if missing:
        problems.append(f"{len(missing)} manifest task(s) have no observation: {missing[:5]}")
    if extra:
        problems.append(f"{len(extra)} observation(s) are not in the manifest: {extra[:5]}")

    checked = 0
    for task_id in sorted(observed & set(planned)):
        row, record = planned[task_id], terminal[task_id]
        checked += 1
        for field_name in IDENTITY_FIELDS:
            if str(record.get(field_name)) != str(row[field_name]):
                problems.append(
                    f"{task_id}: {field_name} is {record.get(field_name)!r}, "
                    f"manifest says {row[field_name]!r}"
                )
        if int(record.get("sample_index")) != int(row["sample_index"]):
            problems.append(f"{task_id}: sample_index differs")
        if (record.get("label_order") or None) != (row["label_order"] or None):
            problems.append(f"{task_id}: label_order differs")

        for field_name in HASH_FIELDS:
            planned_value = row.get(field_name) or None
            observed_value = record.get(field_name) or None
            if planned_value != observed_value:
                problems.append(f"{task_id}: {field_name} differs")

        if str(record.get("api_model_requested")) != str(row["api_model_requested"]):
            problems.append(f"{task_id}: requested model differs")
        if float(record.get("temperature_requested")) != float(row["temperature_requested"]):
            problems.append(f"{task_id}: temperature differs")
        if int(record.get("max_output_tokens")) != int(row["max_output_tokens"]):
            problems.append(f"{task_id}: max_output_tokens differs")

    if problems:
        raise ManifestMismatch(
            "The observations do not match the manifest:\n- "
            + "\n- ".join(problems[:20])
            + ("\n- ..." if len(problems) > 20 else "")
        )

    records = list(terminal.values())
    return {
        "manifest_rows": len(planned),
        "terminal_observations": len(observed),
        "one_to_one": True,
        "fields_checked": list(IDENTITY_FIELDS) + ["sample_index", "label_order"],
        "hashes_checked": list(HASH_FIELDS),
        "missing_tasks": missing,
        "extra_tasks": extra,
        "rows_verified": checked,
        "models_requested": sorted({str(r.get("api_model_requested")) for r in records}),
        "models_returned": sorted({str(r.get("api_model_returned")) for r in records}),
        "providers_requested": sorted({str(r.get("requested_provider")) for r in records}),
        "providers_upstream": sorted({str(r.get("upstream_provider")) for r in records}),
        "routing_consistent": all(
            r.get("api_model_requested") == r.get("api_model_returned")
            and r.get("requested_provider") == r.get("upstream_provider")
            for r in records
        ),
        "temperature_by_arm": _settings_by_arm(records, "temperature_requested"),
        "max_output_tokens_by_arm": _settings_by_arm(records, "max_output_tokens"),
        "reasoning_config_sent": sorted(
            {json.dumps(r.get("reasoning_config_sent"), sort_keys=True) for r in records}
        ),
        "reasoning_tokens_observed": sorted(
            {r.get("reasoning_tokens") for r in records if r.get("reasoning_tokens_reported")},
            key=lambda v: (v is None, v),
        ),
        "finish_reason_by_arm": {
            arm: _tally(r["finish_reason"] for r in records if r["arm"] == arm)
            for arm in sorted({str(r["arm"]) for r in records})
        },
    }


def _settings_by_arm(records: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, list]:
    out: dict[str, set] = {}
    for record in records:
        out.setdefault(str(record["arm"]), set()).add(record.get(field_name))
    return {arm: sorted(values, key=lambda v: (v is None, v)) for arm, values in sorted(out.items())}


# --------------------------------------------------------------------------
# 3. joining the human benchmark and the covariates
# --------------------------------------------------------------------------


def load_covariates(experiment: Mapping[str, Any], project_root: str | Path = ".") -> dict[str, dict]:
    """Index the source dataset by the official ``item_id`` convention.

    The ids are produced by :func:`design.load_items`, which derives them from
    the row position under the configured prefix. Using that function rather
    than re-deriving the convention is what keeps the join aligned with the
    manifest, which was built the same way.
    """

    return {str(row["item_id"]): row for row in load_items(dict(experiment), project_root)}


def _covariate_values(item: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in COVARIATES:
        raw = item.get(name)
        if name in ("HUMAN", "success"):
            out[name] = None if _blank(raw) else int(raw)
        elif name == "lgoal":
            out[name] = None if _blank(raw) else float(raw)
        else:
            out[name] = None if raw is None else str(raw)
    return out


def join_covariates(
    terminal: Mapping[str, Mapping[str, Any]],
    covariates: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the human benchmark and the covariates to every observation."""

    missing = sorted({str(r["item_id"]) for r in terminal.values()} - set(covariates))
    if missing:
        raise AnalysisError(f"Items absent from the source dataset: {missing[:10]}")

    rows: list[dict[str, Any]] = []
    for task_id in sorted(terminal):
        record = terminal[task_id]
        item = covariates[str(record["item_id"])]
        row = {name: record.get(name) for name in _TERMINAL_COLUMNS}
        row["task_id"] = task_id
        row["label"] = valid_label(record)
        row["parse_ok"] = record.get("status") == STATUS_SUCCESS
        row.update(_covariate_values(item))
        rows.append(row)
    return rows


#: Columns carried from the record into the analytic datasets. Deliberately
#: enumerated: a field is carried because it is needed, not because it happened
#: to be in the log.
_TERMINAL_COLUMNS = (
    "task_id", "arm", "item_id", "model_id", "template_id",
    "carlson_strategy_id", "camuffo_variant_id", "sample_index", "label_order",
    "status", "parsed_label", "finish_reason", "finish_reason_reported",
    "api_model_requested", "api_model_returned", "requested_provider", "upstream_provider",
    "temperature_requested", "max_output_tokens", "reasoning_tokens", "reasoning_tokens_reported",
    "input_tokens", "output_tokens", "cost", "cost_reported",
    "attempt_count", "retry_count",
    "text_sha256", "prompt_sha256", "system_prompt_sha256", "payload_sha256", "config_sha256",
)


def pilot_composition(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe the item set against the human benchmark, and warn if it is thin.

    A benchmark with one positive case cannot support a precision, a recall or
    a kappa that means anything. The warning is emitted by the code rather than
    written into a report by hand, so it cannot be forgotten on a later run.
    """

    items = {str(r["item_id"]): r for r in rows}
    human = _tally(r["HUMAN"] for r in items.values())
    success = _tally(r["success"] for r in items.values())
    n_positive = sum(1 for r in items.values() if r["HUMAN"] == 1)
    warnings: list[str] = []
    if n_positive < 2:
        warnings.append(
            f"The item set contains {n_positive} positive human label(s). Recall, "
            "precision, F1 and kappa are computed on a single positive case and "
            "carry no usable precision. No configuration can be ranked on them."
        )
    if len(items) < 30:
        warnings.append(
            f"{len(items)} items. This is a technical pilot: it establishes that the "
            "pipeline runs, not what the measures are worth."
        )
    distinct_subcategories = len({r["subcategory"] for r in items.values()})
    if distinct_subcategories >= len(items):
        warnings.append(
            f"{distinct_subcategories} distinct subcategories for {len(items)} items, so "
            "C(subcategory) saturates any regression before another term is added."
        )
    return {
        "n_items": len(items),
        "human": human,
        "success": success,
        "n_human_positive": n_positive,
        "distinct_subcategories": distinct_subcategories,
        "distinct_years": len({r["year"] for r in items.values()}),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# 4. arm-specific datasets
# --------------------------------------------------------------------------


def split_arms(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Separate the two arms. They share campaigns, never calls."""

    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["arm"]), []).append(row)
    payloads = {arm: {r["payload_sha256"] for r in group} for arm, group in out.items()}
    arms = sorted(payloads)
    for i, left in enumerate(arms):
        for right in arms[i + 1:]:
            shared = payloads[left] & payloads[right]
            if shared:
                raise AnalysisError(
                    f"Arms {left!r} and {right!r} share {len(shared)} payload digest(s). "
                    "The two arms must never reuse a call."
                )
    return {arm: sorted(group, key=lambda r: r["task_id"]) for arm, group in sorted(out.items())}


def sample_level(rows: Sequence[Mapping[str, Any]], model_id: str | None = None) -> list[dict]:
    """Level 1 of the hierarchy: majority over S within item x variant x model."""

    subset = [r for r in rows if model_id is None or r["model_id"] == model_id]
    aggregates = aggregate_samples(subset, expected_samples=3)
    by_cell = {(a["item_id"], a["model_id"], a["template_id"]): a for a in aggregates}
    covariates = {str(r["item_id"]): _covariate_values(r) for r in subset}
    out = []
    for key, aggregate in sorted(by_cell.items()):
        row = dict(aggregate)
        row["unanimous"] = bool(
            row["n_valid"] >= MINIMUM_VALID_CONTRIBUTIONS
            and (row["votes_1"] == 0 or row["votes_0"] == 0)
        )
        row.update(covariates[str(row["item_id"])])
        out.append(row)
    return out


def prompt_level(sample_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Level 2: majority over P within item x model. One row per model per item."""

    aggregates = aggregate_prompts(sample_rows, expected_prompts=3)
    covariates = {str(r["item_id"]): _covariate_values(r) for r in sample_rows}
    out = []
    for aggregate in aggregates:
        row = dict(aggregate)
        row["unanimous"] = bool(
            row["n_valid"] >= MINIMUM_VALID_CONTRIBUTIONS
            and (row["votes_1"] == 0 or row["votes_0"] == 0)
        )
        row.update(covariates[str(row["item_id"])])
        out.append(row)
    return out


def model_level(prompt_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Level 3: majority over M. Refuses to pretend it exists with one model.

    With a single model the level is unavailable, which is a different thing
    from a null aggregate: there is no second contribution to disagree with, so
    the question has not been asked. It is labelled accordingly rather than
    being reported as a missing value or, worse, as a zero.
    """

    models = sorted({str(r["model_id"]) for r in prompt_rows})
    if len(models) < MINIMUM_VALID_CONTRIBUTIONS:
        return {
            "status": MODEL_LEVEL_UNAVAILABLE,
            "models_present": models,
            "n_models": len(models),
            "minimum_required": MINIMUM_VALID_CONTRIBUTIONS,
            "rows": [],
            "note": (
                "The model level needs at least two valid model-level contributions. "
                "It is not null and not zero: it has not been computed, because the "
                "run carries fewer models than the rule requires."
            ),
        }
    return {
        "status": "available",
        "models_present": models,
        "n_models": len(models),
        "minimum_required": MINIMUM_VALID_CONTRIBUTIONS,
        "rows": aggregate_models(prompt_rows, expected_models=len(models)),
        "note": None,
    }


# --------------------------------------------------------------------------
# 5. writing, with a leak check
# --------------------------------------------------------------------------


def assert_no_sensitive_content(payload: str, where: str) -> None:
    """Refuse to write anything that carries a credential or an account id."""

    for pattern in SENSITIVE_PATTERNS:
        match = pattern.search(payload)
        if match:
            raise LeakCheckFailed(
                f"{where} contains a value matching {pattern.pattern!r}. Derived "
                "datasets never carry credentials, account identifiers or raw "
                "provider messages; the immutable log stays the audit source."
            )


def write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> Path:
    """Write a derived table, sorted and leak-checked, refusing to overwrite."""

    target = Path(path)
    if target.exists():
        raise AnalysisError(f"{target} already exists. Derived artefacts are versioned, not edited.")
    target.parent.mkdir(parents=True, exist_ok=True)

    withheld = WITHHELD_FIELDS & set(columns)
    if withheld:
        raise LeakCheckFailed(f"{target.name} would carry withheld fields {sorted(withheld)}")

    buffer: list[str] = []
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {key: _csv_value(row.get(key)) for key in columns}
            buffer.append("".join(str(v) for v in clean.values()))
            writer.writerow(clean)
    assert_no_sensitive_content("\n".join(buffer), target.name)
    return target


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    if target.exists():
        raise AnalysisError(f"{target} already exists. Derived artefacts are versioned, not edited.")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=_jsonable)
    assert_no_sensitive_content(text, target.name)
    target.write_text(text + "\n", encoding="utf-8")
    return target


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    target = Path(path)
    if target.exists():
        raise AnalysisError(f"{target} already exists. Derived artefacts are versioned, not edited.")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, sort_keys=True, ensure_ascii=False, default=_jsonable) for row in rows]
    assert_no_sensitive_content("\n".join(lines), target.name)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _jsonable(value: Any) -> Any:
    if isinstance(value, float) and value != value:  # NaN
        return None
    return str(value)


__all__ = [
    "COVARIATES",
    "MODEL_LEVEL_UNAVAILABLE",
    "PIPELINE_VERSION",
    "SENSITIVE_PATTERNS",
    "WITHHELD_FIELDS",
    "AnalysisError",
    "LeakCheckFailed",
    "ManifestMismatch",
    "Terminalization",
    "TerminalizationError",
    "assert_no_sensitive_content",
    "join_covariates",
    "load_covariates",
    "model_level",
    "pilot_composition",
    "prompt_level",
    "read_manifest_rows",
    "sample_level",
    "split_arms",
    "summarise_error",
    "terminalize",
    "verify_against_manifest",
    "write_csv",
    "write_json",
    "write_jsonl",
]
