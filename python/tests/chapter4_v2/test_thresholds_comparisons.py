"""Exact threshold boundaries, three-state combination, comparators and G margins."""

from fractions import Fraction

import numpy as np

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.comparisons import (
    best_of,
    g_margins,
    standalone_leader,
    standalone_margin,
)
from src.chapter3.chapter4_v2.framework import annotation_adequacy
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b
from src.chapter3.chapter4_v2.scores import AnnotationScores, ClassTally, score_vector
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.thresholds import (
    NOT_EVALUABLE,
    NOT_SATISFIED,
    SATISFIED,
    Conclusion,
    as_exact,
    at_least,
    at_most,
    combine,
    strictly_below,
)

TINY = Fraction(1, 10**12)


def scores_with(pos_correct, n_pos, neg_correct, n_neg, pid="p"):
    return AnnotationScores(pid, "B", "synthetic",
                            ClassTally(n_pos, pos_correct, n_pos - pos_correct, 0),
                            ClassTally(n_neg, neg_correct, n_neg - neg_correct, 0))


class BoundaryTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def test_minima_are_inclusive_and_exact(self):
        for threshold in ("0.75", "0.925", "0.03"):
            self.assertTrue(at_least(Fraction(threshold), threshold))
            self.assertFalse(at_least(Fraction(threshold) - TINY, threshold))
            self.assertTrue(at_least(Fraction(threshold) + TINY, threshold))

    def test_distance_maximum_is_inclusive_and_exact(self):
        self.assertTrue(at_most(Fraction("0.41"), "0.41"))
        self.assertFalse(at_most(Fraction("0.41") + TINY, "0.41"))

    def test_floats_are_compared_at_the_exact_value_of_the_double(self):
        # The double nearest 0.41 lies just below 0.41; the next double up lies above.
        self.assertTrue(at_most(0.41, "0.41"))
        self.assertFalse(at_most(float(np.nextafter(0.41, 1.0)), "0.41"))
        self.assertEqual(as_exact(0.5), Fraction(1, 2))
        with self.assertRaises(ValueError):
            as_exact(float("nan"))

    def test_similarity_bound_is_strict(self):
        self.assertFalse(strictly_below(Fraction("0.03"), "0.03"))
        self.assertTrue(strictly_below(Fraction("0.03") - TINY, "0.03"))

    def test_adequacy_on_exact_scores_at_and_just_off_the_boundary(self):
        # 3/4 is exactly 0.75; 37/40 is exactly 0.925.
        on = annotation_adequacy(self.spec, {"p": scores_with(3, 4, 37, 40)})["p"]
        self.assertEqual(on.status, SATISFIED)
        below_plus = annotation_adequacy(self.spec, {"p": scores_with(2, 4, 37, 40)})["p"]
        below_minus = annotation_adequacy(self.spec, {"p": scores_with(3, 4, 36, 40)})["p"]
        self.assertEqual((below_plus.status, below_minus.status), (NOT_SATISFIED, NOT_SATISFIED))

    def test_planned_benchmark_minimum_correct_counts(self):
        # On 32 positives and 218 negatives the thresholds need 24 and 202 correct.
        self.assertEqual(annotation_adequacy(self.spec, {"p": scores_with(24, 32, 202, 218)})[
            "p"].status, SATISFIED)
        self.assertEqual(annotation_adequacy(self.spec, {"p": scores_with(23, 32, 202, 218)})[
            "p"].status, NOT_SATISFIED)
        self.assertEqual(annotation_adequacy(self.spec, {"p": scores_with(24, 32, 201, 218)})[
            "p"].status, NOT_SATISFIED)

    def test_absent_class_is_not_evaluable(self):
        s = AnnotationScores("p", "B", "synthetic", ClassTally(0, 0, 0, 0), ClassTally(4, 4, 0, 0))
        result = annotation_adequacy(self.spec, {"p": s})["p"]
        self.assertEqual(result.status, NOT_EVALUABLE)


class CombineTests(SyntheticTestCase):
    def part(self, name, status):
        return Conclusion(name, None, "r", "B", status, None if status == SATISFIED else "x")

    def test_known_failure_wins_over_unavailable(self):
        result = combine("c", [self.part("a", NOT_SATISFIED), self.part("b", NOT_EVALUABLE)], "r", "B")
        self.assertEqual(result.status, NOT_SATISFIED)
        self.assertIn("also not evaluable: b", result.reason)

    def test_unavailable_without_failure_is_not_evaluable(self):
        result = combine("c", [self.part("a", SATISFIED), self.part("b", NOT_EVALUABLE)], "r", "B")
        self.assertEqual(result.status, NOT_EVALUABLE)

    def test_all_known_and_met_is_satisfied(self):
        result = combine("c", [self.part("a", SATISFIED), self.part("b", SATISFIED)], "r", "B")
        self.assertEqual((result.status, result.reason), (SATISFIED, None))

    def test_a_non_satisfied_conclusion_needs_a_reason(self):
        with self.assertRaises(ValueError):
            Conclusion("c", None, "r", "B", NOT_SATISFIED, None)
        with self.assertRaises(ValueError):
            Conclusion("c", None, "r", "B", "passed")


class ComparatorTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def b_scores(self, label_of, n_items=12):
        data = fx.build_input(self.spec, n_items=n_items, label_of=label_of)
        vectors = build_vectors(data, self.registry)
        members = sample_b(data).members
        return {p.procedure_id: score_vector(vectors[p.procedure_id], data, members, "B")
                for p in self.registry.primary}

    def test_ties_are_named_by_the_smallest_id_and_leave_the_margin_unchanged(self):
        scores = {"cb::b": scores_with(3, 4, 4, 4, "cb::b"), "va_s::a": scores_with(3, 4, 4, 4),
                  "cb::c": scores_with(3, 4, 4, 4, "cb::c"), "cb::d": scores_with(1, 4, 4, 4)}
        best = best_of(scores, ["va_s::a", "cb::c", "cb::b", "cb::d"])
        self.assertEqual(best.procedure_id, "cb::b")
        self.assertEqual(best.tied_ids, ("cb::b", "cb::c", "va_s::a"))
        self.assertEqual(best.ba, Fraction(7, 8))

    def test_the_search_includes_inadequate_configurations(self):
        # Every configuration predicts 0: A+ = 0, so none is adequate; G is not either.
        scores = self.b_scores(lambda k: 0)
        margins = g_margins(self.spec, self.registry, scores)
        self.assertEqual(margins["g_minus_best_cb"].comparator, "cb::deepseek_v4_pro::cb_t3_cot")
        self.assertEqual(margins["g_minus_best_cb"].value, 0)
        adequacy = annotation_adequacy(self.spec, scores)
        self.assertTrue(all(c.status == NOT_SATISFIED for c in adequacy.values()))

    def test_third_margin_is_the_minimum_of_the_other_two_at_the_point(self):
        def label_of(k):
            truth = int(k.item_id[3:]) % 2
            if k.template_id == "cb_t3_zero_shot" and k.item_id == "SYN01":
                return 1 - truth
            return truth if k.template_id.startswith("cb_") else 0
        margins = g_margins(self.spec, self.registry, self.b_scores(label_of))
        first, second, third = (margins[n].value for n in
                                ("g_minus_best_cb", "g_minus_best_va_post_s", "g_minus_best_all_30"))
        self.assertEqual(third, min(first, second))
        self.assertTrue(margins["g_minus_best_all_30"].comparator.startswith("cb::"))

    def test_standalone_margin_compares_with_every_other_primary_procedure_including_g(self):
        # Only one CB configuration is fully correct; G and everything else predict 0.
        def label_of(k):
            truth = int(k.item_id[3:]) % 2
            return truth if (k.template_id, k.model_key) == ("cb_t3_tot", "sonnet_5") else 0
        scores = self.b_scores(label_of)
        leader = standalone_leader(self.registry, scores)
        self.assertEqual(leader.procedure_id, "cb::sonnet_5::cb_t3_tot")
        margin = standalone_margin(leader.procedure_id, self.spec, self.registry, scores)
        self.assertEqual(margin.value, Fraction(1, 2))
        self.assertEqual(margin.status, SATISFIED)
        self.assertNotEqual(margin.comparator, leader.procedure_id)
