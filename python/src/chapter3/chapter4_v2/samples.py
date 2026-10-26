"""Sample membership as a first-class output: members, class counts, exclusion reasons.

Every sample is fixed by validity and the planned design alone. No membership
rule reads whether a label is correct, so no sample is selected on performance.

* **B**: the benchmark items with a binary HUMAN class.
* **I27**: items of B whose 27 planned VA calls are all valid labels.
* **R**: items of B with binary success, finite lgoal, subcategory and year, and
  all 31 primary labels valid. R is fixed here, once, before any fit.
* **H1 supports**: for each model x prompt cell, the complete triplets; partial
  triplets are reported separately with their valid count.
* **H2 I_m**: for each model, the items whose manifest-selected equal-order
  prompt pair has all six responses valid. The pair comes from the planned
  label orders alone; a planned pattern other than two-plus-one is an integrity
  error, and no other pair is ever substituted. The third prompt does not
  affect inclusion.

H1 and H2 do not use HUMAN, so their supports range over all benchmark items;
the class composition is reported for documentation only.

An item can fail a sample for several reasons at once. Reasons are all
recorded, so reason counts overlap and are never presented as disjoint.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .aggregation import LabelVector
from .inputs import SLOT_VALID, InputIntegrityError, SlotKey, TaskLevelInput
from .procedures import Registry

CLASS_POSITIVE = "positive"
CLASS_NEGATIVE = "negative"
CLASS_UNKNOWN = "human_not_binary"

REASON_NOT_IN_B = "not_in_B"
REASON_HUMAN = "human_not_binary"
COVARIATE_REASONS = ("success_not_binary", "lgoal_not_finite", "subcategory_missing",
                     "year_missing")


def _class_of(data: TaskLevelInput, item: str) -> str:
    human = data.items[item].human
    return {1: CLASS_POSITIVE, 0: CLASS_NEGATIVE}.get(human, CLASS_UNKNOWN)  # type: ignore[arg-type]


def class_counts(data: TaskLevelInput, items) -> dict[str, int]:
    counts = Counter(_class_of(data, i) for i in items)
    out = {CLASS_POSITIVE: counts[CLASS_POSITIVE], CLASS_NEGATIVE: counts[CLASS_NEGATIVE]}
    if counts[CLASS_UNKNOWN]:
        out[CLASS_UNKNOWN] = counts[CLASS_UNKNOWN]
    return out


@dataclass(frozen=True)
class SampleMembership:
    name: str
    definition: str
    members: tuple[str, ...]
    class_counts: Mapping[str, int]
    exclusions: Mapping[str, tuple[str, ...]]
    data_kind: str
    excluded_class_counts: Mapping[str, int] = field(default_factory=dict)

    def reason_counts(self, data: TaskLevelInput) -> dict[str, dict[str, int]]:
        """Items per reason, by class. Overlapping: one item can carry several reasons."""

        out: dict[str, Counter] = {}
        for item, reasons in self.exclusions.items():
            for reason in reasons:
                out.setdefault(reason, Counter())[_class_of(data, item)] += 1
        return {r: {"total": sum(c.values()), **dict(sorted(c.items()))}
                for r, c in sorted(out.items())}

    def as_record(self, data: TaskLevelInput) -> dict[str, Any]:
        return {
            "sample": self.name,
            "definition": self.definition,
            "data_kind": self.data_kind,
            "n_members": len(self.members),
            "class_counts": dict(self.class_counts),
            "n_excluded": len(self.exclusions),
            "excluded_class_counts": dict(self.excluded_class_counts),
            "exclusion_reason_counts": self.reason_counts(data),
            "exclusion_reason_counts_overlap": True,
            "members": list(self.members),
        }


def _membership(name: str, definition: str, data: TaskLevelInput, universe,
                reasons_of) -> SampleMembership:
    members, exclusions = [], {}
    for item in universe:
        reasons = tuple(sorted(set(reasons_of(item))))
        if reasons:
            exclusions[item] = reasons
        else:
            members.append(item)
    return SampleMembership(name, definition, tuple(members), class_counts(data, members),
                            exclusions, data.data_kind,
                            class_counts(data, exclusions))


def sample_b(data: TaskLevelInput) -> SampleMembership:
    return _membership(
        "B", "benchmark items with a binary HUMAN class", data, data.design.item_ids,
        lambda i: [REASON_HUMAN] if data.items[i].human is None else [])


def planned_benchmark_check(data: TaskLevelInput, b: SampleMembership, *,
                            planned_item_ids: Sequence[str] | None,
                            planned_counts: Mapping[str, int]) -> dict[str, Any]:
    """Planned versus actual benchmark, as a visible record. Never raises, never excludes.

    For the empirical run B is the planned list of campaigns. This check sets
    what the data show beside it: missing or extra campaigns, non-binary HUMAN
    labels and class sizes against the planned counts
    (``{"n_items", "positives", "negatives"}``). A difference is reported with
    ``status: "differs_from_plan"``; it is not a validity gate and it does not
    change B.
    """

    planned = None if planned_item_ids is None else sorted(planned_item_ids)
    actual = list(data.design.item_ids)
    counts = class_counts(data, actual)
    record: dict[str, Any] = {
        "data_kind": data.data_kind,
        "planned": {"n_items": planned_counts["n_items"],
                    "positives": planned_counts["positives"],
                    "negatives": planned_counts["negatives"],
                    "item_list_supplied": planned is not None},
        "actual": {"n_items": len(actual), "positives": counts[CLASS_POSITIVE],
                   "negatives": counts[CLASS_NEGATIVE],
                   "human_not_binary": sorted(b.exclusions)},
        "missing_from_data": [] if planned is None else sorted(set(planned) - set(actual)),
        "not_in_plan": [] if planned is None else sorted(set(actual) - set(planned)),
    }
    differences = []
    for key in ("n_items", "positives", "negatives"):
        if record["planned"][key] != record["actual"][key]:
            differences.append(f"{key}: planned {record['planned'][key]}, "
                               f"actual {record['actual'][key]}")
    # A benchmark member without a binary HUMAN class is an integrity discrepancy, named
    # item by item. How such a member would be scored is deliberately not decided here.
    record["integrity_discrepancies"] = [
        {"item_id": item, "issue": "member of B without a binary HUMAN class"}
        for item in record["actual"]["human_not_binary"]]
    record["scoring_of_members_without_binary_human"] = "not decided (D-SAMP-02)"
    if record["actual"]["human_not_binary"]:
        differences.append(f"{len(record['actual']['human_not_binary'])} campaign(s) without "
                           "a binary HUMAN class")
    if record["missing_from_data"] or record["not_in_plan"]:
        differences.append("the campaign list differs from the planned list")
    record["differences"] = differences
    record["status"] = "differs_from_plan" if differences else "matches_plan"
    return record


def _va_reasons(data: TaskLevelInput, item: str) -> list[str]:
    design = data.design
    return [f"va_{slot.state}"
            for m in design.model_keys for t in design.va_templates
            for s in range(1, design.va_generations + 1)
            if (slot := data.slots[SlotKey(item, m, t, s)]).state != SLOT_VALID]


def sample_i27(data: TaskLevelInput, b: SampleMembership) -> SampleMembership:
    in_b = set(b.members)
    return _membership(
        "I27", "items of B whose 27 planned VA calls are all valid labels", data,
        data.design.item_ids,
        lambda i: ([REASON_NOT_IN_B] if i not in in_b else []) + _va_reasons(data, i))


def sample_r(data: TaskLevelInput, b: SampleMembership, registry: Registry,
             vectors: Mapping[str, LabelVector]) -> SampleMembership:
    in_b = set(b.members)

    def reasons(item: str) -> list[str]:
        out = [REASON_NOT_IN_B] if item not in in_b else []
        out += [r for r in data.items[item].issues if r in COVARIATE_REASONS]
        out += [f"primary_label_missing:{p.kind}" for p in registry.primary
                if vectors[p.procedure_id].label(item) is None]
        return out

    return _membership(
        "R", "items of B with valid success and covariates and all 31 primary labels valid",
        data, data.design.item_ids, reasons)


@dataclass(frozen=True)
class TripletSupport:
    """H1 support of one model x prompt cell."""

    model_key: str
    template_id: str
    complete: tuple[str, ...]
    partial: Mapping[str, int]
    data_kind: str

    def as_record(self) -> dict[str, Any]:
        return {"model_key": self.model_key, "template_id": self.template_id,
                "data_kind": self.data_kind, "n_complete": len(self.complete),
                "n_partial": len(self.partial),
                "partial_by_valid_count": dict(sorted(Counter(self.partial.values()).items())),
                "complete": list(self.complete)}


def h1_supports(data: TaskLevelInput) -> list[TripletSupport]:
    design, out = data.design, []
    for m in design.model_keys:
        for t in design.va_templates:
            complete, partial = [], {}
            for item in design.item_ids:
                valid = sum(data.slots[SlotKey(item, m, t, s)].state == SLOT_VALID
                            for s in range(1, design.va_generations + 1))
                if valid == design.va_generations:
                    complete.append(item)
                else:
                    partial[item] = valid
            out.append(TripletSupport(m, t, tuple(complete), partial, data.data_kind))
    return out


@dataclass(frozen=True)
class PairSelection:
    item_id: str
    pair: tuple[str, str]
    shared_order: str
    third: str
    pair_complete: bool
    pair_states: tuple[str, ...]
    third_all_valid: bool


@dataclass(frozen=True)
class H2Support:
    model_key: str
    selections: Mapping[str, PairSelection]
    data_kind: str

    @property
    def members(self) -> tuple[str, ...]:
        return tuple(i for i, s in self.selections.items() if s.pair_complete)

    def as_record(self, data: TaskLevelInput) -> dict[str, Any]:
        excluded = [s for s in self.selections.values() if not s.pair_complete]
        return {
            "model_key": self.model_key, "data_kind": self.data_kind,
            "n_members": len(self.members),
            "class_composition": class_counts(data, self.members),
            "n_excluded_pair_incomplete": len(excluded),
            "planned_pairs": dict(sorted(Counter("/".join(s.pair)
                                                 for s in self.selections.values()).items())),
            "members_with_invalid_third_prompt": sum(
                1 for s in self.selections.values() if s.pair_complete and not s.third_all_valid),
            "members": list(self.members),
        }


def h2_supports(data: TaskLevelInput) -> list[H2Support]:
    """Per model, the manifest-selected equal-order pair of each item, and I_m."""

    design, out, problems = data.design, [], []
    for m in design.model_keys:
        selections: dict[str, PairSelection] = {}
        for item in design.item_ids:
            orders = {t: data.slots[SlotKey(item, m, t, 1)].label_order
                      for t in design.va_templates}
            by_order: dict[str, list[str]] = {}
            for t, o in orders.items():
                by_order.setdefault(str(o), []).append(t)
            shared = [o for o, ts in by_order.items() if len(ts) == 2]
            if len(design.va_templates) != 3 or len(by_order) != 2 or len(shared) != 1:
                problems.append(f"{item}/{m}: planned label orders {orders} are not two-plus-one")
                continue
            pair = tuple(sorted(by_order[shared[0]]))
            third = next(t for t in design.va_templates if t not in pair)
            pair_slots = [data.slots[SlotKey(item, m, t, s)] for t in pair
                          for s in range(1, design.va_generations + 1)]
            third_slots = [data.slots[SlotKey(item, m, third, s)]
                           for s in range(1, design.va_generations + 1)]
            selections[item] = PairSelection(
                item, pair, shared[0], third,
                pair_complete=all(s.state == SLOT_VALID for s in pair_slots),
                pair_states=tuple(s.state for s in pair_slots),
                third_all_valid=all(s.state == SLOT_VALID for s in third_slots))
        out.append(H2Support(m, selections, data.data_kind))
    if problems:
        raise InputIntegrityError(problems)
    return out


__all__ = [
    "CLASS_NEGATIVE",
    "CLASS_POSITIVE",
    "CLASS_UNKNOWN",
    "H2Support",
    "PairSelection",
    "SampleMembership",
    "TripletSupport",
    "class_counts",
    "h1_supports",
    "h2_supports",
    "planned_benchmark_check",
    "sample_b",
    "sample_i27",
    "sample_r",
]
