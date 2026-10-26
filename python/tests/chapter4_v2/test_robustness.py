"""Robustness: possibility-set propagation, fixed I27, tie credit only here, leave-one-out."""

from fractions import Fraction

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.robustness import (
    TIE,
    UNDETERMINED,
    Omission,
    credit,
    g_omission_checks,
    leave_one_out,
    majority_of_possibilities,
    omissions,
    reduced_outcome,
    two_votes,
)
from src.chapter3.chapter4_v2.samples import sample_b, sample_i27
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.thresholds import NOT_SATISFIED, SATISFIED

# Post-S labels of SYN01 (a positive) per model and prompt; every S call agrees.
SYN01 = {
    ("terra_5_6", "cm_base"): 1, ("terra_5_6", "cm_paraphrase_1"): 0,
    ("terra_5_6", "cm_paraphrase_2"): 1,
    ("sonnet_5", "cm_base"): 1, ("sonnet_5", "cm_paraphrase_1"): 1,
    ("sonnet_5", "cm_paraphrase_2"): 0,
    ("deepseek_v4_pro", "cm_base"): 0, ("deepseek_v4_pro", "cm_paraphrase_1"): 0,
    ("deepseek_v4_pro", "cm_paraphrase_2"): 1,
}


def truth(key):
    return int(key.item_id[3:]) % 2


class PossibilityTests(SyntheticTestCase):
    def test_two_votes(self):
        self.assertEqual(two_votes(1, 1), frozenset({1}))
        self.assertEqual(two_votes(0, 1), UNDETERMINED)

    def test_possibilities_propagate_through_the_model_majority(self):
        one, zero = frozenset({1}), frozenset({0})
        self.assertEqual(majority_of_possibilities([one, UNDETERMINED, one]), 1)
        self.assertEqual(majority_of_possibilities([one, UNDETERMINED, zero]), TIE)
        self.assertEqual(majority_of_possibilities([UNDETERMINED, UNDETERMINED, one]), TIE)
        self.assertEqual(majority_of_possibilities([zero, zero, UNDETERMINED]), 0)

    def test_credit_values(self):
        self.assertEqual((credit(1, 1), credit(0, 1), credit(TIE, 0)),
                         (1, 0, Fraction(1, 2)))


class OmissionTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

        def label_of(key):
            if key.item_id == "SYN01" and key.template_id.startswith("cm_"):
                return SYN01[(key.model_key, key.template_id)]
            return truth(key)

        # SYN03 (a positive) is outside I27: one call of its base prompt is invalid.
        cls.data = fx.build_input(cls.spec, n_items=12, label_of=label_of,
                                  states={SlotKey("SYN03", "sonnet_5", "cm_base", 2): "parse_error"})
        cls.vectors = build_vectors(cls.data, cls.registry)
        cls.b = sample_b(cls.data)
        cls.i27 = sample_i27(cls.data, cls.b)

    def outcome(self, kind, omitted):
        return reduced_outcome(Omission(kind, omitted), "SYN01", self.spec, self.vectors)

    def test_six_perturbations_with_eighteen_calls_each(self):
        self.assertEqual(len(omissions(self.spec)), 6)
        self.assertEqual(self.spec.data["robustness"]["g_omissions"]["calls_per_reduced_panel"], 18)

    def test_prompt_omissions_propagate_disagreement_to_a_final_tie(self):
        for prompt in ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2"):
            self.assertEqual(self.outcome("prompt", prompt), TIE, prompt)

    def test_model_omissions_tie_on_discordant_models_only(self):
        self.assertEqual(self.outcome("model", "terra_5_6"), TIE)
        self.assertEqual(self.outcome("model", "sonnet_5"), TIE)
        self.assertEqual(self.outcome("model", "deepseek_v4_pro"), 1)

    def test_i27_stays_fixed_and_ties_earn_half_credit_only_in_the_score(self):
        self.assertNotIn("SYN03", self.i27.members)
        result = g_omission_checks(self.spec, self.data, self.vectors, self.b.members,
                                   self.i27.members, "fixed_comparator", Fraction(1, 2))
        by_name = {r["omission"]: r for r in result["perturbations"]}
        base = by_name["omit_prompt::cm_base"]
        # Positives: SYN01 tie (1/2), SYN03 not recovered (0), four others correct: 9/2 of 6.
        # Negatives all correct. BA = (3/4 + 1) / 2 = 7/8; margin over 1/2 is 3/8.
        self.assertEqual(base["margin"]["exact"], "3/8")
        self.assertEqual(base["final_ties"], 1)
        deepseek = by_name["omit_model::deepseek_v4_pro"]
        self.assertEqual(deepseek["final_ties"], 0)
        for vector in self.vectors.values():
            self.assertTrue(set(vector.labels.values()) <= {0, 1, None})

    def test_all_six_must_pass_and_the_minimum_is_reported(self):
        result = g_omission_checks(self.spec, self.data, self.vectors, self.b.members,
                                   self.i27.members, "fixed_comparator", Fraction(1, 2))
        self.assertEqual(result["n_perturbations"], 6)
        self.assertEqual(result["conclusion"].status, SATISFIED)
        # The lowest reduced BA is 7/8; against a comparator at 17/20 that leaves 1/40.
        self.assertEqual(result["minimum_margin"]["exact"], "3/8")
        strict = g_omission_checks(self.spec, self.data, self.vectors, self.b.members,
                                   self.i27.members, "fixed_comparator", Fraction(17, 20))
        self.assertEqual(strict["minimum_margin"]["exact"], "1/40")
        self.assertEqual(strict["conclusion"].status, NOT_SATISFIED)
        self.assertEqual(strict["n_satisfied"], 1, "only the DeepSeek omission (BA 11/12) passes")


class LeaveOneOutTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

        # Candidate: Terra zero-shot, always right. Sonnet zero-shot is wrong only on
        # SYN01 (positive), DeepSeek zero-shot only on SYN02 (negative). Everything
        # else predicts 0.
        def label_of(key):
            if key.template_id != "cb_t3_zero_shot":
                return 0
            if key.model_key == "sonnet_5" and key.item_id == "SYN01":
                return 0
            if key.model_key == "deepseek_v4_pro" and key.item_id == "SYN02":
                return 1
            return truth(key)

        cls.data = fx.build_input(cls.spec, n_items=12, label_of=label_of)
        cls.vectors = build_vectors(cls.data, cls.registry)
        cls.members = sample_b(cls.data).members
        cls.candidate = "cb::terra_5_6::cb_t3_zero_shot"
        cls.result = leave_one_out(cls.candidate, cls.spec, cls.registry, cls.data,
                                   cls.vectors, cls.members)

    def by_omitted(self, item):
        return next(r for r in self.result["perturbations"] if r["omitted"] == item)

    def test_one_check_per_campaign_with_the_candidate_fixed(self):
        self.assertEqual(self.result["n_perturbations"], 12)
        self.assertEqual(self.result["candidate"], self.candidate)
        self.assertTrue(all(r["comparator"] != self.candidate
                            for r in self.result["perturbations"]))

    def test_the_strongest_alternative_and_denominators_are_recomputed(self):
        # Omitting SYN01 makes Sonnet perfect: margin 0.
        self.assertEqual(self.by_omitted("SYN01")["margin"]["exact"], "0/1")
        self.assertEqual(self.by_omitted("SYN01")["comparator"], "cb::sonnet_5::cb_t3_zero_shot")
        # Omitting SYN03 (positive): Sonnet A+ = 4/5 -> BA 9/10; DeepSeek A- = 5/6 -> 11/12.
        self.assertEqual(self.by_omitted("SYN03")["comparator"], "cb::deepseek_v4_pro::cb_t3_zero_shot")
        self.assertEqual(self.by_omitted("SYN03")["margin"]["exact"], "1/12")

    def test_status_requires_every_omission_and_reports_the_minimum(self):
        self.assertEqual(self.result["conclusion"].status, NOT_SATISFIED)
        self.assertEqual(self.result["minimum_margin"]["exact"], "0/1")

    def test_the_omitted_class_loses_one_from_its_denominator(self):
        # Only Sonnet zero-shot competes, wrong on SYN01 (a positive). Omitting SYN03,
        # another positive, leaves five positives: margin 1/2 * 1/5, not 1/2 * 1/6.
        def label_of(key):
            if key.template_id != "cb_t3_zero_shot" or key.model_key == "deepseek_v4_pro":
                return 0
            if key.model_key == "sonnet_5" and key.item_id == "SYN01":
                return 0
            return truth(key)

        data = fx.build_input(self.spec, n_items=12, label_of=label_of)
        vectors = build_vectors(data, self.registry)
        result = leave_one_out(self.candidate, self.spec, self.registry, data, vectors,
                               sample_b(data).members)
        omit = next(r for r in result["perturbations"] if r["omitted"] == "SYN03")
        self.assertEqual((omit["comparator"], omit["margin"]["exact"]),
                         ("cb::sonnet_5::cb_t3_zero_shot", "1/10"))
