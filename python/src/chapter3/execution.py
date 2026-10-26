"""Execution layer for the Chapter 3 annotation manifest.

Design guarantees enforced here:

* Live calls are off unless the caller passes an explicit live flag together
  with a hard budget cap. The default execution mode is a dry run.
* Raw results are appended to a JSONL file. Nothing is ever overwritten.
* Resume is keyed on the immutable ``task_id``. A task with a recorded success
  is never re-sent.
* A technical failure, in which no completion was received, may be retried on
  the same task and the same sample index. It increments ``attempt_count`` on a
  single record and never produces an extra independent sample.
* Response parsing is strict. Only an exact ``0`` or ``1`` after stripping
  whitespace is accepted. A format failure is a ``parse_error``: it is never
  retried automatically, it consumes its planned sample slot, and the original
  output is preserved verbatim. Retrying only the responses that violated the
  format would condition the realised sample on format compliance.
* Unresolved research decisions fail closed instead of picking a silent
  default.

The runner takes its clock, sleep function and random source by injection, so
every path is deterministic under test and no test ever sleeps or calls out.
"""

from __future__ import annotations

import csv
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .design import load_items
from .providers import (
    ProviderAdapter,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    RetryableProviderError,
    sampling_parameters_omitted,
    temperature_on_the_wire,
)
from .results import RESULT_REQUIRED_FIELDS, parse_binary_label


# Statuses written to the raw JSONL log.
STATUS_SUCCESS = "success"
STATUS_DRY_RUN = "dry_run"
STATUS_API_ERROR = "api_error"
STATUS_PARSE_ERROR = "parse_error"

# Only a success counts toward the three independent samples per cell.
SAMPLE_BEARING_STATUSES = frozenset({STATUS_SUCCESS})

# A completion was received, so the planned sample slot is spent. A parse_error
# belongs here even though it bears no label: the slot is not refilled by a new
# call, because replacing only the format violations would make the realised
# sample depend on format compliance.
SLOT_CONSUMING_STATUSES = frozenset({STATUS_SUCCESS, STATUS_PARSE_ERROR})

# The only text handling policy that is implemented. The design records the
# source-encoding question as unresolved, so no normalization is applied and no
# default is assumed.
TEXT_POLICY_AS_IS = "as_is_latin1"
IMPLEMENTED_TEXT_POLICIES = frozenset({TEXT_POLICY_AS_IS})

CONFIRMED_SELECTION_STATUS = "confirmed_by_user"


class ExecutionBlocked(RuntimeError):
    """Raised when an unresolved decision gate forbids the requested action."""


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed its hard call or cost cap."""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with full jitter."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("Backoff delays must be non-negative")
        if self.multiplier < 1:
            raise ValueError("Backoff multiplier must be at least 1")

    def delay_for(self, attempt: int, jitter: float) -> float:
        """Return the sleep duration before retrying after ``attempt`` failures.

        ``jitter`` is a value in ``[0, 1)`` supplied by the injected random
        source, giving full jitter over the capped exponential window.
        """

        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        window = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (self.multiplier ** (attempt - 1)),
        )
        return window * jitter


@dataclass(frozen=True)
class BudgetPolicy:
    """Hard caps that must be supplied explicitly for any live run."""

    max_calls: int
    max_usd: float

    def __post_init__(self) -> None:
        if self.max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if self.max_usd <= 0:
            raise ValueError("max_usd must be greater than zero")


@dataclass
class RunSummary:
    """Counters returned by :func:`run_manifest`."""

    mode: str
    live: bool
    tasks_in_manifest: int = 0
    already_complete: int = 0
    attempted: int = 0
    succeeded: int = 0
    api_errors: int = 0
    parse_errors: int = 0
    blocked: int = 0
    dry_run_records: int = 0
    provider_calls: int = 0
    retries: int = 0
    blockers: list[str] = field(default_factory=list)
    output_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "live": self.live,
            "tasks_in_manifest": self.tasks_in_manifest,
            "already_complete": self.already_complete,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "api_errors": self.api_errors,
            "parse_errors": self.parse_errors,
            "blocked": self.blocked,
            "dry_run_records": self.dry_run_records,
            "provider_calls": self.provider_calls,
            "retries": self.retries,
            "blockers": list(self.blockers),
            "output_path": self.output_path,
        }


def utc_now_iso(clock: Callable[[], datetime] | None = None) -> str:
    now = clock() if clock is not None else datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def read_manifest(path: str | Path) -> list[dict[str, str]]:
    """Read a manifest CSV produced by ``chapter3_design.py``."""

    manifest_path = Path(path)
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Manifest {manifest_path} contains no tasks")
    task_ids = [row["task_id"] for row in rows]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError(f"Manifest {manifest_path} contains duplicate task IDs")
    return rows


def load_completed_task_ids(
    path: str | Path,
    completed_statuses: frozenset[str] | set[str] = SLOT_CONSUMING_STATUSES,
) -> set[str]:
    """Return task IDs already recorded as complete in an append-only log.

    Malformed trailing lines are ignored so that a log truncated by an
    interrupted run can still be resumed.

    For a live run a task is complete once a completion was received, so both a
    success and a ``parse_error`` block a re-send. An ``api_error``, where no
    completion arrived, is retried on the next run. That asymmetry is the whole
    point: re-sending only the tasks whose output broke the format would rebuild
    the sample out of the responses that happened to comply.

    A dry run also treats a prior ``dry_run`` record as complete, which makes
    repeated dry runs idempotent rather than duplicating planning records.
    """

    log_path = Path(path)
    if not log_path.exists():
        return set()

    completed: set[str] = set()
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") in completed_statuses and record.get("task_id"):
                completed.add(str(record["task_id"]))
    return completed


def _ends_without_newline(log_path: Path) -> bool:
    """True when the file has content whose last byte is not a newline.

    That is the signature of a run killed mid-write. Appending directly would
    concatenate the next record onto the partial line and corrupt it.
    """

    if not log_path.exists() or log_path.stat().st_size == 0:
        return False
    with log_path.open("rb") as handle:
        handle.seek(-1, 2)
        return handle.read(1) != b"\n"


def append_record(path: str | Path, record: Mapping[str, Any]) -> None:
    """Append one JSON record. The file is opened in append mode only.

    A partial line left by an interrupted run is terminated first, so the
    truncated fragment stays isolated on its own line and is skipped by the
    readers instead of swallowing the next record.
    """

    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    repair_newline = _ends_without_newline(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        if repair_newline:
            handle.write("\n")
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def build_user_prompt(prompt_text: str, source_text: str, text_policy: str) -> str:
    """Compose the user message under an explicitly chosen text policy.

    The source-encoding decision is unresolved, so the only implemented policy
    passes the decoded text through unchanged. Nothing is stripped, repaired or
    re-encoded silently.
    """

    if text_policy not in IMPLEMENTED_TEXT_POLICIES:
        raise ExecutionBlocked(
            f"Text handling policy {text_policy!r} is not implemented. The source "
            "encoding decision is unresolved, so no normalization rule is applied. "
            f"Implemented policies: {sorted(IMPLEMENTED_TEXT_POLICIES)}"
        )
    return f"{prompt_text}\n\n{source_text}"


def _row_value(task: Mapping[str, Any], field: str) -> Any:
    """Read a per-row setting from a manifest, treating blanks as absent.

    A manifest read back from CSV yields strings, and an absent value arrives as
    an empty string rather than as ``None``.
    """

    raw = task.get(field)
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text and text.lower() not in {"none", "null"} else None


def max_output_tokens_for(
    task: Mapping[str, Any],
    settings: Mapping[str, Any],
    default: int = 16,
) -> int:
    """The output cap for one task, preferring the manifest row.

    The two arms use different caps, so the cap belongs to the row, not to the
    model. The model-level ``request_settings`` value remains a fallback for the
    single-arm manifests, which carry no per-row cap.
    """

    row = _row_value(task, "max_output_tokens")
    if row is not None:
        return int(row)
    return int(settings.get("max_output_tokens", default))


def temperature_for(
    task: Mapping[str, Any],
    settings: Mapping[str, Any],
) -> float | None:
    """The temperature for one task, preferring the manifest row.

    ``None`` means no temperature parameter is placed on the wire at all. The
    provider's own default then applies, which is what the policy prescribes
    where the control is unavailable: the parameter is omitted, never simulated.
    """

    row = _row_value(task, "temperature_requested")
    if row is not None:
        return float(row)
    value = settings.get("temperature_requested", settings.get("temperature"))
    return None if value is None else float(value)


def requested_provider_from(settings: Mapping[str, Any]) -> str | None:
    """The upstream backend the configuration pinned, if it pinned one.

    Recorded next to the one that actually served the call, so that a router
    quietly moving between backends is visible in the data rather than only in
    the config that asked for it.
    """

    only = settings.get("openrouter_provider_only")
    if only:
        return ",".join(str(name) for name in only)
    # The Hugging Face route pins its provider inside the model id; the setting
    # is the configuration's own declaration of the same choice, which the
    # adapter refuses to send unless the two agree.
    declared = settings.get("huggingface_provider")
    if declared:
        return str(declared)
    return None


def reasoning_config_from(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The reasoning configuration as it was requested, recorded verbatim."""

    config: dict[str, Any] = {}
    for key in ("reasoning", "reasoning_effort", "thinking"):
        if settings.get(key) is not None:
            config[key] = settings[key]
    return config


def route_for(model: Mapping[str, Any]) -> str:
    """Return the adapter key used to reach a model.

    ``provider`` names the model family. An optional ``api_route`` names the
    service actually called, so a model can be reached through an aggregator
    while the record still states plainly which route produced it.
    """

    return str(model.get("api_route") or model["provider"])


def collect_blockers(config: Mapping[str, Any], model_ids: Iterable[str]) -> list[str]:
    """List unresolved decision gates that apply to the requested models."""

    blockers: list[str] = []
    wanted = set(model_ids)
    by_id = {model["id"]: model for model in config.get("models", [])}
    for model_id in sorted(wanted):
        model = by_id.get(model_id)
        if model is None:
            blockers.append(f"Model {model_id!r} is not present in the frozen configuration")
            continue
        if model.get("selection_status") != CONFIRMED_SELECTION_STATUS:
            blockers.append(
                f"Model {model_id!r} ({model.get('api_model')!r}) has selection_status "
                f"{model.get('selection_status')!r}; an exact model must be confirmed and "
                "recorded before live calls"
            )
    return blockers


def _index_items(config: Mapping[str, Any], project_root: str | Path) -> dict[str, dict[str, str]]:
    return {row["item_id"]: row for row in load_items(config, project_root)}


def _base_record(task: Mapping[str, str], started_at: str) -> dict[str, Any]:
    """Seed a result record with every field the validator requires."""

    record: dict[str, Any] = {name: None for name in RESULT_REQUIRED_FIELDS}
    record.update(
        {
            "task_id": task["task_id"],
            "item_id": task["item_id"],
            "model_id": task["model_id"],
            "api_model_requested": task["api_model_requested"],
            "prompt_id": task["prompt_id"],
            "replicate_id": int(task["replicate_id"]),
            "text_sha256": task["text_sha256"],
            "prompt_sha256": task["prompt_sha256"],
            "config_sha256": task["config_sha256"],
            "started_at_utc": started_at,
            "attempt_count": 0,
        }
    )
    # Provenance beyond the minimum validator schema.
    record["study_id"] = task.get("study_id")
    record["provider"] = task.get("provider")
    record["prompt_family"] = task.get("prompt_family")
    return record


def execute_task(
    task: Mapping[str, str],
    adapter: ProviderAdapter,
    request: ProviderRequest,
    *,
    retry_policy: RetryPolicy,
    sleep: Callable[[float], None],
    jitter_source: Callable[[], float],
    clock: Callable[[], datetime] | None = None,
    base_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one manifest task to a single terminal record.

    Exactly one record is produced regardless of how many attempts were needed.
    ``attempt_count`` reports the technical attempts; only a ``success`` status
    contributes one of the independent samples for the cell.

    Technical failures, where no completion arrived, are retried under the
    backoff policy. A ``parse_error`` is not: the provider answered, the slot is
    spent, and the original output is kept verbatim in ``raw_response``.

    ``base_record`` lets a caller seed the record from its own manifest schema.
    The two-arm runner supplies one, because its rows name ``template_id`` and
    ``sample_index`` and must never be translated into the single-arm spelling.
    """

    started_at = utc_now_iso(clock)
    started_monotonic = time.monotonic()
    record = dict(base_record) if base_record is not None else _base_record(task, started_at)
    record.setdefault("started_at_utc", started_at)
    record.setdefault("attempt_count", 0)
    requested_provider = requested_provider_from(request.settings)
    reasoning_config = reasoning_config_from(request.settings)

    last_error_type: str | None = None
    last_error_message: str | None = None
    # The transport status of the last attempt, whichever way it ended. A failed
    # call carries it on the error, a successful one on the response, and a
    # client that cannot see it leaves it None rather than guessing 200.
    last_http_status: int | None = None
    last_response: ProviderResponse | None = None
    status = STATUS_API_ERROR
    parsed_label: int | None = None
    retries = 0

    for attempt in range(1, retry_policy.max_attempts + 1):
        record["attempt_count"] = attempt
        try:
            response = adapter.complete(request)
        except ProviderError as error:
            last_error_type = type(error).__name__
            last_error_message = str(error)
            code = getattr(error, "status_code", None)
            last_http_status = code if isinstance(code, int) and not isinstance(code, bool) else None
            status = STATUS_API_ERROR
            if isinstance(error, RetryableProviderError) and attempt < retry_policy.max_attempts:
                retries += 1
                sleep(retry_policy.delay_for(attempt, jitter_source()))
                continue
            break

        last_response = response
        last_http_status = response.http_status
        try:
            parsed_label = parse_binary_label(response.text)
        except ValueError as error:
            last_error_type = "ParseError"
            last_error_message = str(error)
            status = STATUS_PARSE_ERROR
            # The provider answered. The slot is spent and the original output
            # is kept verbatim. Retrying here would resample only the responses
            # that broke the format, so it is not done.
            break

        status = STATUS_SUCCESS
        last_error_type = None
        last_error_message = None
        break

    completed_at = utc_now_iso(clock)
    latency_ms = int((time.monotonic() - started_monotonic) * 1000)

    record.update(
        {
            "status": status,
            "parsed_label": parsed_label if status == STATUS_SUCCESS else None,
            "raw_response": last_response.text if last_response is not None else None,
            "api_model_returned": (
                last_response.api_model_returned if last_response is not None else None
            ),
            "provider_request_id": (
                last_response.provider_request_id if last_response is not None else None
            ),
            "system_fingerprint": (
                last_response.system_fingerprint if last_response is not None else None
            ),
            "input_tokens": last_response.input_tokens if last_response is not None else None,
            "output_tokens": last_response.output_tokens if last_response is not None else None,
            "stop_reason": last_response.stop_reason if last_response is not None else None,
            # Always present, so a truncation is visible rather than absorbed
            # into the parse_error count. Never inferred when the provider is
            # silent about it.
            "finish_reason": last_response.stop_reason if last_response is not None else None,
            "finish_reason_reported": (
                last_response is not None and last_response.stop_reason is not None
            ),
            "upstream_provider": (
                last_response.upstream_provider if last_response is not None else None
            ),
            # Which backend the configuration asked for, alongside the one that
            # actually served the call. A silent divergence between the two is
            # the failure this pair exists to make visible.
            "requested_provider": requested_provider,
            # Never assume zero: null plus a false *_reported flag keeps "not
            # reported" distinguishable from "reported as none".
            "reasoning_tokens": (
                last_response.reasoning_tokens if last_response is not None else None
            ),
            "reasoning_tokens_reported": (
                last_response.reasoning_tokens_reported if last_response is not None else False
            ),
            # The usage field the count came from; null when nothing was reported.
            "reasoning_tokens_source": (
                last_response.reasoning_tokens_source if last_response is not None else None
            ),
            # Anthropic content blocks of type thinking / redacted_thinking. Null
            # where the API has no such blocks or no response arrived.
            "thinking_blocks": (
                last_response.thinking_blocks if last_response is not None else None
            ),
            "redacted_thinking_blocks": (
                last_response.redacted_thinking_blocks if last_response is not None else None
            ),
            # Where the serving backend was named. A gateway may state it in
            # the body, in a header, or not at all, and a record that only said
            # "deepinfra" could not be audited for which of the three it was.
            "upstream_provider_source": (
                last_response.upstream_provider_source if last_response is not None else None
            ),
            "cost": last_response.cost if last_response is not None else None,
            "cost_reported": (
                last_response.cost_reported if last_response is not None else False
            ),
            # A credited charge and a provider's own estimate are both
            # "reported" and are not the same number. Summing them without the
            # distinction would overstate what the second one establishes.
            "cost_source": (
                last_response.cost_source if last_response is not None else None
            ),
            "cost_is_provider_estimate": (
                last_response.cost_is_provider_estimate if last_response is not None else False
            ),
            # Prompt tokens served from cache, billed at a lower rate. Null
            # means the provider did not say, never that none were cached.
            "cached_input_tokens": (
                last_response.cached_input_tokens if last_response is not None else None
            ),
            # Prompt tokens written to the cache, priced apart from reads and
            # from ordinary input. Null means not reported.
            "cache_write_input_tokens": (
                last_response.cache_write_input_tokens if last_response is not None else None
            ),
            "cost_estimated": (
                last_response.cost_estimated if last_response is not None else None
            ),
            "cost_estimate_basis": (
                last_response.cost_estimate_basis if last_response is not None else None
            ),
            "reasoning_config_sent": reasoning_config,
            "request_settings": (
                dict(last_response.request_settings) if last_response is not None else None
            ),
            "completed_at_utc": completed_at,
            "latency_ms": latency_ms,
            "error_type": last_error_type,
            "error_message": last_error_message,
            # Recorded for every terminal status, so a parse_error that arrived
            # over a clean 200 is distinguishable from one that did not.
            "http_status": last_http_status,
            "retry_count": retries,
            "counts_as_sample": status in SAMPLE_BEARING_STATUSES,
            "slot_consumed": status in SLOT_CONSUMING_STATUSES,
            "is_remediation": False,
            # The settings actually used for this call, which the two-arm design
            # takes from the manifest row rather than from the model.
            "max_output_tokens": request.max_output_tokens,
            # What the design asked for, from the manifest row.
            "temperature_requested": request.temperature,
            # What was placed on the wire. None means the parameter was omitted
            # and the provider's own default applied. It is never simulated.
            "temperature_parameter_sent": temperature_on_the_wire(request),
            "temperature_control": _temperature_control(request),
            # The documented provider limitation behind an omission, if any.
            "sampling_parameters_policy": request.settings.get("sampling_parameters"),
            "temperature_control_source": request.settings.get(
                "temperature_verification_source"
            ),
        }
    )
    return record


def _temperature_control(request: ProviderRequest) -> str:
    """How the temperature was controlled on this call.

    ``unavailable``: the provider documents that it rejects the parameter, so the
    design's value was recorded and nothing was sent. ``unverified``: a value was
    sent and its effect has not been confirmed against a live response.
    """

    if sampling_parameters_omitted(request.settings):
        return "unavailable"
    return "unverified" if request.temperature is not None else "unavailable_or_omitted"


def run_manifest(
    *,
    config: Mapping[str, Any],
    manifest_path: str | Path,
    output_path: str | Path,
    project_root: str | Path = ".",
    mode: str = "pilot",
    live: bool = False,
    budget: BudgetPolicy | None = None,
    adapter_factory: Callable[[str], ProviderAdapter] | None = None,
    text_policy: str = TEXT_POLICY_AS_IS,
    retry_policy: RetryPolicy | None = None,
    resume: bool = True,
    limit: int | None = None,
    model_ids: Iterable[str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter_source: Callable[[], float] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> RunSummary:
    """Execute a manifest in dry-run or live mode.

    ``live=False`` (the default) never constructs a provider client and never
    calls ``adapter_factory``. A live run additionally requires a
    :class:`BudgetPolicy` and refuses to start while any decision gate for the
    requested models is unresolved.
    """

    retry_policy = retry_policy or RetryPolicy()
    jitter_source = jitter_source or random.random
    summary = RunSummary(mode=mode, live=live, output_path=str(output_path))

    tasks = read_manifest(manifest_path)

    # Restricting the run to a subset of models lets a single-provider key
    # exercise only its own tasks. Decision gates are then evaluated on the
    # selected models only.
    if model_ids is not None:
        wanted = set(model_ids)
        unknown = wanted - {model["id"] for model in config.get("models", [])}
        if unknown:
            raise ExecutionBlocked(
                f"Unknown model ids: {sorted(unknown)}. "
                f"Configured: {sorted(model['id'] for model in config.get('models', []))}"
            )
        tasks = [task for task in tasks if task["model_id"] in wanted]
        if not tasks:
            raise ExecutionBlocked(
                f"No manifest task matches model ids {sorted(wanted)}"
            )

    summary.tasks_in_manifest = len(tasks)

    selected_models = {task["model_id"] for task in tasks}
    blockers = collect_blockers(config, selected_models)
    summary.blockers = list(blockers)

    if live:
        if budget is None:
            raise ExecutionBlocked(
                "A live run requires an explicit hard budget cap (max calls and max USD). "
                "Live execution is disabled by default."
            )
        if config.get("execution", {}).get("live_calls_enabled") is not False:
            raise ExecutionBlocked(
                "The frozen configuration must keep live_calls_enabled false; the live "
                "flag is supplied per run, not stored in the design file."
            )
        if adapter_factory is None:
            raise ExecutionBlocked("A live run requires an adapter factory")
        if blockers:
            raise ExecutionBlocked(
                "Live execution is blocked by unresolved decision gates:\n- "
                + "\n- ".join(blockers)
            )

    # A live run treats a task as complete once a completion was received, so a
    # parse_error is not re-sent and its slot is not refilled. Only an api_error,
    # where nothing came back, is retried. A dry run also counts prior dry_run
    # records, which keeps repeated dry runs idempotent.
    completed_statuses = (
        SLOT_CONSUMING_STATUSES if live else SLOT_CONSUMING_STATUSES | {STATUS_DRY_RUN}
    )
    completed = load_completed_task_ids(output_path, completed_statuses) if resume else set()
    pending = [task for task in tasks if task["task_id"] not in completed]
    summary.already_complete = len(tasks) - len(pending)

    if limit is not None:
        pending = pending[:limit]

    if live and budget is not None and len(pending) > budget.max_calls:
        raise BudgetExceeded(
            f"This run would send {len(pending)} calls, exceeding the hard cap of "
            f"{budget.max_calls}. Raise the cap deliberately or narrow the manifest."
        )

    items = _index_items(config, project_root)
    prompts = {prompt["id"]: prompt for prompt in config["prompts"]}
    models = {model["id"]: model for model in config["models"]}
    system_prompt = config["system_prompt"]
    text_column = config["dataset"]["text_column"]

    adapters: dict[str, ProviderAdapter] = {}

    for task in pending:
        item = items.get(task["item_id"])
        if item is None:
            raise ExecutionBlocked(f"Manifest item {task['item_id']!r} is not in the dataset")
        prompt = prompts[task["prompt_id"]]
        model = models[task["model_id"]]
        settings = dict(model.get("request_settings") or {})

        user_prompt = build_user_prompt(prompt["text"], item[text_column], text_policy)
        request = ProviderRequest(
            api_model=model["api_model"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens_for(task, settings),
            temperature=temperature_for(task, settings),
            settings=settings,
        )

        route = route_for(model)

        if not live:
            started_at = utc_now_iso(clock)
            record = _base_record(task, started_at)
            record.update(
                {
                    "api_route": route,
                    "status": STATUS_DRY_RUN,
                    "parsed_label": None,
                    "raw_response": None,
                    "api_model_returned": None,
                    "completed_at_utc": started_at,
                    "latency_ms": 0,
                    "attempt_count": 0,
                    "retry_count": 0,
                    "counts_as_sample": False,
                    "slot_consumed": False,
                    "is_remediation": False,
                    "finish_reason": None,
                    "finish_reason_reported": False,
                    "max_output_tokens": request.max_output_tokens,
                    "temperature_requested": request.temperature,
                    "temperature_parameter_sent": request.temperature,
                    "requested_provider": requested_provider_from(settings),
                    "reasoning_config_sent": reasoning_config_from(settings),
                    "reasoning_tokens": None,
                    "reasoning_tokens_reported": False,
                    "cost": None,
                    "cost_reported": False,
                    "error_type": None,
                    "error_message": None,
                    "provider": model["provider"],
                    "planned_request_settings": settings,
                    "user_prompt_chars": len(user_prompt),
                    "system_prompt_chars": len(system_prompt),
                    "text_policy": text_policy,
                    "blockers": blockers,
                }
            )
            append_record(output_path, record)
            summary.dry_run_records += 1
            summary.attempted += 1
            continue

        if route not in adapters:
            adapters[route] = adapter_factory(route)  # type: ignore[misc]
        adapter = adapters[route]

        record = execute_task(
            task,
            adapter,
            request,
            retry_policy=retry_policy,
            sleep=sleep,
            jitter_source=jitter_source,
            clock=clock,
        )
        record["text_policy"] = text_policy
        record["provider"] = model["provider"]
        record["api_route"] = route
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


def count_samples_by_cell(records: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    """Count successful, sample-bearing records per item-model-prompt cell.

    Retries and failures are excluded by construction, so this is the quantity
    that must reach three for every cell.
    """

    counts: dict[tuple[str, str, str], int] = {}
    for record in records:
        if record.get("status") not in SAMPLE_BEARING_STATUSES:
            continue
        key = (
            str(record["item_id"]),
            str(record["model_id"]),
            str(record["prompt_id"]),
        )
        counts[key] = counts.get(key, 0) + 1
    return counts


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Read every well-formed record from an append-only JSONL log."""

    log_path = Path(path)
    if not log_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


__all__ = [
    "BudgetExceeded",
    "BudgetPolicy",
    "ExecutionBlocked",
    "RetryPolicy",
    "RunSummary",
    "SAMPLE_BEARING_STATUSES",
    "SLOT_CONSUMING_STATUSES",
    "STATUS_API_ERROR",
    "STATUS_DRY_RUN",
    "STATUS_PARSE_ERROR",
    "STATUS_SUCCESS",
    "TEXT_POLICY_AS_IS",
    "append_record",
    "build_user_prompt",
    "collect_blockers",
    "count_samples_by_cell",
    "execute_task",
    "load_completed_task_ids",
    "max_output_tokens_for",
    "read_manifest",
    "reasoning_config_from",
    "requested_provider_from",
    "read_records",
    "run_manifest",
    "temperature_for",
    "utc_now_iso",
]
