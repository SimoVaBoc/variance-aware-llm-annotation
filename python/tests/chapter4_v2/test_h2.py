"""H2 core: the conditional law derived by enumeration, exact tails, edge cases, Holm, rates.

The law of Q given T is derived here by enumerating, with itertools, the 20
allocations of six responses into two triplets; it is compared with the module
and with the table in the specification, not copied from either.
"""

import ast
from collections import Counter
from fractions import Fraction
from itertools import combinations, product

from _guard import PROJECT_ROOT, SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.h2 import (
    UNINFORMATIVE,
    h2_ancillary_bootstrap,
    h2_core,
    h2_ps_anova,
    h2_temporal_sensitivity,
    holm,
    null_law,
    upper_tail,
)
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.pending import DecisionPending
from src.chapter3.chapter4_v2.spec import load_spec

TEMPLATES = ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")


def enumerated_law(t):
    """Q over the 20 equally likely allocations of t positives among six responses."""
    responses = [1] * t + [0] * (6 - t)
    allocations = list(combinations(range(6), 3))
    assert len(allocations) == 20
    counts = Counter(Fraction((2 * sum(responses[i] for i in a) - t) ** 2, 6) for a in allocations)
    return {q: Fraction(c, 20) for q, c in counts.items()}


def brute_force_tail(totals, observed_six_q):
    """P(6Q >= observed) by enumerating every allocation in every stratum."""
    laws = [enumerated_law(t) for t in totals]
    p = Fraction(0)
    for combo in product(*(law.items() for law in laws)):
        six_q = sum(6 * q for q, _ in combo)
        weight = Fraction(1)
        for _, w in combo:
            weight *= w
        if six_q >= observed_six_q:
            p += weight
    return p


def pair_of(index):
    """The two equal-order prompts the fixture plans for the item at this position."""
    odd = sorted(TEMPLATES)[index % 3]
    return tuple(t for t in sorted(TEMPLATES) if t != odd)


class LawTests(SyntheticTestCase):
    def test_module_law_matches_enumeration_for_every_total(self):
        for t in range(7):
            self.assertEqual(null_law(t), enumerated_law(t), t)

    def test_specification_table_matches_enumeration(self):
        table = load_spec().module("h2_core")["null_law_of_Q_by_T"]
        for key, law in table.items():
            expected = {Fraction(q): Fraction(p) for q, p in law.items()}
            for t in (int(x) for x in key.split("|")):
                self.assertEqual(enumerated_law(t), expected, key)

    def test_six_q_reduces_to_counts_and_two_binomials(self):
        # Every allocation of strata T = (1, 2, 3, 4, 5): 6Q = n15 + n3 + 4X + 8Z, with X the
        # number of T in {2, 4} strata at Q = 2/3 and Z the number of T = 3 strata at Q = 3/2.
        totals = (1, 2, 3, 4, 5)
        for combo in product(*(enumerated_law(t) for t in totals)):
            x = sum(1 for t, q in zip(totals, combo) if t in (2, 4) and q == Fraction(2, 3))
            z = sum(1 for t, q in zip(totals, combo) if t == 3 and q == Fraction(3, 2))
            self.assertEqual(sum(6 * q for q in combo), 2 + 1 + 4 * x + 8 * z)

    def test_exact_tail_equals_brute_force_and_includes_equality(self):
        totals = (1, 2, 3, 4, 3)  # n15 = 1, n24 = 2, n3 = 2
        support = sorted({sum(6 * q for q in combo)
                          for combo in product(*(enumerated_law(t) for t in totals))})
        for observed in support:
            exact = upper_tail(observed, n15=1, n24=2, n3=2)
            self.assertEqual(exact, brute_force_tail(totals, observed), observed)
            if observed != support[-1]:
                self.assertGreater(exact, brute_force_tail(totals, observed + 1))
        self.assertEqual(upper_tail(support[0], 1, 2, 2), 1)

    def test_holm_step_down_is_exact_and_monotone(self):
        self.assertEqual(holm([Fraction(1, 100), Fraction(1, 50), Fraction(1, 2)]),
                         [Fraction(3, 100), Fraction(1, 25), Fraction(1, 2)])
        self.assertEqual(holm([Fraction(4, 100), Fraction(3, 100), Fraction(1, 2)]),
                         [Fraction(9, 100), Fraction(9, 100), Fraction(1, 2)])
        self.assertEqual(holm([Fraction(1, 2)] * 3), [Fraction(1)] * 3)


class CoreTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def build(self, patterns, model="terra_5_6", states=None, rows=None):
        """patterns: item -> (A triplet, B triplet) on the planned pair of that item."""
        items = [r["item_id"] for r in (rows or fx.make_item_rows(4))]
        pairs = {item: pair_of(i) for i, item in enumerate(items)}

        def label_of(k):
            if k.model_key == model and k.item_id in patterns and k.template_id in pairs[k.item_id]:
                a, b = patterns[k.item_id]
                triplet = a if k.template_id == pairs[k.item_id][0] else b
                return triplet[k.sample_index - 1]
            return 0

        return fx.build_input(self.spec, item_rows=rows, label_of=label_of, states=states), pairs

    def pick(self, result, model="terra_5_6"):
        return next(t for t in result["tests"] if t["model_key"] == model)

    def test_opposite_directions_do_not_cancel(self):
        data, _ = self.build({"SYN1": ((1, 1, 1), (0, 0, 0)), "SYN2": ((0, 0, 0), (1, 1, 1))})
        t = self.pick(h2_core(self.spec, data))
        # Both campaigns have T = 3 and Q = 3/2; positive shares cancel, Q does not.
        self.assertEqual((t["Q_m"]["exact"], t["six_Q_m"]), ("3/1", 18))
        self.assertEqual(t["strata"], {"n06": 2, "n15": 0, "n24": 0, "n3": 2})
        # 6Q_null = 2 + 8Z with Z ~ Bin(2, 1/10); observing 18 needs Z = 2.
        self.assertEqual(t["p_value"]["exact"], "1/100")
        self.assertIsNone(t["flag"])

    def test_constant_strata_give_p_one_with_the_flag(self):
        data, _ = self.build({"SYN1": ((1, 0, 0), (0, 0, 0)), "SYN2": ((1, 1, 1), (1, 1, 0))})
        t = self.pick(h2_core(self.spec, data))
        self.assertEqual((t["N_Q"], t["p_value"]["exact"], t["flag"]), (0, "1/1", UNINFORMATIVE))

    def test_third_prompt_invalidity_does_not_exclude_and_the_pair_is_fixed(self):
        rows = fx.make_item_rows(4)
        third = [t for t in TEMPLATES if t not in pair_of(0)][0]
        states = {SlotKey("SYN1", "terra_5_6", third, s): "parse_error" for s in (1, 2, 3)}
        data, pairs = self.build({"SYN1": ((1, 1, 0), (0, 0, 0))}, states=states, rows=rows)
        t = self.pick(h2_core(self.spec, data))
        self.assertEqual(t["N"], 4)
        # A broken selected pair excludes; no other pair is used instead.
        states = {SlotKey("SYN1", "terra_5_6", pairs["SYN1"][0], 2): "parse_error"}
        data, _ = self.build({}, states=states, rows=rows)
        self.assertEqual(self.pick(h2_core(self.spec, data))["N"], 3)

    def test_human_does_not_enter(self):
        patterns = {"SYN1": ((1, 1, 0), (0, 0, 1)), "SYN3": ((1, 0, 0), (1, 1, 1))}
        rows = fx.make_item_rows(4)
        flipped = fx.make_item_rows(4)
        for row in flipped:
            row["HUMAN"] = str(1 - int(row["HUMAN"]))
        a = h2_core(self.spec, self.build(patterns, rows=rows)[0])
        b = h2_core(self.spec, self.build(patterns, rows=flipped)[0])
        strip = lambda r: [{k: v for k, v in t.items() if k != "class_composition"} for t in r["tests"]]
        self.assertEqual(strip(a), strip(b))

    def test_within_and_between_rates_on_the_same_campaigns(self):
        data, _ = self.build({"SYN1": ((1, 0, 0), (1, 1, 0))}, rows=fx.make_item_rows(1))
        t = self.pick(h2_core(self.spec, data))
        # Within: A has 2 of 3 pairs disagreeing, B 2 of 3: 4/6. Between: 5 of 9 cross pairs.
        self.assertEqual(t["within_prompt_rate"]["exact"], "2/3")
        self.assertEqual(t["between_prompt_rate"]["exact"], "5/9")
        self.assertIsNone(h2_core(self.spec, data)["between_minus_within_contrast"])

    def test_empty_sample_is_not_evaluable_and_the_family_incomplete(self):
        rows = fx.make_item_rows(2)
        states = {SlotKey(item, "sonnet_5", pair_of(i)[1], 1): "parse_error"
                  for i, item in enumerate(r["item_id"] for r in rows)}
        data, _ = self.build({}, states=states, rows=rows)
        result = h2_core(self.spec, data)
        self.assertEqual(self.pick(result, "sonnet_5")["status"], "not_evaluable")
        self.assertEqual(result["holm_family"]["status"], "incomplete")
        self.assertEqual(result["holm_family"]["evaluable_tests"], 2)
        self.assertTrue(all(t["holm_adjusted_p"] is None for t in result["tests"]))

    def test_complete_family_reports_raw_and_adjusted_p(self):
        data, _ = self.build({"SYN1": ((1, 1, 1), (0, 0, 0)), "SYN2": ((0, 0, 0), (1, 1, 1))})
        result = h2_core(self.spec, data)
        self.assertEqual(result["holm_family"]["status"], "complete")
        terra = self.pick(result)
        self.assertEqual((terra["p_value"]["exact"], terra["holm_adjusted_p"]["exact"]),
                         ("1/100", "3/100"))
        self.assertTrue(terra["rejected_at_familywise_alpha"])
        other = self.pick(result, "sonnet_5")
        self.assertEqual(other["flag"], UNINFORMATIVE)
        self.assertEqual(other["holm_adjusted_p"]["exact"], "1/1")

    def test_the_planned_family_is_never_shrunk(self):
        # One model has N = 0. The property under test: all three planned tests stay in the
        # family, the family is reported incomplete, and no adjusted p-value is produced
        # (not even for the two evaluable models). Every check is an assertion on fields
        # read with .get, so a violation fails here rather than raising elsewhere.
        rows = fx.make_item_rows(2)
        states = {SlotKey(item, "sonnet_5", pair_of(i)[1], 1): "parse_error"
                  for i, item in enumerate(r["item_id"] for r in rows)}
        data, _ = self.build({"SYN1": ((1, 1, 1), (0, 0, 0))}, states=states, rows=rows)
        result = h2_core(self.spec, data)
        tests = result.get("tests", [])
        self.assertEqual(len(tests), 3, "every planned model test stays in the family")
        self.assertEqual(sorted(t.get("model_key") for t in tests),
                         sorted(("terra_5_6", "sonnet_5", "deepseek_v4_pro")))
        family = result.get("holm_family", {})
        self.assertEqual(family.get("status"), "incomplete")
        self.assertEqual(family.get("size_planned"), 3)
        self.assertEqual(family.get("evaluable_tests"), 2)
        self.assertEqual([t.get("holm_adjusted_p") for t in tests], [None, None, None],
                         "no Holm adjustment over a reduced family")
        self.assertFalse(any("rejected_at_familywise_alpha" in t for t in tests))

    def test_pending_extensions_refuse_to_run(self):
        for entry in (h2_temporal_sensitivity, h2_ancillary_bootstrap, h2_ps_anova):
            with self.assertRaises(DecisionPending):
                entry(self.spec)
        data, _ = self.build({})
        pending = {p["module"] for p in h2_core(self.spec, data)["pending"]}
        self.assertEqual(pending, {"h2_temporal_sensitivity",
                                   "h2_ancillary_bootstrap_and_temporal_holm", "h2_ps_anova"})

    def test_the_framework_bootstrap_is_not_used_for_h2_or_h3(self):
        for name in ("h2.py", "h3.py"):
            tree = ast.parse((PROJECT_ROOT / "python/src/chapter3/chapter4_v2" / name)
                             .read_text(encoding="utf-8"))
            imported = {node.module for node in ast.walk(tree)
                        if isinstance(node, ast.ImportFrom) and node.module}
            self.assertFalse(any("bootstrap" in m for m in imported), name)
