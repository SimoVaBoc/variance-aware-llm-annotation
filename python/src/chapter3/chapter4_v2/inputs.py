"""Task-level analytical input: planned slots, their observed state, and the items.

The new analysis is built from validated task-level records and the planned
design, never from older aggregate or report outputs. Every planned call is a
*slot* identified by item, model, template and sample index, and every slot ends
in exactly one of four states:

* ``valid_label``: a terminal ``success`` record whose label the strict parser
  reproduces from the raw response;
* ``terminal_invalid``: a terminal ``parse_error``. The slot is spent and the
  label stays missing; it is never replaced;
* ``technical_failure``: only ``api_error`` records, no completion;
* ``planned_unobserved``: no record at all.

The four are kept apart because they mean different things to the reader, even
though all three non-valid states leave the label missing.

Duplicates, records outside the plan, identity or hash mismatches, remediation
records and labels that the parser does not reproduce are *integrity errors*:
they are collected in full and raised, never treated as ordinary missing
labels. Nothing here suggests or launches a new call to repair an input.

Campaign text and raw responses are read only to validate and are not carried
into the result.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..analysis import HASH_FIELDS
from ..catalog import LABEL_ORDERS
from ..execution import (
    SLOT_CONSUMING_STATUSES,
    STATUS_API_ERROR,
    STATUS_PARSE_ERROR,
    STATUS_SUCCESS,
)
from ..results import parse_binary_label
from .spec import AnalysisSpec

SLOT_VALID = "valid_label"
SLOT_TERMINAL_INVALID = "terminal_invalid"
SLOT_TECHNICAL_FAILURE = "technical_failure"
SLOT_UNOBSERVED = "planned_unobserved"
SLOT_STATES = (SLOT_VALID, SLOT_TERMINAL_INVALID, SLOT_TECHNICAL_FAILURE, SLOT_UNOBSERVED)

ARM_CB = "carlson"
ARM_VA = "camuffo"

#: Statuses an analytical log may contain. ``dry_run`` is a planning record and
#: has no place in an analytical input.
KNOWN_STATUSES = frozenset(SLOT_CONSUMING_STATUSES | {STATUS_API_ERROR})

COVARIATE_FIELDS = ("HUMAN", "success", "lgoal", "subcategory", "year")


class InputIntegrityError(RuntimeError):
    """The records, the manifest and the plan do not describe one consistent run."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        shown = "\n- ".join(self.problems[:25])
        more = f"\n- ... and {len(self.problems) - 25} more" if len(self.problems) > 25 else ""
        super().__init__(f"{len(self.problems)} integrity problem(s):\n- {shown}{more}")


@dataclass(frozen=True, order=True)
class SlotKey:
    """One planned call, in design terms."""

    item_id: str
    model_key: str
    template_id: str
    sample_index: int


@dataclass(frozen=True)
class PlannedTask:
    task_id: str
    key: SlotKey
    arm: str
    label_order: str | None
    row: Mapping[str, Any]


@dataclass(frozen=True)
class Slot:
    key: SlotKey
    task_id: str
    arm: str
    label_order: str | None
    state: str
    label: int | None
    n_technical_records: int = 0


@dataclass(frozen=True)
class ItemRecord:
    """Benchmark item with validated covariates. Invalid values are None, with a reason."""

    item_id: str
    human: int | None
    success: int | None
    lgoal: float | None
    subcategory: str | None
    year: str | None
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedDesign:
    """The planned slots for a set of items, taken from the specification."""

    item_ids: tuple[str, ...]
    model_keys: tuple[str, ...]
    cb_templates: tuple[str, ...]
    va_templates: tuple[str, ...]
    va_generations: int

    @classmethod
    def from_spec(cls, spec: AnalysisSpec, item_ids: Iterable[str]) -> "PlannedDesign":
        return cls(item_ids=tuple(sorted(item_ids)), model_keys=spec.model_keys,
                   cb_templates=spec.cb_template_ids, va_templates=spec.va_template_ids,
                   va_generations=spec.va_generations)

    def arm_of(self, template_id: str) -> str | None:
        if template_id in self.cb_templates:
            return ARM_CB
        if template_id in self.va_templates:
            return ARM_VA
        return None

    def expected_keys(self) -> set[SlotKey]:
        keys: set[SlotKey] = set()
        for item in self.item_ids:
            for model in self.model_keys:
                keys.update(SlotKey(item, model, t, 1) for t in self.cb_templates)
                keys.update(SlotKey(item, model, t, s) for t in self.va_templates
                            for s in range(1, self.va_generations + 1))
        return keys


@dataclass
class TaskLevelInput:
    """Everything the analysis modules read. Built only by :func:`assemble_input`."""

    design: PlannedDesign
    items: dict[str, ItemRecord]
    slots: dict[SlotKey, Slot]
    data_kind: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def state_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, Counter] = {}
        for slot in self.slots.values():
            out.setdefault(slot.arm, Counter())[slot.state] += 1
        return {arm: {s: counts.get(s, 0) for s in SLOT_STATES} for arm, counts in sorted(out.items())}


# --------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _binary(value: Any) -> int | None:
    text = None if value is None else str(value).strip()
    return {"0": 0, "1": 1}.get(text) if text is not None else None


def parse_item(row: Mapping[str, Any]) -> ItemRecord:
    """Validate types and finiteness. Values are not recoded, pooled or re-logged."""

    issues: list[str] = []
    human = _binary(row.get("HUMAN"))
    if human is None:
        issues.append("HUMAN_not_binary")
    success = _binary(row.get("success"))
    if success is None:
        issues.append("success_not_binary")
    lgoal: float | None = None
    try:
        lgoal = float(str(row.get("lgoal")).strip())
        if not math.isfinite(lgoal):
            raise ValueError
    except (TypeError, ValueError):
        lgoal = None
        issues.append("lgoal_not_finite")
    subcategory = None if _blank(row.get("subcategory")) else str(row["subcategory"])
    if subcategory is None:
        issues.append("subcategory_missing")
    year = None if _blank(row.get("year")) else str(row["year"])
    if year is None:
        issues.append("year_missing")
    return ItemRecord(item_id=str(row["item_id"]), human=human, success=success, lgoal=lgoal,
                      subcategory=subcategory, year=year, issues=tuple(issues))


def parse_items(rows: Iterable[Mapping[str, Any]]) -> dict[str, ItemRecord]:
    items: dict[str, ItemRecord] = {}
    duplicated: list[str] = []
    for row in rows:
        record = parse_item(row)
        if record.item_id in items:
            duplicated.append(record.item_id)
        items[record.item_id] = record
    if duplicated:
        raise InputIntegrityError([f"duplicate item_id {i!r}" for i in sorted(set(duplicated))])
    return items


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def plan_tasks(
    design: PlannedDesign,
    manifests: Mapping[str, Sequence[Mapping[str, Any]]],
    collection_model_ids: Mapping[str, str],
) -> dict[str, PlannedTask]:
    """Map every manifest row onto a planned slot, and the plan onto the manifests.

    ``manifests`` and ``collection_model_ids`` are keyed by design model key; the
    collection's own ``model_id`` (which can differ from the design key) must
    appear on every row of its manifest.
    """

    problems: list[str] = []
    tasks: dict[str, PlannedTask] = {}
    by_key: dict[SlotKey, str] = {}
    orders: dict[tuple[str, str, str], set] = {}
    items = set(design.item_ids)

    if set(manifests) != set(design.model_keys):
        problems.append(f"manifests are given for {sorted(manifests)}, the design has "
                        f"{sorted(design.model_keys)}")

    for model_key, rows in sorted(manifests.items()):
        expected_model_id = collection_model_ids.get(model_key)
        for row in rows:
            task_id = str(row.get("task_id") or "")
            where = task_id or "<row without task_id>"
            if not task_id:
                problems.append("a manifest row has no task_id")
                continue
            if task_id in tasks:
                problems.append(f"{where}: duplicate task_id in the manifests")
                continue
            if str(row.get("model_id")) != str(expected_model_id):
                problems.append(f"{where}: model_id {row.get('model_id')!r} is not the bound "
                                f"collection model {expected_model_id!r}")
            template = str(row.get("template_id"))
            arm = design.arm_of(template)
            if arm is None:
                problems.append(f"{where}: template {template!r} is outside the planned design")
                continue
            if str(row.get("arm")) != arm:
                problems.append(f"{where}: arm {row.get('arm')!r} does not match template {template!r}")
            try:
                sample = int(row.get("sample_index"))
            except (TypeError, ValueError):
                problems.append(f"{where}: sample_index {row.get('sample_index')!r}")
                continue
            limit = 1 if arm == ARM_CB else design.va_generations
            if not 1 <= sample <= limit:
                problems.append(f"{where}: sample_index {sample} outside 1..{limit}")
            item = str(row.get("item_id"))
            if item not in items:
                problems.append(f"{where}: item {item!r} is not a planned item")
            order = None if _blank(row.get("label_order")) else str(row["label_order"])
            if arm == ARM_CB and order is not None:
                problems.append(f"{where}: a CB task carries a label order")
            if arm == ARM_VA:
                if order not in LABEL_ORDERS:
                    problems.append(f"{where}: VA task with label order {order!r}")
                orders.setdefault((item, model_key, template), set()).add(order)
            if _truthy(row.get("is_remediation")):
                problems.append(f"{where}: a remediation row is not a planned primary task")
            key = SlotKey(item, model_key, template, sample)
            if key in by_key:
                problems.append(f"{where}: slot {key} is already planned as {by_key[key]}")
                continue
            by_key[key] = task_id
            tasks[task_id] = PlannedTask(task_id, key, arm, order, dict(row))

    for cell, seen in sorted(orders.items()):
        if len(seen) != 1:
            problems.append(f"cell {cell} varies its label order across S")
    missing = sorted(design.expected_keys() - set(by_key))
    if missing:
        problems.append(f"{len(missing)} planned slot(s) are absent from the manifests, "
                        f"first {missing[0]}")
    if problems:
        raise InputIntegrityError(problems)
    return tasks


# --------------------------------------------------------------------------
# observations
# --------------------------------------------------------------------------


def _record_problems(task: PlannedTask, record: Mapping[str, Any]) -> list[str]:
    where = task.task_id
    row = task.row
    out: list[str] = []
    for name in ("item_id", "model_id", "arm", "template_id"):
        if str(record.get(name)) != str(row.get(name)):
            out.append(f"{where}: {name} is {record.get(name)!r}, the manifest says {row.get(name)!r}")
    try:
        if int(record.get("sample_index")) != task.key.sample_index:
            out.append(f"{where}: sample_index differs from the manifest")
    except (TypeError, ValueError):
        out.append(f"{where}: sample_index {record.get('sample_index')!r}")
    if (None if _blank(record.get("label_order")) else str(record["label_order"])) != task.label_order:
        out.append(f"{where}: label_order differs from the manifest")
    for name in HASH_FIELDS:
        planned = row.get(name) or None
        if planned is not None and (record.get(name) or None) != planned:
            out.append(f"{where}: {name} differs from the manifest")
    if _truthy(record.get("is_remediation")):
        out.append(f"{where}: remediation records are not primary observations")
    status = record.get("status")
    if status not in KNOWN_STATUSES:
        out.append(f"{where}: status {status!r} is not an analytical status")
    return out


def _terminal_label(task: PlannedTask, record: Mapping[str, Any]) -> tuple[int | None, list[str]]:
    """Re-check the stored label with the strict parser; never trust it blindly."""

    where = task.task_id
    if "raw_response" not in record:
        return None, [f"{where}: terminal record without raw_response cannot be verified"]
    raw = record["raw_response"]
    try:
        reparsed: int | None = parse_binary_label("" if raw is None else raw)
    except ValueError:
        reparsed = None
    stored = record.get("parsed_label")
    if record["status"] == STATUS_SUCCESS:
        if stored not in (0, 1) or isinstance(stored, bool):
            return None, [f"{where}: success without a binary label"]
        if reparsed != stored:
            return None, [f"{where}: stored label is not what the strict parser reads"]
        return int(stored), []
    # parse_error
    if stored is not None:
        return None, [f"{where}: parse_error carries a label"]
    if reparsed is not None:
        return None, [f"{where}: parse_error on a response the strict parser accepts"]
    return None, []


def observe_slots(
    tasks: Mapping[str, PlannedTask],
    records: Iterable[Mapping[str, Any]],
) -> dict[SlotKey, Slot]:
    """Reduce the append-only history to one state per planned slot."""

    problems: list[str] = []
    history: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        task_id = str(record.get("task_id") or "")
        if task_id not in tasks:
            problems.append(f"{task_id or '<record without task_id>'}: record is not in the plan")
            continue
        history.setdefault(task_id, []).append(record)

    slots: dict[SlotKey, Slot] = {}
    for task_id, task in sorted(tasks.items()):
        records_for_task = history.get(task_id, [])
        for record in records_for_task:
            problems.extend(_record_problems(task, record))
        terminal = [r for r in records_for_task if r.get("status") in SLOT_CONSUMING_STATUSES]
        technical = [r for r in records_for_task if r.get("status") == STATUS_API_ERROR]
        if len(terminal) > 1:
            problems.append(f"{task_id}: {len(terminal)} terminal records; the slot was spent twice")
            continue
        if terminal:
            label, label_problems = _terminal_label(task, terminal[0])
            problems.extend(label_problems)
            state = SLOT_VALID if terminal[0]["status"] == STATUS_SUCCESS else SLOT_TERMINAL_INVALID
        else:
            label = None
            state = SLOT_TECHNICAL_FAILURE if technical else SLOT_UNOBSERVED
        slots[task.key] = Slot(task.key, task_id, task.arm, task.label_order, state, label,
                               n_technical_records=len(technical))
    if problems:
        raise InputIntegrityError(problems)
    return slots


def assemble_input(
    spec: AnalysisSpec,
    item_rows: Iterable[Mapping[str, Any]],
    manifests: Mapping[str, Sequence[Mapping[str, Any]]],
    collection_model_ids: Mapping[str, str],
    records: Iterable[Mapping[str, Any]],
    *,
    data_kind: str,
    provenance: Mapping[str, Any] | None = None,
) -> TaskLevelInput:
    """Validate and assemble the analytical input. ``data_kind`` is mandatory."""

    if data_kind not in {"synthetic", "empirical"}:
        raise ValueError("data_kind must be 'synthetic' or 'empirical'")
    items = parse_items(item_rows)
    design = PlannedDesign.from_spec(spec, items)
    tasks = plan_tasks(design, manifests, collection_model_ids)
    slots = observe_slots(tasks, records)
    return TaskLevelInput(design=design, items=items, slots=slots, data_kind=data_kind,
                          provenance={**spec.identity(), **dict(provenance or {})})


__all__ = [
    "ARM_CB",
    "ARM_VA",
    "SLOT_STATES",
    "SLOT_TECHNICAL_FAILURE",
    "SLOT_TERMINAL_INVALID",
    "SLOT_UNOBSERVED",
    "SLOT_VALID",
    "InputIntegrityError",
    "ItemRecord",
    "PlannedDesign",
    "PlannedTask",
    "Slot",
    "SlotKey",
    "TaskLevelInput",
    "assemble_input",
    "observe_slots",
    "parse_item",
    "parse_items",
    "plan_tasks",
]
