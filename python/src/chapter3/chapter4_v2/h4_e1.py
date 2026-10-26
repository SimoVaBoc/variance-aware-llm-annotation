"""H4 coefficient dispersion before and after P, and E1 BA-distance correspondence.

**H4** (descriptive). Nine post-S coefficients beta_mp and three within-model
post-S->P coefficients beta_m, all Firth on the same R. For each prompt the SD
across the three models uses denominator 3; D_pre is the mean of those three
SDs; D_post is the SD (denominator 3) of the three post-P coefficients;
Delta_D = D_pre - D_post. The percentage is reported only when D_pre > 0. Ranges
R_p and R_post are reported, and three outcomes are kept apart: contraction
(Delta_D > 0), final pairwise tolerance (R_post <= 0.41), and contraction that
crosses into the tolerance (Delta_D > 0, some R_p > 0.41, R_post <= 0.41). All 12
fits must be usable; otherwise the contrast is ``not_computable`` and each fit keeps
its own status. No bootstrap, p-value or minimum reduction. The SD of all nine
coefficients together is never used.

**E1** (descriptive). For the 31 primary procedures, BA on R against the absolute
Firth distance from HUMAN on R, so both axes use the same campaigns. BA on B
remains the decision score. CB, post-S VA and G are told apart, coincident
points keep every identity, and procedures without an available distance are
listed. No correlation, p-value or extra regression.
"""

from __future__ import annotations

import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aggregation import LabelVector
from .firth import USABLE, DownstreamResult
from .inputs import TaskLevelInput
from .procedures import Registry
from .scores import fraction_record, score_vector
from .spec import AnalysisSpec
from .analysis_status import COMPUTED, NOT_COMPUTABLE
from .thresholds import at_most


def population_sd(values: Sequence[float]) -> float:
    """SD with denominator n: the spread of this fixed set, not a population estimate."""

    mean = math.fsum(values) / len(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / len(values))


def h4_dispersion(spec: AnalysisSpec, downstream: DownstreamResult) -> dict[str, Any]:
    scheme = spec.data["procedures"]["id_scheme"]
    limit = spec.data["scores"]["thresholds"]["coefficient_distance_max"]
    models, prompts = spec.model_keys, spec.va_template_ids
    pre_ids = {(m, p): scheme["va_post_s"].format(model_key=m, template_id=p)
               for m in models for p in prompts}
    post_ids = {m: scheme["va_post_sp"].format(model_key=m) for m in models}
    fits = {pid: downstream.fits[pid] for pid in [*pre_ids.values(), *post_ids.values()]}
    record: dict[str, Any] = {
        "fits": {pid: {"status": f.status, "coefficient": f.coefficient,
                       "ci": None if f.ci is None else list(f.ci)} for pid, f in fits.items()},
        "n_fits_required": len(fits),
    }
    unusable = sorted(pid for pid, f in fits.items() if f.status != USABLE)
    if unusable:
        return {**record, "status": NOT_COMPUTABLE,
                "reason": f"{len(unusable)} of {len(fits)} fits not usable: {', '.join(unusable)}"}

    beta = {key: fits[pid].coefficient for key, pid in pre_ids.items()}
    s_p = {p: population_sd([beta[(m, p)] for m in models]) for p in prompts}
    r_p = {p: max(beta[(m, p)] for m in models) - min(beta[(m, p)] for m in models)
           for p in prompts}
    post = [fits[post_ids[m]].coefficient for m in models]
    d_pre = math.fsum(s_p.values()) / len(prompts)
    d_post = population_sd(post)
    delta = d_pre - d_post
    r_post = max(post) - min(post)
    contraction = delta > 0
    within = at_most(r_post, limit)
    crossing = contraction and any(not at_most(r, limit) for r in r_p.values()) and within
    return {**record, "status": COMPUTED, "reason": None,
            "sd_by_prompt": s_p, "D_pre": d_pre, "D_post": d_post, "Delta_D": delta,
            "percent_contraction": (100 * delta / d_pre) if d_pre > 0 else None,
            "range_by_prompt": r_p, "range_post": r_post,
            "outcomes": {"contraction": contraction, "final_within_tolerance": within,
                         "contraction_crossing_into_tolerance": crossing},
            "note": "Descriptive; the status says only whether the contrast was computed."}


def e1_points(data: TaskLevelInput, registry: Registry, vectors: Mapping[str, LabelVector],
              r_members: Sequence[str], downstream: DownstreamResult) -> dict[str, Any]:
    points, unavailable = [], []
    for procedure in registry.primary:
        pid = procedure.procedure_id
        ba = score_vector(vectors[pid], data, r_members, "R").ba
        distance = downstream.distance_to_human(pid)
        entry = {"procedure_id": pid, "group": procedure.kind, "ba_R": fraction_record(ba),
                 "distance_R": distance}
        if distance is None or ba is None:
            fit = downstream.fits[pid]
            entry["reason"] = (f"HUMAN fit {downstream.human.status}" if downstream.human.status
                               != USABLE else f"fit {fit.status}")
            unavailable.append(entry)
        else:
            points.append(entry)
    coincident: dict[tuple, list[str]] = defaultdict(list)
    for point in points:
        coincident[(point["ba_R"]["exact"], point["distance_R"])].append(point["procedure_id"])
    return {"sample": "R", "data_kind": data.data_kind, "points": points,
            "unavailable": unavailable,
            "coincident_points": [ids for ids in coincident.values() if len(ids) > 1],
            "note": "BA on R and distance on R; BA on B remains the decision score. "
                    "No correlation or test."}


def plot_e1(result: Mapping[str, Any], path: str | Path) -> Path:
    """A labelled scatter plot. Written only where the caller says."""

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    markers = {"cb": ("o", "CB"), "va_post_s": ("s", "VA after S"), "g": ("*", "G")}
    fig, ax = plt.subplots(figsize=(7, 5))
    for kind, (marker, label) in markers.items():
        pts = [p for p in result["points"] if p["group"] == kind]
        ax.scatter([p["distance_R"] for p in pts], [p["ba_R"]["value"] for p in pts],
                   marker=marker, label=label, alpha=0.8)
        for p in pts:
            ax.annotate(p["procedure_id"], (p["distance_R"], p["ba_R"]["value"]), fontsize=5)
    ax.set_xlabel("|beta_j - beta_HUMAN| on R (Firth)")
    ax.set_ylabel("BA on R")
    title = "E1: BA(R) against distance from HUMAN(R)"
    if result.get("data_kind") == "synthetic":
        title += " - SYNTHETIC DATA"
    ax.set_title(title)
    ax.legend()
    path = Path(path)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


__all__ = ["e1_points", "h4_dispersion", "plot_e1", "population_sd"]
