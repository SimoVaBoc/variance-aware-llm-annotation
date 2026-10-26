"""Primary label vectors: designated CB labels and the complete VA hierarchy.

The primary rule is strict and has no fallback:

* a VA configuration after S needs exactly its three planned generations, all
  valid; their majority is the label;
* G needs all 27 planned VA calls valid, and is the hierarchical majority
  S -> P -> M of those calls, never the pooled majority of the 27;
* the within-model S -> P vector (an H4 input) needs the nine planned calls of
  its model, all valid;
* a CB configuration uses its single designated generation as it is.

Anything short of that is missing, with a recorded reason, and is never read as
label 0. Validation of *which* calls these are has already happened at the
input boundary: every slot here is a planned task identity.

The historical two-valid-concordant rule survives as
:func:`legacy_two_valid_concordant`, named separately and delegating to the
unchanged historical module, for provenance only. Nothing on the primary path
calls it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..hierarchy import majority as _historical_majority
from .inputs import SLOT_VALID, SlotKey, TaskLevelInput
from .procedures import (
    KIND_CB,
    KIND_G,
    KIND_VA_COMPONENT,
    KIND_VA_POST_S,
    KIND_VA_POST_SP,
    Procedure,
    Registry,
)

PRIMARY_RULE_ID = "primary_complete_hierarchical_majority_v2"
LEGACY_RULE_ID = "legacy_two_valid_concordant_v1"

REASON_VA_INCOMPLETE = "va_generations_incomplete"
REASON_G_OUTSIDE_I27 = "g_outside_i27"
REASON_POST_SP_INCOMPLETE = "va_post_sp_inputs_incomplete"


@dataclass(frozen=True)
class LabelVector:
    """One procedure's labels over the items. ``None`` is missing, with a reason."""

    procedure_id: str
    kind: str
    labels: Mapping[str, int | None]
    missing_reasons: Mapping[str, str]

    def label(self, item_id: str) -> int | None:
        return self.labels[item_id]


def complete_majority(labels: Sequence[int | None], required: int) -> int | None:
    """Majority of exactly ``required`` valid labels; missing if any one is missing."""

    if required % 2 == 0 or required < 1:
        raise ValueError("the primary majority needs an odd number of contributions")
    if len(labels) != required:
        raise ValueError(f"expected {required} planned contributions, got {len(labels)}")
    if any(label is None for label in labels):
        return None
    return 1 if 2 * sum(labels) > required else 0  # type: ignore[arg-type]


def legacy_two_valid_concordant(labels: Sequence[int | None]) -> int | None:
    """The historical rule, for provenance only: two concordant valid votes decide.

    Delegates to ``src.chapter3.hierarchy.majority`` so that the historical
    behaviour is reproduced, not re-implemented. Never used by the primary path.
    """

    return _historical_majority(list(labels)).label


def _slot_reason(states: Sequence[str]) -> str:
    bad = sorted({s for s in states if s != SLOT_VALID})
    return f"{REASON_VA_INCOMPLETE}:{'+'.join(bad)}"


class _Hierarchy:
    """Per-item VA hierarchy over the input's slots, computed once."""

    def __init__(self, data: TaskLevelInput):
        self.data = data
        self.design = data.design

    def generations(self, item: str, model: str, template: str):
        return [self.data.slots[SlotKey(item, model, template, s)]
                for s in range(1, self.design.va_generations + 1)]

    def post_s(self, item: str, model: str, template: str) -> tuple[int | None, str | None]:
        slots = self.generations(item, model, template)
        label = complete_majority([s.label if s.state == SLOT_VALID else None for s in slots],
                                  self.design.va_generations)
        return label, (None if label is not None else _slot_reason([s.state for s in slots]))

    def post_sp(self, item: str, model: str) -> int | None:
        votes = [self.post_s(item, model, t)[0] for t in self.design.va_templates]
        return complete_majority(votes, len(votes))

    def g(self, item: str) -> int | None:
        votes = [self.post_sp(item, m) for m in self.design.model_keys]
        return complete_majority(votes, len(votes))

    def all_va_valid(self, item: str) -> bool:
        return all(slot.state == SLOT_VALID
                   for m in self.design.model_keys for t in self.design.va_templates
                   for slot in self.generations(item, m, t))


def va_complete_items(data: TaskLevelInput) -> tuple[str, ...]:
    """Items whose every planned VA call is valid: the eligibility set for G (I27)."""

    hierarchy = _Hierarchy(data)
    return tuple(i for i in data.design.item_ids if hierarchy.all_va_valid(i))


def _vector(procedure: Procedure, data: TaskLevelInput, hierarchy: _Hierarchy,
            complete: frozenset[str]) -> LabelVector:
    labels: dict[str, int | None] = {}
    reasons: dict[str, str] = {}
    for item in data.design.item_ids:
        reason: str | None = None
        if procedure.kind in (KIND_CB, KIND_VA_COMPONENT):
            sample = procedure.sample_index or 1
            slot = data.slots[SlotKey(item, procedure.model_key, procedure.template_id, sample)]
            label = slot.label if slot.state == SLOT_VALID else None
            reason = None if label is not None else f"slot_{slot.state}"
        elif procedure.kind == KIND_VA_POST_S:
            label, reason = hierarchy.post_s(item, procedure.model_key, procedure.template_id)
        elif procedure.kind == KIND_VA_POST_SP:
            label = hierarchy.post_sp(item, procedure.model_key)
            reason = None if label is not None else REASON_POST_SP_INCOMPLETE
        elif procedure.kind == KIND_G:
            label = hierarchy.g(item) if item in complete else None
            reason = None if label is not None else REASON_G_OUTSIDE_I27
        else:  # pragma: no cover - the registry has no other kinds
            raise ValueError(procedure.kind)
        labels[item] = label
        if label is None:
            reasons[item] = reason or "missing"
    return LabelVector(procedure.procedure_id, procedure.kind, labels, reasons)


def build_vectors(data: TaskLevelInput, registry: Registry) -> dict[str, LabelVector]:
    """Every registered vector, keyed by procedure ID, coincident ones included."""

    hierarchy = _Hierarchy(data)
    complete = frozenset(va_complete_items(data))
    return {p.procedure_id: _vector(p, data, hierarchy, complete) for p in registry.all()}


__all__ = [
    "LEGACY_RULE_ID",
    "PRIMARY_RULE_ID",
    "REASON_G_OUTSIDE_I27",
    "REASON_POST_SP_INCOMPLETE",
    "REASON_VA_INCOMPLETE",
    "LabelVector",
    "build_vectors",
    "complete_majority",
    "legacy_two_valid_concordant",
    "va_complete_items",
]
