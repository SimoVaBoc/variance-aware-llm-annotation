"""H1: observed repeated-call variation in each VA model x prompt cell (descriptive).

For each of the nine cells, only complete binary triplets (all three planned
generations valid) are used. The primary summary is the proportion of those
triplets that are not unanimous.

Mean pairwise disagreement over the three pairs of each triplet is computed on
exactly the same triplets and is reported as an identity, not as a second
finding: in a binary triplet that is not unanimous exactly two of the three
pairs disagree, and in a unanimous one none does, so the mean pairwise
disagreement is always two thirds of the non-unanimous proportion. The identity
is checked on every call.

Incomplete triplets are reported separately, by their number of valid labels.
There is no repeated-call comparator for CB, which uses one designated
generation per configuration.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import combinations
from typing import Any

from .inputs import SlotKey, TaskLevelInput
from .samples import h1_supports
from .scores import fraction_record
from .analysis_status import COMPUTED, NOT_COMPUTABLE

IDENTITY = Fraction(2, 3)


def triplet_summary(triplets: list[tuple[int, int, int]]) -> dict[str, Any]:
    """Non-unanimous proportion and mean pairwise disagreement on the same triplets."""

    n = len(triplets)
    if n == 0:
        return {"n_complete": 0, "n_not_unanimous": 0, "not_unanimous_proportion": None,
                "mean_pairwise_disagreement": None}
    not_unanimous = sum(1 for t in triplets if len(set(t)) > 1)
    pair_rates = [Fraction(sum(a != b for a, b in combinations(t, 2)), 3) for t in triplets]
    proportion = Fraction(not_unanimous, n)
    mean_pairwise = sum(pair_rates, Fraction(0)) / n
    if mean_pairwise != IDENTITY * proportion:
        raise AssertionError("mean pairwise disagreement must equal 2/3 of the proportion")
    return {"n_complete": n, "n_not_unanimous": not_unanimous,
            "not_unanimous_proportion": proportion, "mean_pairwise_disagreement": mean_pairwise}


def h1_variation(data: TaskLevelInput) -> dict[str, Any]:
    cells = []
    for support in h1_supports(data):
        triplets = [tuple(data.slots[SlotKey(item, support.model_key, support.template_id, s)].label
                          for s in range(1, data.design.va_generations + 1))
                    for item in support.complete]
        summary = triplet_summary(triplets)
        cells.append({
            "model_key": support.model_key, "template_id": support.template_id,
            "status": COMPUTED if summary["n_complete"] else NOT_COMPUTABLE,
            "reason": None if summary["n_complete"] else "no complete triplet in this cell",
            "n_complete": summary["n_complete"],
            "n_not_unanimous": summary["n_not_unanimous"],
            "not_unanimous_proportion": fraction_record(summary["not_unanimous_proportion"]),
            "mean_pairwise_disagreement": fraction_record(summary["mean_pairwise_disagreement"]),
            "identity": "mean pairwise disagreement = 2/3 x not-unanimous proportion "
                        "(same triplets; not an independent finding)",
            "incomplete": {"n": len(support.partial),
                           "by_valid_count": dict(sorted(Counter(support.partial.values()).items()))},
        })
    return {"analysis": "H1", "data_kind": data.data_kind, "cells": cells,
            "cb_comparator": None,
            "note": "Descriptive. CB uses one designated generation and has no repeated-call "
                    "comparator. The status says only whether the summary was computed; no "
                    "criterion is applied."}


__all__ = ["IDENTITY", "h1_variation", "triplet_summary"]
