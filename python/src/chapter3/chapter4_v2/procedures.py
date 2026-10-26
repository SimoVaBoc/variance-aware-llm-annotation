"""Canonical procedure registry: fixed, unique IDs built from the planned design.

Three disjoint sets, never merged:

* the **31 primary procedures**: 21 CB configurations (strategy x model, the
  designated single generation), nine VA configurations after the S majority
  (prompt x model) and the final aggregate G (S -> P -> M);
* the **27 VA components**: one whole vector per model x prompt x generation,
  inputs to H3 only;
* the **three within-model S -> P vectors**, inputs to H4 only.

IDs come from the specification's ``procedures.id_scheme`` and the design's
model keys and template IDs, so they are fixed before any label is seen.
Procedures whose vectors happen to coincide keep separate identities: nothing
here, or downstream, deduplicates them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .spec import AnalysisSpec

KIND_CB = "cb"
KIND_VA_POST_S = "va_post_s"
KIND_G = "g"
KIND_VA_COMPONENT = "va_component"
KIND_VA_POST_SP = "va_post_sp"

PRIMARY_KINDS = (KIND_CB, KIND_VA_POST_S, KIND_G)


class RegistryError(ValueError):
    """The registry does not reproduce the counts the specification declares."""


@dataclass(frozen=True)
class Procedure:
    procedure_id: str
    kind: str
    model_key: str | None = None
    template_id: str | None = None
    sample_index: int | None = None

    @property
    def is_primary(self) -> bool:
        return self.kind in PRIMARY_KINDS


@dataclass(frozen=True)
class Registry:
    primary: tuple[Procedure, ...]
    va_components: tuple[Procedure, ...]
    va_post_sp: tuple[Procedure, ...]

    def by_id(self) -> dict[str, Procedure]:
        return {p.procedure_id: p for p in self.all()}

    def all(self) -> tuple[Procedure, ...]:
        return self.primary + self.va_components + self.va_post_sp

    def primary_of_kind(self, kind: str) -> tuple[Procedure, ...]:
        return tuple(p for p in self.primary if p.kind == kind)

    @property
    def g(self) -> Procedure:
        return self.primary_of_kind(KIND_G)[0]


def build_registry(spec: AnalysisSpec) -> Registry:
    scheme = spec.data["procedures"]["id_scheme"]
    models, cb, va = spec.model_keys, spec.cb_template_ids, spec.va_template_ids

    def make(kind: str, model=None, template=None, sample=None) -> Procedure:
        pid = scheme[kind].format(model_key=model, template_id=template, sample_index=sample)
        return Procedure(pid, kind, model, template, sample)

    primary = tuple(make(KIND_CB, m, t) for m in models for t in cb)
    primary += tuple(make(KIND_VA_POST_S, m, t) for m in models for t in va)
    primary += (make(KIND_G),)
    components = tuple(make(KIND_VA_COMPONENT, m, t, s) for m in models for t in va
                       for s in range(1, spec.va_generations + 1))
    post_sp = tuple(make(KIND_VA_POST_SP, m) for m in models)
    registry = Registry(primary, components, post_sp)

    counts = spec.data["procedures"]["primary_counts"]
    problems = []
    for kind in PRIMARY_KINDS:
        if len(registry.primary_of_kind(kind)) != counts[kind]:
            problems.append(f"{kind}: {len(registry.primary_of_kind(kind))} != {counts[kind]}")
    if len(primary) != counts["total"]:
        problems.append(f"primary total {len(primary)} != {counts['total']}")
    if len(components) != spec.data["procedures"]["h3_component_count"]:
        problems.append("h3 component count differs from the specification")
    if len(post_sp) != spec.data["procedures"]["h4_within_model_count"]:
        problems.append("h4 within-model count differs from the specification")
    ids = [p.procedure_id for p in registry.all()]
    if len(ids) != len(set(ids)):
        problems.append("procedure IDs are not unique")
    if problems:
        raise RegistryError("; ".join(problems))
    return registry


__all__ = [
    "KIND_CB",
    "KIND_G",
    "KIND_VA_COMPONENT",
    "KIND_VA_POST_S",
    "KIND_VA_POST_SP",
    "PRIMARY_KINDS",
    "Procedure",
    "Registry",
    "RegistryError",
    "build_registry",
]
