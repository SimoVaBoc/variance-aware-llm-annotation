"""H2 core: prompt sensitivity at constant label order, exact conditional test per model.

**Sample.** For each campaign and model the pair (A, B) is the two prompt variants
with the same planned ``label_order``, taken from the manifest before any
validity or label is seen (:func:`.samples.h2_supports`); a planned pattern other
than two-plus-one is an integrity error and no other pair is ever chosen. I_m
holds the campaigns whose six selected responses are all valid; the third
prompt does not affect inclusion. HUMAN does not enter the test.

**Statistic.** With S_A and S_B the positive counts of the two triplets and
T = S_A + S_B, ``Q_i = (2 S_A - T)^2 / 6`` and ``Q_m = sum Q_i``. The square keeps
opposite-direction differences between campaigns from cancelling.

**Exact conditional reference.** Under the null, S_A | T is hypergeometric
(N = 6, K = T, n = 3): the 20 allocations of the six responses into two
triplets are equally likely. Hence Q_i is 0 for T in {0, 6}, 1/6 for T in {1, 5},
0 or 2/3 with probabilities 3/5 and 2/5 for T in {2, 4}, and 1/6 or 3/2 with
probabilities 9/10 and 1/10 for T = 3. Across campaigns,
``6 Q_m = n15 + n3 + 4X + 8Z`` with X ~ Bin(n24, 2/5) and Z ~ Bin(n3, 1/10)
independent. The p-value is the upper tail including equality, computed exactly
in integers and fractions: no mid-p, no Monte Carlo. The alternative is
non-directional for prompt differences although the tail is upper for Q.

**Edge cases.** N = 0: not evaluable. N > 0 with no stratum 2 <= T <= 4: p = 1 with
the flag 'uninformative conditional Q'. Holm runs over the three planned
model-specific tests at familywise 0.05, reporting raw and adjusted p-values. If
fewer than three tests are evaluable, the family is reported as incomplete and no
adjusted p-value is produced (D-H2-04 open); the family is never shrunk.

**Descriptive rates** on the same I_m, averaged with equal weight over campaigns:
within-prompt disagreements over the six within-triplet pairs, and
between-prompt disagreements over all nine cross-triplet pairs. No
between-minus-within contrast is computed.

**Sufficient assumptions** (documented, not verified by any audit): S1 the six
calls of a selected pair are conditionally independent given the design; S2
the ternary output probabilities (label 1, label 0, invalid) are constant
within each repeated configuration; S3 output vectors of different campaigns
are independent given the design, which gives the product law across strata;
S4 validity probabilities are positive. Under S1-S2 conditioning on a complete
pair cancels the validity factors, so the six valid labels are independent
Bernoulli; under the null they are i.i.d. within the stratum. Label-order
matching does not randomise execution order, so the test does not by itself
identify a causal effect of wording. Non-rejection is not equivalence.

**Not enabled here** (visible as pending): temporal sensitivity with W <= 300 s
(D-H2-02), the appendix bootstrap of the two rates and the separate temporal
Holm family (D-H2-03), and the P-S ANOVA candidate (D-H2-05). The framework
bootstrap is not used for H2.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from math import comb
from typing import Any, Sequence

from .inputs import SlotKey, TaskLevelInput
from .pending import refuse
from .samples import H2Support, class_counts, h2_supports
from .scores import fraction_record
from .spec import AnalysisSpec

UNINFORMATIVE = "uninformative conditional Q"
FAMILY_SIZE = 3


def null_law(t: int) -> dict[Fraction, Fraction]:
    """Law of Q_i given T = t, from the hypergeometric law of S_A (exact)."""

    if not 0 <= t <= 6:
        raise ValueError("T must lie between 0 and 6")
    law: dict[Fraction, Fraction] = {}
    for s_a in range(max(0, t - 3), min(3, t) + 1):
        weight = Fraction(comb(t, s_a) * comb(6 - t, 3 - s_a), comb(6, 3))
        q = Fraction((2 * s_a - t) ** 2, 6)
        law[q] = law.get(q, Fraction(0)) + weight
    return law


def strata(totals: Sequence[int]) -> dict[str, int]:
    return {"n06": sum(t in (0, 6) for t in totals), "n15": sum(t in (1, 5) for t in totals),
            "n24": sum(t in (2, 4) for t in totals), "n3": sum(t == 3 for t in totals)}


def upper_tail(six_q_observed: int, n15: int, n24: int, n3: int) -> Fraction:
    """P(6 Q_null >= 6 Q_obs) with 6 Q_null = n15 + n3 + 4X + 8Z, exactly."""

    p = Fraction(0)
    for x, z in product(range(n24 + 1), range(n3 + 1)):
        if n15 + n3 + 4 * x + 8 * z >= six_q_observed:
            p += (comb(n24, x) * Fraction(2, 5) ** x * Fraction(3, 5) ** (n24 - x)
                  * comb(n3, z) * Fraction(1, 10) ** z * Fraction(9, 10) ** (n3 - z))
    return p


def holm(p_values: Sequence[Fraction]) -> list[Fraction]:
    """Holm step-down adjusted p-values, exactly, in the input order."""

    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [Fraction(0)] * m
    running = Fraction(0)
    for rank, index in enumerate(order):
        running = max(running, min(Fraction(1), (m - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def _labels(data: TaskLevelInput, item: str, model: str, template: str) -> list[int]:
    return [data.slots[SlotKey(item, model, template, s)].label
            for s in range(1, data.design.va_generations + 1)]


def model_test(data: TaskLevelInput, support: H2Support) -> dict[str, Any]:
    members = support.members
    record: dict[str, Any] = {"model_key": support.model_key, "N": len(members),
                              "class_composition": class_counts(data, members),
                              "data_kind": data.data_kind}
    if not members:
        return {**record, "status": "not_evaluable", "reason": "N = 0", "p_value": None}
    totals, squares, within, between = [], [], [], []
    for item in members:
        pair = support.selections[item].pair
        a, b = (_labels(data, item, support.model_key, t) for t in pair)
        s_a, t = sum(a), sum(a) + sum(b)
        totals.append(t)
        squares.append((2 * s_a - t) ** 2)
        within.append(Fraction(sum(x != y for i, x in enumerate(a) for y in a[i + 1:])
                               + sum(x != y for i, x in enumerate(b) for y in b[i + 1:]), 6))
        between.append(Fraction(sum(x != y for x in a for y in b), 9))
    counts = strata(totals)
    six_q = sum(squares)
    q_m = Fraction(six_q, 6)
    n_q = counts["n24"] + counts["n3"]
    if n_q == 0:
        p, flag = Fraction(1), UNINFORMATIVE
    else:
        p, flag = upper_tail(six_q, counts["n15"], counts["n24"], counts["n3"]), None
    return {**record, "status": "evaluable", "reason": None, "N_Q": n_q, "strata": counts,
            "Q_m": fraction_record(q_m), "six_Q_m": six_q, "p_value": p,
            "p_value_record": fraction_record(p), "flag": flag,
            "within_prompt_rate": fraction_record(sum(within, Fraction(0)) / len(members)),
            "between_prompt_rate": fraction_record(sum(between, Fraction(0)) / len(members))}


def h2_core(spec: AnalysisSpec, data: TaskLevelInput) -> dict[str, Any]:
    tests = [model_test(data, support) for support in h2_supports(data)]
    alpha = Fraction(spec.data["modules"]["h2_core"]["familywise_alpha"])
    evaluable = [t for t in tests if t["status"] == "evaluable"]
    if len(tests) == FAMILY_SIZE and len(evaluable) == FAMILY_SIZE:
        adjusted = holm([t["p_value"] for t in tests])
        for t, adj in zip(tests, adjusted):
            t["holm_adjusted_p"] = fraction_record(adj)
            t["rejected_at_familywise_alpha"] = adj <= alpha
        family = {"status": "complete", "size": FAMILY_SIZE, "familywise_alpha": str(alpha)}
    else:
        for t in tests:
            t["holm_adjusted_p"] = None
        family = {"status": "incomplete", "size_planned": FAMILY_SIZE,
                  "evaluable_tests": len(evaluable), "familywise_alpha": str(alpha),
                  "reason": "fewer than three evaluable tests; no adjusted p-values are produced "
                            "and the family is not shrunk (D-H2-04 open)"}
    for t in tests:
        if t.get("p_value") is not None:
            t["p_value"] = fraction_record(t["p_value"])
    return {"analysis": "H2 core", "data_kind": data.data_kind, "tests": tests,
            "holm_family": family,
            "pending": [{"module": m, "waiting_on": spec.module(m).get("decision_ids", [])}
                        for m in ("h2_temporal_sensitivity",
                                  "h2_ancillary_bootstrap_and_temporal_holm", "h2_ps_anova")],
            "between_minus_within_contrast": None}


def h2_temporal_sensitivity(spec: AnalysisSpec, *args: Any, **kwargs: Any) -> None:
    refuse(spec, "h2_temporal_sensitivity")
    raise NotImplementedError("temporal sensitivity is not implemented")


def h2_ancillary_bootstrap(spec: AnalysisSpec, *args: Any, **kwargs: Any) -> None:
    refuse(spec, "h2_ancillary_bootstrap_and_temporal_holm")
    raise NotImplementedError("the appendix bootstrap is not implemented")


def h2_ps_anova(spec: AnalysisSpec, *args: Any, **kwargs: Any) -> None:
    refuse(spec, "h2_ps_anova")
    raise NotImplementedError("the P-S ANOVA candidate is outside the primary plan")


__all__ = [
    "FAMILY_SIZE",
    "UNINFORMATIVE",
    "h2_ancillary_bootstrap",
    "h2_core",
    "h2_ps_anova",
    "h2_temporal_sensitivity",
    "holm",
    "model_test",
    "null_law",
    "strata",
    "upper_tail",
]
