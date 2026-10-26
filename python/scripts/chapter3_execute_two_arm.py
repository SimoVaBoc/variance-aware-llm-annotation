#!/usr/bin/env python3
# REVIEW REDACTION (decision D-EXPORT-03). Reviewer-facing derived copy of
# python/scripts/chapter3_execute_two_arm.py, not the frozen file.
# Original SHA-256: 48873814e6d83464d81d6d7032bcda72f2471433474f7aa7399a1a55533455d2
# Removed or neutralised, by line of the original:
#   12        docstring: one phrase removed
#   106-118   comments removed; the four route values of VALIDATION_SCOPE replaced
#             by "redacted_for_review"
#   669-673   --help epilog: the route-by-route status sentences removed
# Only comments, the docstring and string constants differ from the original; the
# syntax tree is otherwise identical. No execution contract is included; a contract
# binds the exact files it authorises by SHA-256.
"""Verify, plan and, only under double authorisation, execute a two-arm manifest.

    python python/scripts/chapter3_execute_two_arm.py --manifest <csv> --config <json>

Status: implementation_status ready_for_review, freeze_status not_frozen.

A thin wrapper around ``src.chapter3.runner_two_arm.run_two_arm_manifest``. It
adds nothing to the experimental logic: schema, approval gates, reference
hashes, payload reconstruction, request building, parsing and the
terminal-status contract all come from the library. What it adds is what the
temporary drivers used to provide, now written down:

* a dry run that writes nothing, reads no credential and opens no connection;
* an explicit execution order (``manifest`` or ``item``), applied by handing
  the library a segment manifest whose rows are byte-identical to the frozen
  manifest's, only reordered and subset;
* a strict resume check of the existing log;
* per-call guards around the provider adapter: returned model, upstream
  provider, HTTP status, reasoning tokens and thinking blocks, cost against a
  hard cap (the reported cost, or on the first-party routes a local estimate
  from usage and a dated tariff snapshot), and a clean stop on any API error,
  HTTP 402 included and named separately;
* an optional item filter, ``--item-id``, which a live run accepts only when
  the execution contract binds exactly those items and their task counts;
* one plan file and one metadata file per execution segment.

Without ``--live`` the command is always a dry run, and a dry run never
authorises anything. A live run needs ``--live`` together with
``--confirm-live TWO_ARM_LIVE_RUN``, every live argument listed in ``--help``
(none has a default), and ``--execution-contract``: a frozen contract that binds
this CLI and its executive components by hash, the manifest, config and route,
the model and provider requested and expected, the cost source, the API-error,
attempt and resume policies, and the reasoning guard. Any divergence is refused
before the output, the log or a credential is touched. Keys are never accepted as
arguments: the adapter reads its own environment variable, and only after every
preflight has passed.

Exit codes: 0 done, 2 refused or blocked before any call, 3 a live segment
stopped on a guard.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _path in (PROJECT_ROOT / "python", PROJECT_ROOT / "python" / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from src.chapter3 import first_party as fp  # noqa: E402
from src.chapter3 import huggingface as hf  # noqa: E402
from src.chapter3.analysis import write_json  # noqa: E402
from src.chapter3.catalog import (  # noqa: E402
    LABEL_ORDERS,
    load_json,
    render_system_prompt,
)
from src.chapter3.design import load_items, sha256_file  # noqa: E402
from src.chapter3.execution import (  # noqa: E402
    SLOT_CONSUMING_STATUSES,
    STATUS_API_ERROR,
    STATUS_DRY_RUN,
    STATUS_PARSE_ERROR,
    STATUS_SUCCESS,
    BudgetExceeded,
    BudgetPolicy,
    ExecutionBlocked,
    RetryPolicy,
    collect_blockers,
    read_manifest,
    requested_provider_from,
    route_for,
)
from src.chapter3.providers import (  # noqa: E402
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    build_adapter,
)
from src.chapter3.runner_two_arm import (  # noqa: E402
    build_request,
    run_two_arm_manifest,
    verify_rows_against_config,
    verify_schema,
)

CLI_ID = "chapter3_execute_two_arm"
IMPLEMENTATION_STATUS = "ready_for_review"
FREEZE_STATUS = "not_frozen"

#: What is enabled, route by route. The general implementation is not frozen.
#: A live run needs an execution contract that matches it exactly. A cost
#: source the adapter can read does not, by itself, enable a route.
VALIDATION_SCOPE = {
    "general_implementation": "ready_for_review",
    # [review redaction: route-by-route validation history and run statuses removed]
    "deepseek_huggingface_deepinfra": "redacted_for_review",
    "openrouter": "redacted_for_review",
    "terra_openai": "redacted_for_review",
    "sonnet_anthropic": "redacted_for_review",
}
ROUTE_STATUS = {
    "huggingface": VALIDATION_SCOPE["deepseek_huggingface_deepinfra"],
    "openrouter": VALIDATION_SCOPE["openrouter"],
    "openai": VALIDATION_SCOPE["terra_openai"],
    "anthropic": VALIDATION_SCOPE["sonnet_anthropic"],
}

#: Execution contracts. Schema and the status that authorises live execution.
CONTRACT_SCHEMA = "two_arm_execution_contract/1"
CONTRACT_LIVE_STATUS = "frozen_for_execution"
RESUME_POLICY = "manual_explicit_resume_v1"
MAX_ATTEMPTS = 1
#: Executable components whose hashes every contract must bind, besides this CLI.
#: A contract that omits one cannot authorise a run.
REQUIRED_COMPONENTS = (
    "python/src/chapter3/runner_two_arm.py",
    "python/src/chapter3/execution.py",
    "python/src/chapter3/providers.py",
    "python/src/chapter3/huggingface.py",
    "python/src/chapter3/first_party.py",
    "python/src/chapter3/results.py",
    "python/src/chapter3/catalog.py",
    "python/src/chapter3/manifest.py",
    "python/src/chapter3/design.py",
    "python/scripts/chapter3_execute.py",
)

#: Operational contract v1 for API errors. It changes no status semantics: an
#: api_error still carries no label and leaves its slot open, as in the library.
API_ERROR_POLICY = {
    "max_attempts": 1,
    "automatic_retry": False,
    "any_api_error_stops_the_segment": True,
    "task_after_an_api_error": "pending; no label, slot not consumed",
    "resume": "manual and explicit, with --resume",
    "http_402": "identified separately as stop_reason 'http_402'; it is one of the "
                "errors that stop the segment, not the only one",
}
LIVE_CONFIRMATION = "TWO_ARM_LIVE_RUN"
EXECUTION_ORDERS = ("manifest", "item")
#: must_be_zero: stop unless a zero reasoning count is reported, and on any
#: thinking block. stop_if_positive: stop on a positive count or any thinking
#: block; a missing count is recorded and flagged, never read as zero.
#: record_only: record everything, stop on nothing.
REASONING_GUARDS = ("must_be_zero", "stop_if_positive", "record_only")
NONE_TOKEN = "none"

#: Routes whose adapter yields a per-call cost the cap can be enforced on, and
#: what that cost is. Taken from the adapters themselves; the test suite checks
#: the two stay in step. A route absent from this table yields no usable cost,
#: so a dollar cap could not be enforced on it and a live run is refused. On
#: the first-party routes the cost is a local estimate from usage and a dated
#: tariff snapshot, read from ``cost_estimated``; it is not the bill.
ROUTE_COST_CONTRACT = {
    "openrouter": {"cost_source": "openrouter_usage_cost_credited", "kind": "credited_charge"},
    "huggingface": {"cost_source": hf.COST_SOURCE, "kind": "provider_estimate"},
    "openai": {"cost_source": fp.COST_SOURCE, "kind": fp.COST_KIND,
               "tariff_snapshot": fp.OPENAI_TARIFF_SNAPSHOT_ID},
    "anthropic": {"cost_source": fp.COST_SOURCE, "kind": fp.COST_KIND,
                  "tariff_snapshot": fp.ANTHROPIC_TARIFF_SNAPSHOT_ID},
}


class Refused(RuntimeError):
    """A preflight check failed. Nothing was sent and nothing was written."""


def verify_execution_contract(path: Path, args: argparse.Namespace,
                              root: Path) -> dict[str, Any]:
    """Refuse unless the contract authorises exactly this run. Reads files only.

    Called before the output, the log or any credential is touched. Every
    divergence is collected and reported together, so a reviewer sees all of
    them at once.
    """

    if not path.is_file():
        raise Refused(f"execution contract not found: {path}")
    raw = path.read_bytes()
    try:
        contract = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Refused(f"execution contract is not valid JSON: {error}") from error

    problems: list[str] = []

    def expect(label: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            problems.append(f"{label}: {actual!r} != contract {wanted!r}")

    expect("schema_version", contract.get("schema_version"), CONTRACT_SCHEMA)
    expect("execution_status", contract.get("execution_status"), CONTRACT_LIVE_STATUS)
    expect("contract_id vs file name", contract.get("contract_id"), path.stem)

    bound = contract.get("bound_files") or {}
    cli_entry = bound.get("cli") or {}
    if Path(root / str(cli_entry.get("path", ""))).resolve() != Path(__file__).resolve():
        problems.append("bound_files.cli does not name this CLI")
    expect("CLI sha256", sha256_file(Path(__file__).resolve()), cli_entry.get("sha256"))
    components = {c.get("path"): c.get("sha256") for c in bound.get("executive_components", [])}
    for required in REQUIRED_COMPONENTS:
        if required not in components:
            problems.append(f"contract does not bind {required}")
    for rel_path, wanted in components.items():
        file = root / str(rel_path)
        expect(f"{rel_path} sha256", sha256_file(file) if file.is_file() else None, wanted)
    for key, given in (("manifest", args.manifest), ("config", args.config)):
        entry = bound.get(key) or {}
        expect(f"{key} sha256", sha256_file(given) if given.is_file() else None,
               entry.get("sha256"))
    route_file = bound.get("route") or {}
    rf = root / str(route_file.get("path", ""))
    expect("route file sha256", sha256_file(rf) if rf.is_file() else None,
           route_file.get("sha256"))

    route = contract.get("route") or {}
    expect("--model-id", args.model_id, route.get("model_id"))
    expect("--confirm-api-route", args.confirm_api_route, route.get("api_route"))
    expect("--confirm-requested-model", args.confirm_requested_model,
           route.get("requested_model"))
    expect("--confirm-requested-provider", _none(args.confirm_requested_provider),
           route.get("requested_provider"))
    expect("--expect-returned-model", args.expect_returned_model,
           route.get("expected_returned_model"))
    expect("--expect-upstream-provider", _none(args.expect_upstream_provider),
           route.get("expected_upstream_provider"))

    cost = contract.get("cost") or {}
    cli_cost = ROUTE_COST_CONTRACT.get(str(route.get("api_route")), {})
    expect("cost_source (adapter)", cli_cost.get("cost_source"), cost.get("cost_source"))
    expect("cost_kind (adapter)", cli_cost.get("kind"), cost.get("cost_kind"))
    expect("tariff_snapshot (adapter)", cli_cost.get("tariff_snapshot"),
           cost.get("tariff_snapshot"))

    # A contract may bind the exact items it authorises. One that does not
    # authorises no item filter at all.
    selection = contract.get("selection") or {}
    expect("--item-id", sorted(args.item_id) if args.item_id else None,
           sorted(selection["item_ids"]) if selection.get("item_ids") else None)

    policies = contract.get("policies") or {}
    expect("api_error_policy", API_ERROR_POLICY, policies.get("api_error_policy"))
    expect("max_attempts", MAX_ATTEMPTS, policies.get("max_attempts"))
    expect("resume_policy", RESUME_POLICY, policies.get("resume_policy"))
    if policies.get("reasoning_guard") not in REASONING_GUARDS:
        problems.append(f"contract reasoning_guard {policies.get('reasoning_guard')!r} is invalid")
    expect("--reasoning-guard", args.reasoning_guard, policies.get("reasoning_guard"))

    if problems:
        requested_route = args.confirm_api_route
        status = ROUTE_STATUS.get(str(requested_route), "no_contract_for_this_route")
        raise Refused(f"execution contract {path.name} does not authorise this run "
                      f"(route {requested_route!r}: {status}):\n- " + "\n- ".join(problems))
    return {"path": rel(path, root), "sha256": hashlib.sha256(raw).hexdigest(),
            "contract_id": contract["contract_id"],
            "execution_status": contract["execution_status"],
            "selection": selection or None}


class GuardTripped(RuntimeError):
    """A per-call guard stopped the segment before the next request."""


# --------------------------------------------------------------------------
# loading and verification: library functions only
# --------------------------------------------------------------------------


def rel(path: Path, root: Path = PROJECT_ROOT) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def load_and_verify(manifest: Path, config: Path, root: Path) -> tuple[list[dict], dict, dict]:
    """Read the manifest and config and run every library verification.

    Returns the rows in manifest order, the experiment and the catalogue.
    """

    if not manifest.is_file():
        raise Refused(f"manifest not found: {manifest}")
    if not config.is_file():
        raise Refused(f"config not found: {config}")
    try:
        rows = read_manifest(manifest)
    except ValueError as error:
        raise Refused(str(error)) from error
    experiment = load_json(config)
    try:
        verify_schema(rows)
        catalog = verify_rows_against_config(rows, experiment, root)
    except (ExecutionBlocked, ValueError, KeyError) as error:
        raise Refused(f"{type(error).__name__}: {error}") from error

    models = {model["id"]: model for model in experiment["models"]}
    problems = []
    for row in rows:
        model = models.get(row.get("model_id"))
        if model is None:
            problems.append(f"{row['task_id']}: model {row.get('model_id')!r} is not in the config")
            continue
        if row.get("api_model_requested") != model["api_model"]:
            problems.append(f"{row['task_id']}: requested model differs from the config")
        if row.get("provider") != model["provider"]:
            problems.append(f"{row['task_id']}: provider differs from the config")
    if problems:
        raise Refused("rows whose model, route or provider cannot be resolved:\n- "
                      + "\n- ".join(problems[:20]))
    return rows, experiment, catalog


def model_contract(experiment: Mapping[str, Any], model_id: str) -> dict[str, Any]:
    model = next(m for m in experiment["models"] if m["id"] == model_id)
    settings = dict(model.get("request_settings") or {})
    return {
        "model_id": model_id,
        "api_model_requested": model["api_model"],
        "provider": model["provider"],
        "api_route": route_for(model),
        "requested_provider": requested_provider_from(settings),
    }


def request_profile(rows: Sequence[Mapping[str, Any]], experiment: Mapping[str, Any],
                    catalog: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Build every request exactly as the runner would, without sending it."""

    camuffo = load_json(root / experiment["references"]["camuffo_prompts"]["file"])
    renderings = {order: render_system_prompt(camuffo, order) for order in LABEL_ORDERS}
    delimiter = camuffo["assembly"]["delimiter"]
    items = {row["item_id"]: row for row in load_items(dict(experiment), root)}
    models = {model["id"]: model for model in experiment["models"]}
    text_column = experiment["dataset"]["text_column"]
    settings = Counter()
    wire = Counter()
    for row in rows:
        system = renderings[row["label_order"]] if row["arm"] == "camuffo" else None
        model = models[row["model_id"]]
        request: ProviderRequest = build_request(
            row, catalog[row["template_id"]], model,
            str(items[row["item_id"]][text_column]), system, delimiter)
        settings[(row["arm"], request.temperature, request.max_output_tokens,
                  request.system_prompt is not None)] += 1
        wire[(row["model_id"], row["arm"], request.temperature,
              json.dumps(wire_settings(route_for(model), request), sort_keys=True))] += 1
    return {
        "requests_built": len(rows),
        "by_arm_temperature_cap_system": [
            {"arm": a, "temperature": t, "max_output_tokens": c, "system_message": s, "rows": n}
            for (a, t, c, s), n in sorted(settings.items(), key=lambda kv: str(kv[0]))],
        # What the adapter would place on the wire, built by the adapter itself
        # around a client that cannot send anything. Texts are left out.
        "wire_settings": [
            {"model_id": m, "arm": a, "temperature_requested_by_design": t,
             "sent": json.loads(s), "rows": n}
            for (m, a, t, s), n in sorted(wire.items(), key=lambda kv: str(kv[0]))],
    }


class _NoClient:
    """Stands in for a provider client in a dry run. Has no methods to call."""


#: Payload keys that carry prompt text. Their presence is shown, not their text.
_TEXT_KEYS = ("messages", "system")


def wire_settings(route: str, request: ProviderRequest) -> dict[str, Any]:
    """The request body the route's adapter would send, minus the prompt texts."""

    payload = build_adapter(route, _NoClient()).build_payload(request)
    shown = {key: value for key, value in payload.items() if key not in _TEXT_KEYS}
    shown["system_message"] = (
        "system" in payload
        or any(m.get("role") == "system" for m in payload.get("messages", []))
    )
    return shown


# --------------------------------------------------------------------------
# the existing log
# --------------------------------------------------------------------------


def read_log_strict(path: Path) -> list[dict]:
    """Every non-empty line must be a JSON object. Nothing is skipped silently."""

    records, bad = [], []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad.append(number)
                continue
            if not isinstance(record, dict) or not record.get("task_id"):
                bad.append(number)
                continue
            records.append(record)
    if bad:
        raise Refused(f"{path} has {len(bad)} unreadable line(s), first at line {bad[0]}. "
                      "The log is not reinterpreted; resolve it before resuming.")
    return records


def log_compatibility(records: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
                      experiment: Mapping[str, Any]) -> list[str]:
    """Problems that make an existing log unusable with this manifest and config."""

    by_id = {row["task_id"]: row for row in rows}
    models = {model["id"]: model for model in experiment["models"]}
    problems: list[str] = []
    terminal = Counter()
    for record in records:
        task_id = str(record["task_id"])
        row = by_id.get(task_id)
        if row is None:
            problems.append(f"{task_id}: not in the selected manifest rows")
            continue
        if record.get("status") == STATUS_DRY_RUN:
            problems.append(f"{task_id}: a dry_run record in an execution log")
        for field in ("item_id", "model_id", "arm", "template_id", "payload_sha256",
                      "config_sha256", "api_model_requested"):
            if str(record.get(field)) != str(row.get(field)):
                problems.append(f"{task_id}: {field} differs from the manifest")
        if int(record.get("sample_index", -1)) != int(row["sample_index"]):
            problems.append(f"{task_id}: sample_index differs from the manifest")
        expected_route = route_for(models[row["model_id"]])
        if record.get("api_route") != expected_route:
            problems.append(f"{task_id}: api_route {record.get('api_route')!r} is not "
                            f"{expected_route!r}")
        if record.get("status") in SLOT_CONSUMING_STATUSES:
            terminal[task_id] += 1
    for task_id, count in terminal.items():
        if count > 1:
            problems.append(f"{task_id}: {count} terminal records")
    return problems


def terminal_ids(records: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(r["task_id"]) for r in records if r.get("status") in SLOT_CONSUMING_STATUSES}


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------


def plan_sequence(rows: Sequence[Mapping[str, Any]], terminal: set[str], order: str,
                  max_calls: int | None) -> dict[str, Any]:
    """The tasks a segment would send, in order. Rows are never altered.

    ``manifest`` keeps manifest order. ``item`` sorts items by ``item_id``,
    keeps manifest order within an item, finishes partially completed items
    first, and never splits an untouched item to fit ``max_calls``.
    """

    pending = [row for row in rows if row["task_id"] not in terminal]
    expected = Counter(row["item_id"] for row in rows)
    done = Counter(row["item_id"] for row in rows if row["task_id"] in terminal)
    partial = sorted(i for i in expected if 0 < done[i] < expected[i])
    complete = sorted(i for i in expected if done[i] == expected[i])
    untouched = sorted(i for i in expected if done[i] == 0)
    warnings: list[str] = []

    if order == "manifest":
        sequence = list(pending if max_calls is None else pending[:max_calls])
    elif order == "item":
        by_item: "OrderedDict[str, list]" = OrderedDict()
        for item in partial + [i for i in untouched]:
            by_item[item] = [r for r in pending if r["item_id"] == item]
        sequence = []
        for item, chunk in by_item.items():
            if max_calls is None or len(sequence) + len(chunk) <= max_calls:
                sequence.extend(chunk)
                continue
            if not sequence and item in partial:
                sequence.extend(chunk[:max_calls])
                warnings.append(f"partial item {item} is continued but not finished: "
                                f"{len(chunk) - max_calls} of its tasks stay pending")
            elif not sequence:
                raise Refused(f"--max-calls {max_calls} would split item {item}, which needs "
                              f"{len(chunk)} calls. Raise --max-calls to at least {len(chunk)}.")
            else:
                unused = max_calls - len(sequence)
                if unused:
                    warnings.append(f"{unused} call(s) of --max-calls left unused so that item "
                                    f"{item} is not split")
            break
    else:
        raise Refused(f"unknown execution order {order!r}")

    items_in_sequence = list(OrderedDict.fromkeys(r["item_id"] for r in sequence))
    return {
        "order": order,
        "tasks_selected": len(rows),
        "tasks_terminal": len(rows) - len(pending),
        "tasks_pending": len(pending),
        "tasks_in_segment": len(sequence),
        "tasks_pending_after_segment": len(pending) - len(sequence),
        "items": len(expected),
        "tasks_per_item": sorted(set(expected.values())),
        "items_complete": len(complete),
        "items_partial": partial,
        "items_untouched": len(untouched),
        "items_in_segment": items_in_sequence,
        "warnings": warnings,
        "sequence": sequence,
    }


# --------------------------------------------------------------------------
# guards around the adapter
# --------------------------------------------------------------------------


class GuardState:
    def __init__(self, *, route: str, max_calls: int, max_usd: float, expected_model: str,
                 expected_provider: str | None, reasoning_guard: str) -> None:
        self.route = route
        self.max_calls = max_calls
        self.max_usd = max_usd
        self.expected_model = expected_model
        self.expected_provider = expected_provider
        self.reasoning_guard = reasoning_guard
        self.contract = ROUTE_COST_CONTRACT[route]
        self.calls = 0
        self.cost = 0.0
        self.stop_reason: str | None = None
        self.violations: list[dict[str, Any]] = []
        # Responses that carried no reasoning count. Flagged in the segment
        # metadata; never read as zero.
        self.reasoning_unreported = 0


class GuardedAdapter:
    """Checks every response; stops the segment before the next request on a breach.

    A breaching response is still returned, so the library records it exactly
    as it arrived: a paid observation is never discarded, and whether to use it
    is left to the researcher. An exception raised here before a request is not
    a ProviderError, so it ends the run without writing a record for that task,
    which therefore stays pending.
    """

    def __init__(self, inner: Any, state: GuardState) -> None:
        self.inner = inner
        self.state = state

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        state = self.state
        if state.stop_reason:
            raise GuardTripped(state.stop_reason)
        if state.calls >= state.max_calls:
            state.stop_reason = "max_calls_reached"
            raise GuardTripped(state.stop_reason)
        if state.cost >= state.max_usd:
            state.stop_reason = "max_usd_reached"
            raise GuardTripped(state.stop_reason)

        state.calls += 1
        try:
            response = self.inner.complete(request)
        except ProviderError as error:
            code = getattr(error, "status_code", None)
            # Operational contract v1: every API error stops the segment, so the
            # task stays pending for an explicit, manual resume. 402 is named.
            if code == 402:
                state.stop_reason = "http_402"
            elif code is None:
                state.stop_reason = "api_error_without_http_status"
            else:
                state.stop_reason = f"api_error_http_{code}"
            state.violations.append({"call": state.calls, "reason": state.stop_reason,
                                     "error_type": type(error).__name__,
                                     "http_status": code})
            raise

        breaches = []
        if response.api_model_returned != state.expected_model:
            breaches.append("returned_model_mismatch")
        if (response.upstream_provider or None) != state.expected_provider:
            breaches.append("upstream_provider_mismatch")
        if response.http_status is not None and response.http_status != 200:
            breaches.append(f"http_status_{response.http_status}")
        if not response.reasoning_tokens_reported:
            state.reasoning_unreported += 1
        if state.reasoning_guard in ("must_be_zero", "stop_if_positive"):
            if not response.reasoning_tokens_reported:
                if state.reasoning_guard == "must_be_zero":
                    breaches.append("reasoning_tokens_not_reported")
            elif response.reasoning_tokens != 0:
                breaches.append("reasoning_tokens_nonzero")
            if (response.thinking_blocks or 0) + (response.redacted_thinking_blocks or 0) > 0:
                breaches.append("thinking_blocks_present")
        if state.contract["kind"] == fp.COST_KIND:
            # First-party routes: the cap runs on the local estimate, computed
            # by the adapter from usage and the contract's tariff snapshot.
            if response.cost_estimated is None:
                breaches.append("unpriced_call")
            elif response.cost_estimate_basis != state.contract["tariff_snapshot"]:
                breaches.append("tariff_snapshot_mismatch")
            else:
                state.cost += float(response.cost_estimated)
                if state.cost > state.max_usd:
                    breaches.append("max_usd_exceeded")
        elif not response.cost_reported or response.cost is None:
            breaches.append("unpriced_call")
        elif response.cost_source != state.contract["cost_source"]:
            breaches.append("cost_source_mismatch")
        else:
            state.cost += float(response.cost)
            if state.cost > state.max_usd:
                breaches.append("max_usd_exceeded")
        if breaches:
            state.stop_reason = "+".join(breaches)
            state.violations.append({"call": state.calls, "reason": state.stop_reason,
                                     "api_model_returned": response.api_model_returned,
                                     "upstream_provider": response.upstream_provider})
        return response


def default_adapter_factory(route: str):
    """The live client factory of the existing CLI. Reached only after preflight."""

    import chapter3_execute

    return chapter3_execute.live_adapter_factory(route)


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify, plan and, only under double authorisation, execute a two-arm "
                    "manifest. Without --live this is always a dry run that writes nothing.",
        epilog="A live run is authorised only by a frozen execution contract given with "
               "--execution-contract that matches this CLI, its executive components, the "
               "manifest, config and route, and every live argument. API errors "
               "(operational contract v1): one attempt per task, no automatic retry; any API "
               "error stops the segment and leaves its task pending; resuming is manual, with "
               "--resume. HTTP 402 is reported separately as 'http_402' but is not the only "
               "error that stops a segment.")
    parser.add_argument("--manifest", type=Path, required=True, help="two-arm manifest CSV")
    parser.add_argument("--config", type=Path, required=True, help="experiment JSON")
    parser.add_argument("--model-id", default=None,
                        help="restrict to one configured model id; required for --live")
    parser.add_argument("--item-id", action="append", default=None,
                        help="restrict to this item id; repeatable. A live run accepts it only "
                             "when the execution contract binds exactly these items")
    parser.add_argument("--output-jsonl", type=Path, default=None,
                        help="dry run: an existing log to audit, read only. Live: the "
                             "append-only log; required")
    parser.add_argument("--execution-order", choices=EXECUTION_ORDERS, default=None,
                        help="required for --live; in a dry run, previews that order")
    parser.add_argument("--max-calls", type=int, default=None,
                        help="hard cap on requests in this segment; required for --live")
    parser.add_argument("--resume", action="store_true",
                        help="continue an existing --output-jsonl; without it an existing "
                             "log is refused")
    parser.add_argument("--format", choices=("text", "json"), default="text")

    live = parser.add_argument_group("live execution (all required, none has a default)")
    live.add_argument("--live", action="store_true", help="send real requests")
    live.add_argument("--execution-contract", type=Path, default=None,
                      help="the frozen execution contract that must authorise this exact run "
                           "(CLI and component hashes, manifest, config, route, model, "
                           "provider, cost source, policies, reasoning guard). In a dry "
                           "run it is only checked and reported, never used to authorise")
    live.add_argument("--confirm-live", default=None,
                      help=f"must be exactly {LIVE_CONFIRMATION}")
    live.add_argument("--max-usd", type=float, default=None,
                      help="hard cap on the cost of this segment: the reported cost, or on "
                           "first-party routes the local tariff estimate. Checked before each "
                           "call, so the call in flight can take the total past it by at most "
                           "its own cost")
    live.add_argument("--confirm-api-route", default=None,
                      help="must equal the selected model's api_route")
    live.add_argument("--confirm-requested-model", default=None,
                      help="must equal the selected model's api_model")
    live.add_argument("--confirm-requested-provider", default=None,
                      help=f"must equal the configured pinned provider, or '{NONE_TOKEN}'")
    live.add_argument("--expect-returned-model", default=None,
                      help="the model id every response must report")
    live.add_argument("--expect-upstream-provider", default=None,
                      help=f"the upstream provider every response must report, or '{NONE_TOKEN}'")
    live.add_argument("--reasoning-guard", choices=REASONING_GUARDS, default=None,
                      help="must_be_zero stops on any response without a reported zero "
                           "reasoning count; stop_if_positive stops on a positive count or a "
                           "thinking block and flags a missing count; record_only records them")
    return parser


LIVE_REQUIRED = ("confirm_live", "execution_contract", "manifest", "config", "output_jsonl",
                 "execution_order",
                 "max_calls", "max_usd", "model_id", "confirm_api_route",
                 "confirm_requested_model", "confirm_requested_provider",
                 "expect_returned_model", "expect_upstream_provider", "reasoning_guard")


def check_live_arguments(args: argparse.Namespace) -> None:
    missing = [name for name in LIVE_REQUIRED if getattr(args, name) is None]
    if missing:
        raise Refused("--live requires " + ", ".join("--" + m.replace("_", "-") for m in missing)
                      + ". No live argument has a default.")
    if args.confirm_live != LIVE_CONFIRMATION:
        raise Refused(f"--confirm-live must be exactly {LIVE_CONFIRMATION}")
    if args.max_calls < 1 or args.max_usd <= 0:
        raise Refused("--max-calls must be at least 1 and --max-usd greater than zero")


def _none(value: str | None) -> str | None:
    return None if value is None or value.lower() == NONE_TOKEN else value


def select_model(rows: list[dict], experiment: dict, model_id: str | None,
                 item_ids: Sequence[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Rows for one model and, if given, these items, plus the route profile.

    Items are matched by id, never by position: the rows keep manifest order,
    and an item id with no row is refused rather than ignored.
    """

    if model_id is not None:
        if model_id not in {m["id"] for m in experiment["models"]}:
            raise Refused(f"--model-id {model_id!r} is not a configured model")
        rows = [r for r in rows if r["model_id"] == model_id]
        if not rows:
            raise Refused(f"no manifest row has model id {model_id!r}")
    if item_ids:
        wanted = set(item_ids)
        missing = sorted(wanted - {r["item_id"] for r in rows})
        if missing:
            raise Refused(f"--item-id {missing} has no row for the selected model")
        rows = [r for r in rows if r["item_id"] in wanted]
    profile = Counter()
    for row in rows:
        c = model_contract(experiment, row["model_id"])
        profile[(c["model_id"], c["api_model_requested"], c["api_route"], c["requested_provider"])] += 1
    routes = [{"model_id": k[0], "api_model_requested": k[1], "api_route": k[2],
               "requested_provider": k[3], "rows": n} for k, n in sorted(profile.items(), key=str)]
    return rows, routes


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = sorted({r["item_id"] for r in rows})
    by_item: Any = "more than 20 items; see by_arm"
    if len(items) <= 20:
        by_item = {item: dict(sorted(Counter(r["arm"] for r in rows
                                             if r["item_id"] == item).items()))
                   for item in items}
    return {
        "by_arm": dict(sorted(Counter(r["arm"] for r in rows).items())),
        "by_item_and_arm": by_item,
        "by_template": dict(sorted(Counter(r["template_id"] for r in rows).items())),
        "by_model": dict(sorted(Counter(r["model_id"] for r in rows).items())),
        "by_provider": dict(sorted(Counter(r["provider"] for r in rows).items())),
        "temperature_by_arm": {a: sorted({r["temperature_requested"] for r in rows if r["arm"] == a})
                               for a in sorted({r["arm"] for r in rows})},
        "max_output_tokens_by_arm": {a: sorted({r["max_output_tokens"] for r in rows if r["arm"] == a})
                                     for a in sorted({r["arm"] for r in rows})},
    }


def prepare(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Everything a dry run reports and a live run needs. Writes nothing."""

    rows, experiment, catalog = load_and_verify(args.manifest, args.config, root)
    selected, routes = select_model(rows, experiment, args.model_id, args.item_id)
    blockers = collect_blockers(experiment, {r["model_id"] for r in selected})

    records: list[dict] = []
    log_problems: list[str] = []
    if args.output_jsonl is not None and args.output_jsonl.exists():
        records = read_log_strict(args.output_jsonl)
        log_problems = log_compatibility(records, selected, experiment)
    terminal = terminal_ids(records) & {r["task_id"] for r in selected}

    order = args.execution_order or "item"
    plan = plan_sequence(selected, terminal, order, args.max_calls)
    status_counts = Counter(str(r.get("status")) for r in records)
    return {
        "rows": selected,
        "experiment": experiment,
        "routes": routes,
        "homogeneous": len(routes) == 1,
        "blockers": blockers,
        "log_records": len(records),
        "log_status_counts": dict(sorted(status_counts.items())),
        "log_problems": log_problems,
        "plan": plan,
        "terminal": terminal,
        "order_was_explicit": args.execution_order is not None,
        "summary": summarise(selected),
        "requests": request_profile(selected, experiment, catalog, root),
        "manifest_total_rows": len(rows),
    }


def dry_run_report(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    plan = state["plan"]
    return {
        "cli": CLI_ID,
        "implementation_status": IMPLEMENTATION_STATUS,
        "freeze_status": FREEZE_STATUS,
        "validation_scope": VALIDATION_SCOPE,
        "api_error_policy": API_ERROR_POLICY,
        "mode": "dry_run",
        "writes": "none",
        "network": "none",
        "credentials_read": "none",
        "manifest": rel(args.manifest),
        "config": rel(args.config),
        "manifest_rows": state["manifest_total_rows"],
        "item_filter": sorted(args.item_id) if args.item_id else None,
        "selected_rows": len(state["rows"]),
        "routes": state["routes"],
        "route_homogeneous": state["homogeneous"],
        "payloads_reproduced": len(state["rows"]),
        **state["summary"],
        "requests": state["requests"],
        "audited_log": rel(args.output_jsonl) if args.output_jsonl else None,
        "log_records": state["log_records"],
        "log_status_counts": state["log_status_counts"],
        "log_problems": state["log_problems"][:20],
        "blockers": state["blockers"],
        "execution_order_previewed": plan["order"] + ("" if state["order_was_explicit"]
                                                      else " (default preview only)"),
        "tasks_terminal": plan["tasks_terminal"],
        "tasks_pending": plan["tasks_pending"],
        "tasks_in_next_segment": plan["tasks_in_segment"],
        "items": plan["items"],
        "tasks_per_item": plan["tasks_per_item"],
        "items_complete": plan["items_complete"],
        "items_partial": plan["items_partial"],
        "items_untouched": plan["items_untouched"],
        "first_items_in_order": plan["items_in_segment"][:5],
        "warnings": plan["warnings"],
    }


def print_text(report: Mapping[str, Any]) -> None:
    for key, value in report.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=True)
        print(f"{key:30s} {value}")


# --------------------------------------------------------------------------
# live
# --------------------------------------------------------------------------


def _file_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def task_ids_sha256(task_ids) -> str:
    """sha256 of the task ids joined by newlines, in the order given."""

    return hashlib.sha256("\n".join(task_ids).encode("utf-8")).hexdigest()


def run_live(args: argparse.Namespace, root: Path,
             adapter_factory: Callable[[str], Any]) -> int:
    check_live_arguments(args)
    # The contract is the gate: nothing else is read, and no credential can be,
    # until it authorises exactly this run.
    contract = verify_execution_contract(args.execution_contract, args, root)
    output: Path = args.output_jsonl
    if output.exists() and not args.resume:
        raise Refused(f"{output} already exists. Pass --resume to continue it; it is never "
                      "overwritten.")
    if args.resume and not output.exists():
        raise Refused(f"--resume given but {output} does not exist")

    state = prepare(args, root)
    if not state["homogeneous"]:
        raise Refused(f"the selection is not homogeneous: {state['routes']}")
    route = state["routes"][0]
    for flag, expected in (("confirm_api_route", route["api_route"]),
                           ("confirm_requested_model", route["api_model_requested"]),
                           ("confirm_requested_provider", route["requested_provider"])):
        if _none(getattr(args, flag)) != expected:
            raise Refused(f"--{flag.replace('_', '-')} {getattr(args, flag)!r} does not match "
                          f"the configuration ({expected!r})")
    if route["api_route"] not in ROUTE_COST_CONTRACT:
        raise Refused(f"route {route['api_route']!r} yields no usable per-call cost, so "
                      "--max-usd cannot be enforced. Live is refused.")
    selection = contract.get("selection") or {}
    if selection:
        by_arm = dict(sorted(Counter(r["arm"] for r in state["rows"]).items()))
        if len(state["rows"]) != selection.get("tasks") or by_arm != selection.get("by_arm"):
            raise Refused(f"the selection has {len(state['rows'])} tasks {by_arm}; the contract "
                          f"binds {selection.get('tasks')} {selection.get('by_arm')}")
    if route["api_route"] == "huggingface":
        hub_model, _ = hf.split_model_and_provider(route["api_model_requested"])
        if args.expect_returned_model != hub_model:
            raise Refused(f"--expect-returned-model must be {hub_model!r} on this route")
    if state["blockers"]:
        raise Refused("blocked by gates:\n- " + "\n- ".join(state["blockers"]))
    if state["log_problems"]:
        raise Refused("the existing log is not compatible:\n- "
                      + "\n- ".join(state["log_problems"][:20]))
    if state["experiment"].get("execution", {}).get("live_calls_enabled") is not False:
        raise Refused("the configuration must keep live_calls_enabled false")
    plan = state["plan"]
    if plan["tasks_in_segment"] == 0:
        print("Nothing to do: every selected task is terminal. Nothing was written.")
        return 0

    segment_dir = output.parent / f"{output.stem}.segments"
    previous = sorted(segment_dir.glob("segment_*.plan.json")) if segment_dir.exists() else []
    if previous:
        last = json.loads(previous[-1].read_text(encoding="utf-8"))
        for key, value in (("manifest_sha256", sha256_file(args.manifest)),
                           ("config_sha256", sha256_file(args.config)),
                           ("model_id", args.model_id),
                           ("item_ids", sorted(args.item_id) if args.item_id else None)):
            if last.get(key) != value:
                raise Refused(f"previous segment {previous[-1].name} used a different {key}")
    index = len(previous) + 1
    stem = f"segment_{index:03d}"

    # Every preflight has passed. Only now is anything written.
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_manifest = segment_dir / f"{stem}_tasks.csv"
    if segment_manifest.exists():
        raise Refused(f"{segment_manifest} already exists")
    fieldnames = list(plan["sequence"][0].keys())
    with segment_manifest.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(plan["sequence"])

    manifest_meta = args.manifest.with_suffix(".meta.json")
    log_lines_before = (len(output.read_text(encoding="utf-8").splitlines())
                        if output.exists() else 0)
    plan_record = {
        "cli": CLI_ID, "implementation_status": IMPLEMENTATION_STATUS,
        "freeze_status": FREEZE_STATUS, "segment": index,
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cli_sha256": sha256_file(Path(__file__).resolve()),
        "runner_sha256": sha256_file(root / "python/src/chapter3/runner_two_arm.py"),
        "manifest": rel(args.manifest), "manifest_sha256": sha256_file(args.manifest),
        "manifest_meta_sha256": _file_sha(manifest_meta),
        "config": rel(args.config), "config_sha256": sha256_file(args.config),
        "model_id": args.model_id, "item_ids": sorted(args.item_id) if args.item_id else None,
        "route": route,
        "arguments": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "execution_order": plan["order"], "segment_manifest": rel(segment_manifest),
        "segment_manifest_sha256": sha256_file(segment_manifest),
        "tasks_planned": plan["tasks_in_segment"],
        "tasks_skipped_terminal": plan["tasks_terminal"],
        "items_in_segment": plan["items_in_segment"], "warnings": plan["warnings"],
        "log": rel(output), "log_sha256_before": _file_sha(output),
        "log_lines_before": log_lines_before,
        "previous_segment": previous[-1].name if previous else None,
        "retry_policy": "max_attempts=1; no automatic retry",
        "api_error_policy": API_ERROR_POLICY,
        "validation_scope": VALIDATION_SCOPE,
        "execution_contract": contract,
        "cost_contract": ROUTE_COST_CONTRACT[route["api_route"]],
        # Enough to rebuild the segment without the CLI: the selected rows are the
        # source manifest's rows for model_id, in manifest order (hashed here);
        # the terminal ones are listed; the planned ones are listed in execution
        # order, and the same rows sit unchanged in the segment manifest beside
        # this file.
        "selection": {
            "rule": "rows of the source manifest whose model_id equals model_id"
                    + (" and whose item_id is in item_ids" if args.item_id else "")
                    + ", in manifest order",
            "item_ids": sorted(args.item_id) if args.item_id else None,
            "selected_by_arm": dict(sorted(Counter(r["arm"] for r in state["rows"]).items())),
            "selected_tasks": len(state["rows"]),
            "selected_task_ids_sha256": task_ids_sha256(r["task_id"] for r in state["rows"]),
            "terminal_before_task_ids": sorted(state["terminal"]),
            "planned_task_ids_in_order": [r["task_id"] for r in plan["sequence"]],
            "planned_task_ids_sha256": task_ids_sha256(r["task_id"] for r in plan["sequence"]),
        },
    }
    write_json(segment_dir / f"{stem}.plan.json", plan_record)

    guard = GuardState(route=route["api_route"], max_calls=args.max_calls,
                       max_usd=args.max_usd, expected_model=args.expect_returned_model,
                       expected_provider=_none(args.expect_upstream_provider),
                       reasoning_guard=args.reasoning_guard)

    def guarded_factory(requested_route: str):
        if requested_route != guard.route:
            raise GuardTripped(f"route {requested_route!r} is not the confirmed route")
        return GuardedAdapter(adapter_factory(requested_route), guard)

    stop_reason = None
    try:
        run_two_arm_manifest(
            experiment=state["experiment"], manifest_path=segment_manifest, output_path=output,
            project_root=root, live=True,
            budget=BudgetPolicy(max_calls=args.max_calls, max_usd=args.max_usd),
            adapter_factory=guarded_factory, retry_policy=RetryPolicy(max_attempts=MAX_ATTEMPTS),
            resume=True)
    except GuardTripped as error:
        stop_reason = str(error)
    except (BudgetExceeded, ExecutionBlocked) as error:
        stop_reason = f"{type(error).__name__}: {error}"
    except Exception as error:  # noqa: BLE001 - recorded, never swallowed silently
        stop_reason = f"unexpected {type(error).__name__}: {error}"
    stop_reason = stop_reason or guard.stop_reason

    after = read_log_strict(output) if output.exists() else []
    lines = output.read_text(encoding="utf-8").splitlines() if output.exists() else []
    segment_records = [json.loads(line) for line in lines[log_lines_before:] if line.strip()]
    selected_ids = {r["task_id"] for r in state["rows"]}
    terminal_after = terminal_ids(after) & selected_ids
    statuses = Counter(r.get("status") for r in segment_records)
    meta = {
        **{k: plan_record[k] for k in ("cli", "implementation_status", "freeze_status",
                                       "segment", "started_at_utc", "cli_sha256",
                                       "runner_sha256", "manifest", "manifest_sha256",
                                       "manifest_meta_sha256", "config", "config_sha256",
                                       "execution_order", "segment_manifest",
                                       "segment_manifest_sha256", "log", "log_sha256_before",
                                       "previous_segment")},
        "completed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arguments": plan_record["arguments"],
        "tasks_planned": plan["tasks_in_segment"],
        "tasks_attempted": len(segment_records),
        "success": statuses.get(STATUS_SUCCESS, 0),
        "parse_error": statuses.get(STATUS_PARSE_ERROR, 0),
        "api_error": statuses.get(STATUS_API_ERROR, 0),
        "tasks_skipped_terminal": plan["tasks_terminal"],
        "tasks_pending_after": len(selected_ids - terminal_after),
        "cost_usd_this_segment": round(guard.cost, 10),
        "cost_source": ROUTE_COST_CONTRACT[route["api_route"]]["cost_source"],
        "cost_kind": ROUTE_COST_CONTRACT[route["api_route"]]["kind"],
        "cost_usd_log_total": round(sum(float(r.get("cost") or 0) for r in after
                                        if r.get("cost_reported")), 10),
        # Local tariff estimates, kept apart from reported cost. Not the bill.
        "cost_estimated_usd_log_total": round(sum(float(r.get("cost_estimated") or 0)
                                                  for r in after), 10),
        "cost_estimate_basis": dict(Counter(str(r.get("cost_estimate_basis"))
                                            for r in segment_records)),
        "cap_overshoot_note": "--max-usd is checked before each call; the call in flight can "
                              "take the total past it by at most its own cost",
        "requested": route,
        "expected_returned_model": args.expect_returned_model,
        "expected_upstream_provider": _none(args.expect_upstream_provider),
        "returned_models": dict(Counter(str(r.get("api_model_returned")) for r in segment_records)),
        "upstream_providers": dict(Counter(str(r.get("upstream_provider")) for r in segment_records)),
        "http_status": dict(Counter(str(r.get("http_status")) for r in segment_records)),
        "reasoning_tokens": dict(Counter(str(r.get("reasoning_tokens")) for r in segment_records)),
        # A missing count is flagged here, never read as zero.
        "reasoning_tokens_unreported_calls": sum(1 for r in segment_records
                                                 if r.get("status") != STATUS_API_ERROR
                                                 and not r.get("reasoning_tokens_reported")),
        "reasoning_tokens_source": dict(Counter(str(r.get("reasoning_tokens_source"))
                                                for r in segment_records)),
        "thinking_blocks_total": sum(int(r.get("thinking_blocks") or 0)
                                     + int(r.get("redacted_thinking_blocks") or 0)
                                     for r in segment_records),
        "finish_reasons": dict(Counter(str(r.get("finish_reason")) for r in segment_records)),
        "temperature_sent_by_arm": {
            arm: sorted({str(r.get("temperature_parameter_sent")) for r in segment_records
                         if r.get("arm") == arm})
            for arm in sorted({r.get("arm") for r in segment_records if r.get("arm")})},
        "api_errors": [{"task_id": r["task_id"], "http_status": r.get("http_status"),
                        "error_type": r.get("error_type")}
                       for r in segment_records if r.get("status") == STATUS_API_ERROR],
        "http_402_seen": any(r.get("http_status") == 402 for r in segment_records
                             if r.get("status") == STATUS_API_ERROR),
        "api_error_policy": API_ERROR_POLICY,
        "validation_scope": VALIDATION_SCOPE,
        "execution_contract": contract,
        "segment_manifest_sha256_after": _file_sha(segment_manifest),
        "segment_manifest_unchanged": _file_sha(segment_manifest) == plan_record[
            "segment_manifest_sha256"],
        "planned_task_ids_sha256": plan_record["selection"]["planned_task_ids_sha256"],
        "reasoning_guard": args.reasoning_guard,
        "guard_violations": guard.violations,
        "stop_reason": stop_reason,
        "log_sha256_after": _file_sha(output),
        "log_lines_after": len(lines),
    }
    write_json(segment_dir / f"{stem}.meta.json", meta)
    print(f"Segment {index}: planned {meta['tasks_planned']}, attempted "
          f"{meta['tasks_attempted']}, success {meta['success']}, parse_error "
          f"{meta['parse_error']}, api_error {meta['api_error']}, pending after "
          f"{meta['tasks_pending_after']}, cost ${meta['cost_usd_this_segment']:.6f} "
          f"({meta['cost_kind']}), stop: {stop_reason or 'none'}")
    return 3 if stop_reason else 0


def main(argv: Sequence[str] | None = None, *, root: Path = PROJECT_ROOT,
         adapter_factory: Callable[[str], Any] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.live:
            return run_live(args, root, adapter_factory or default_adapter_factory)
        if args.confirm_live is not None:
            raise Refused("--confirm-live without --live does nothing; refusing an ambiguous "
                          "command")
        if args.resume and (args.output_jsonl is None or not args.output_jsonl.exists()):
            raise Refused("--resume needs an existing --output-jsonl")
        state = prepare(args, root)
        report = dry_run_report(args, state)
        contract_failed = False
        if args.execution_contract is None:
            check: Any = ("not evaluated: no contract given. A dry run never authorises "
                          "execution.")
        else:
            try:
                check = {"result": "matches_these_arguments",
                         **verify_execution_contract(args.execution_contract, args, root),
                         "note": "a dry run never authorises execution; a live run with "
                                 "exactly these arguments would pass the contract gate"}
            except Refused as error:
                contract_failed = True
                check = {"result": "does_not_authorise", "detail": str(error)}
        report["authorises_execution"] = False
        report["execution_contract_check"] = check
        if args.format == "json":
            print(json.dumps(report, indent=2, sort_keys=False, default=str))
        else:
            print_text(report)
        failing = state["blockers"] or state["log_problems"] or contract_failed
        return 2 if failing else 0
    except Refused as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
