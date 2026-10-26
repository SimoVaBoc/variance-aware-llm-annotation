"""Samples and scores: validity-only membership, overlapping reasons, zero credit for missing."""

from fractions import Fraction

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.inputs import InputIntegrityError, SlotKey
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import (
    h1_supports,
    h2_supports,
    sample_b,
    sample_i27,
    sample_r,
)
from src.chapter3.chapter4_v2.scores import score_vector
from src.chapter3.chapter4_v2.spec import load_spec

G = "va_g::s_p_m"
VA_PROMPTS = ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")


class Base(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def samples(self, data):
        vectors = build_vectors(data, self.registry)
        b = sample_b(data)
        return vectors, b, sample_i27(data, b), sample_r(data, b, self.registry, vectors)


class SampleTests(Base):
    def test_b_holds_items_with_a_binary_human_class_and_counts_both_classes(self):
        rows = fx.make_item_rows(4)
        rows[2]["HUMAN"] = "unclear"
        data = fx.build_input(self.spec, item_rows=rows)
        b = sample_b(data)
        self.assertEqual(b.members, ("SYN1", "SYN2", "SYN4"))
        self.assertEqual(dict(b.class_counts), {"positive": 1, "negative": 2})
        self.assertEqual(b.exclusions, {"SYN3": ("human_not_binary",)})
        self.assertEqual(b.as_record(data)["data_kind"], "synthetic")

    def test_i27_reasons_are_recorded_by_state_and_may_overlap(self):
        states = {SlotKey("SYN1", "sonnet_5", "cm_base", 1): "parse_error",
                  SlotKey("SYN1", "terra_5_6", "cm_paraphrase_2", 3): "api_error_only",
                  SlotKey("SYN2", "deepseek_v4_pro", "cm_base", 2): "absent"}
        data = fx.build_input(self.spec, states=states)
        _, _, i27, _ = self.samples(data)
        self.assertEqual(i27.members, ("SYN3", "SYN4"))
        self.assertEqual(i27.exclusions["SYN1"],
                         ("va_technical_failure", "va_terminal_invalid"))
        self.assertEqual(i27.exclusions["SYN2"], ("va_planned_unobserved",))
        counts = i27.reason_counts(data)
        self.assertEqual(sum(c["total"] for c in counts.values()), 3)
        self.assertEqual(len(i27.exclusions), 2, "two items, three reasons")
        self.assertTrue(i27.as_record(data)["exclusion_reason_counts_overlap"])

    def test_r_requires_covariates_and_all_31_primary_labels(self):
        rows = fx.make_item_rows(4)
        rows[3]["lgoal"] = "nan"
        states = {SlotKey("SYN1", "terra_5_6", "cb_t3_cot", 1): "parse_error",
                  SlotKey("SYN2", "sonnet_5", "cm_paraphrase_1", 2): "parse_error"}
        data = fx.build_input(self.spec, item_rows=rows, states=states)
        _, _, i27, r = self.samples(data)
        self.assertEqual(r.members, ("SYN3",))
        self.assertEqual(r.exclusions["SYN1"], ("primary_label_missing:cb",))
        self.assertIn("SYN1", i27.members, "a missing CB label does not touch I27")
        self.assertEqual(r.exclusions["SYN2"],
                         ("primary_label_missing:g", "primary_label_missing:va_post_s"))
        self.assertEqual(r.exclusions["SYN4"], ("lgoal_not_finite",))

    def test_membership_never_depends_on_correctness(self):
        states = {SlotKey("SYN2", "sonnet_5", "cm_base", 1): "parse_error"}
        right = fx.build_input(self.spec, states=states,
                               label_of=lambda k: int(k.item_id[-1]) % 2)
        wrong = fx.build_input(self.spec, states=states,
                               label_of=lambda k: 1 - int(k.item_id[-1]) % 2)
        for a, b in zip(self.samples(right)[1:], self.samples(wrong)[1:]):
            self.assertEqual(a.members, b.members)
            self.assertEqual(a.exclusions, b.exclusions)

    def test_an_empty_i27_and_r_are_explicit(self):
        states = {SlotKey(f"SYN{i}", "terra_5_6", "cm_base", 1): "parse_error" for i in range(1, 5)}
        data = fx.build_input(self.spec, states=states)
        vectors, b, i27, r = self.samples(data)
        self.assertEqual((i27.members, r.members), ((), ()))
        self.assertEqual(i27.as_record(data)["class_counts"], {"positive": 0, "negative": 0})
        g = score_vector(vectors[G], data, b.members, "B")
        self.assertEqual((g.a_plus, g.a_minus), (Fraction(0), Fraction(0)))
        self.assertEqual((g.positive.missing, g.negative.missing), (2, 2))


class SupportTests(Base):
    def test_h1_separates_complete_and_partial_triplets(self):
        states = {SlotKey("SYN1", "sonnet_5", "cm_base", 1): "parse_error",
                  SlotKey("SYN1", "sonnet_5", "cm_base", 2): "absent",
                  SlotKey("SYN3", "sonnet_5", "cm_base", 3): "api_error_only"}
        data = fx.build_input(self.spec, states=states)
        cell = next(s for s in h1_supports(data)
                    if (s.model_key, s.template_id) == ("sonnet_5", "cm_base"))
        self.assertEqual(cell.complete, ("SYN2", "SYN4"))
        self.assertEqual(dict(cell.partial), {"SYN1": 1, "SYN3": 2})
        self.assertEqual(len(h1_supports(data)), 9)

    def pair_of(self, data, model, item):
        return next(s for s in h2_supports(data) if s.model_key == model).selections[item]

    def test_h2_pair_comes_from_the_planned_orders(self):
        data = fx.build_input(self.spec)
        for index, item in enumerate(data.design.item_ids):
            orders = fx.label_orders_for(index, self.spec.va_template_ids)
            selection = self.pair_of(data, "terra_5_6", item)
            self.assertEqual(len({orders[t] for t in selection.pair}), 1)
            self.assertNotEqual(orders[selection.third], selection.shared_order)

    def test_h2_third_prompt_invalidity_does_not_exclude(self):
        data = fx.build_input(self.spec)
        third = self.pair_of(data, "sonnet_5", "SYN1").third
        data = fx.build_input(self.spec, states={SlotKey("SYN1", "sonnet_5", third, 1):
                                                 "parse_error"})
        support = next(s for s in h2_supports(data) if s.model_key == "sonnet_5")
        self.assertIn("SYN1", support.members)
        self.assertFalse(support.selections["SYN1"].third_all_valid)

    def test_h2_incomplete_pair_excludes_and_is_never_replaced(self):
        data = fx.build_input(self.spec)
        selection = self.pair_of(data, "sonnet_5", "SYN2")
        bad = SlotKey("SYN2", "sonnet_5", selection.pair[0], 3)
        data = fx.build_input(self.spec, states={bad: "parse_error"})
        support = next(s for s in h2_supports(data) if s.model_key == "sonnet_5")
        self.assertNotIn("SYN2", support.members)
        self.assertEqual(support.selections["SYN2"].pair, selection.pair)
        other = next(s for s in h2_supports(data) if s.model_key == "terra_5_6")
        self.assertIn("SYN2", other.members, "I_m is model-specific")

    def test_h2_pattern_other_than_two_plus_one_is_an_integrity_error(self):
        def same_order(manifests):
            for row in manifests["deepseek_v4_pro"]:
                if row["item_id"] == "SYN1" and row["arm"] == "camuffo":
                    row["label_order"] = "10"
        data = fx.build_input(self.spec, mutate_manifests=same_order)
        with self.assertRaises(InputIntegrityError) as caught:
            h2_supports(data)
        self.assertIn("two-plus-one", caught.exception.problems[0])


class ScoreTests(Base):
    def test_missing_lowers_the_score_without_becoming_a_false_negative(self):
        # SYN1 and SYN3 are positives. Missing on SYN1 versus wrong on SYN1.
        missing = fx.build_input(self.spec, label_of=lambda k: int(k.item_id[-1]) % 2,
                                 states={SlotKey("SYN1", "terra_5_6", "cb_t3_cot", 1):
                                         "parse_error"})
        wrong = fx.build_input(self.spec, label_of=lambda k: 0 if k.item_id == "SYN1"
                               else int(k.item_id[-1]) % 2)
        pid = "cb::terra_5_6::cb_t3_cot"
        s_missing = score_vector(build_vectors(missing, self.registry)[pid], missing,
                                 sample_b(missing).members, "B")
        s_wrong = score_vector(build_vectors(wrong, self.registry)[pid], wrong,
                               sample_b(wrong).members, "B")
        self.assertEqual(s_missing.a_plus, s_wrong.a_plus)
        self.assertEqual(s_missing.a_plus, Fraction(1, 2))
        self.assertEqual((s_missing.positive.missing, s_missing.positive.valid_incorrect), (1, 0))
        self.assertEqual((s_wrong.positive.missing, s_wrong.positive.valid_incorrect), (0, 1))
        self.assertEqual(s_missing.coverage, Fraction(3, 4))
        self.assertEqual(s_wrong.coverage, 1)
        self.assertEqual(s_missing.ba, Fraction(3, 4))

    def test_tallies_add_up_to_the_class_sizes(self):
        states = {SlotKey("SYN2", "sonnet_5", "cb_t3_tot", 1): "absent"}
        data = fx.build_input(self.spec, n_items=6, states=states,
                              label_of=lambda k: int(int(k.item_id[-1]) % 3 == 0))
        b = sample_b(data)
        for vector in build_vectors(data, self.registry).values():
            s = score_vector(vector, data, b.members, "B")
            self.assertEqual(s.positive.n + s.negative.n, len(b.members))
            self.assertEqual(s.positive.n, b.class_counts["positive"])

    def test_g_outside_i27_earns_zero_credit_on_b_and_stays_missing(self):
        data = fx.build_input(self.spec, label_of=lambda k: int(k.item_id[-1]) % 2,
                              states={SlotKey("SYN3", "terra_5_6", "cm_base", 2): "parse_error"})
        vectors = build_vectors(data, self.registry)
        self.assertIsNone(vectors[G].label("SYN3"))
        g = score_vector(vectors[G], data, sample_b(data).members, "B")
        self.assertEqual((g.positive.valid_correct, g.positive.missing), (1, 1))
        self.assertEqual(g.a_plus, Fraction(1, 2))
        self.assertEqual(g.a_minus, 1)

    def test_one_class_sample_is_not_evaluable_never_zero(self):
        rows = fx.make_item_rows(4)
        for row in rows:
            row["HUMAN"] = "0"
        data = fx.build_input(self.spec, item_rows=rows)
        s = score_vector(build_vectors(data, self.registry)[G], data, sample_b(data).members, "B")
        self.assertIsNone(s.a_plus)
        self.assertIsNone(s.ba)
        self.assertEqual(s.a_minus, 1)
        self.assertEqual(s.not_evaluable_reason, "class_absent_from_sample:positive")

    def test_scores_use_the_sample_s_own_class_denominators(self):
        data = fx.build_input(self.spec, label_of=lambda k: 1,
                              states={SlotKey("SYN2", "terra_5_6", "cm_base", 1): "parse_error"})
        vectors, b, i27, _ = self.samples(data)
        on_i27 = score_vector(vectors[G], data, i27.members, "I27")
        self.assertEqual((on_i27.positive.n, on_i27.negative.n), (2, 1))
        self.assertEqual(on_i27.as_record()["sample"], "I27")
        self.assertEqual(on_i27.as_record()["a_plus"], {"exact": "1/1", "value": 1.0})
