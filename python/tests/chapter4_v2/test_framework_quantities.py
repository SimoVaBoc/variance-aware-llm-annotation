"""Framework quantities and the status table: missing as non-correspondence, J/E/U, A1-A6."""

from fractions import Fraction

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import LabelVector, build_vectors
from src.chapter3.chapter4_v2.annotation_framework import evaluate_annotation_framework
from src.chapter3.chapter4_v2.framework import (
    directional_corrections,
    error_groups,
    kappa_exact,
    noncorrespondence,
    overall_adequacy,
    pair_table,
    practical_similarity,
    shared_errors,
    sufficiency_threshold,
)
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import planned_benchmark_check, sample_b
from src.chapter3.chapter4_v2.scores import missing_by_procedure
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.thresholds import (
    NOT_EVALUABLE,
    NOT_SATISFIED,
    SATISFIED,
    Conclusion,
)

PROMPTS = ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")
MODELS = ("terra_5_6", "sonnet_5", "deepseek_v4_pro")


def truth(key_or_item):
    item = getattr(key_or_item, "item_id", key_or_item)
    return int(item[3:]) % 2


def vec(name, labels):
    return LabelVector(name, "cb", labels, {i: "slot_planned_unobserved"
                                            for i, v in labels.items() if v is None})


def status(name, value):
    return Conclusion(name, None, "r", "B", value, None if value == SATISFIED else "x")


class PairTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)
        cls.data = fx.build_input(cls.spec, n_items=4)  # SYN1, SYN3 positive

    def test_two_missing_labels_are_non_correspondence_and_split_by_cause(self):
        a = vec("a", {"SYN1": None, "SYN2": 0, "SYN3": 1, "SYN4": 1})
        b = vec("b", {"SYN1": None, "SYN2": 0, "SYN3": 0, "SYN4": 1})
        nc = noncorrespondence(a, b, self.data, ["SYN1", "SYN2", "SYN3", "SYN4"])
        self.assertEqual(nc["by_class"]["positive"]["total"], 1)
        self.assertEqual(nc["by_class"]["positive"]["missingness"], Fraction(1, 2))
        self.assertEqual(nc["by_class"]["positive"]["valid_disagreement"], Fraction(1, 2))
        self.assertEqual(nc["by_class"]["negative"]["total"], 0)
        self.assertEqual(nc["balanced"]["total"], Fraction(1, 2))

    def test_undefined_kappa_is_none_never_one(self):
        constant = vec("c", {"SYN1": 1, "SYN2": 1, "SYN3": 1, "SYN4": 1})
        kappa, support = kappa_exact(constant, constant, self.data, ["SYN1", "SYN2", "SYN3", "SYN4"])
        self.assertIsNone(kappa)
        self.assertEqual(support, 4)
        empty = vec("e", {"SYN1": None, "SYN2": None, "SYN3": None, "SYN4": None})
        self.assertEqual(kappa_exact(empty, None, self.data, ["SYN1", "SYN2"]), (None, 0))

    def test_465_fixed_pairs_and_fixed_groups(self):
        vectors = build_vectors(self.data, self.registry)
        pairs = pair_table(self.registry, vectors, self.data, sample_b(self.data).members)
        self.assertEqual(len(pairs), 465)
        self.assertEqual(len({frozenset(p["pair"]) for p in pairs}), 465)
        self.assertEqual([p["pair"] for p in pairs], sorted(p["pair"] for p in pairs))
        groups = error_groups(self.registry)
        self.assertEqual({k: len(v) for k, v in groups.items()},
                         {"S_CB": 21, "S_VA": 9, "S_ALL": 30})
        self.assertNotIn(self.registry.g.procedure_id, groups["S_ALL"])


class SharedErrorTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def test_sufficiency_thresholds_follow_from_adequacy(self):
        self.assertEqual(sufficiency_threshold(32, "0.75"), 9)
        self.assertEqual(sufficiency_threshold(218, "0.925"), 17)
        self.assertEqual(sufficiency_threshold(3, "0.75"), 1)

    def test_j_e_u_definitions(self):
        # Six items; positives SYN1, SYN3, SYN5. Every CB label is wrong on SYN1 and SYN3,
        # but one CB call on SYN3 is missing: SYN1 is a shared error (E), SYN3 only a
        # shared failure (U). SYN5 is right everywhere.
        def label_of(k):
            if k.template_id.startswith("cb_") and k.item_id in ("SYN1", "SYN3"):
                return 0
            return truth(k)

        data = fx.build_input(self.spec, n_items=6, label_of=label_of,
                              states={SlotKey("SYN3", "sonnet_5", "cb_t3_rot", 1): "parse_error"})
        vectors = build_vectors(data, self.registry)
        shared = shared_errors(self.spec, self.registry, vectors, data, sample_b(data).members)
        pos = shared["S_CB"]["by_class"]["positive"]
        self.assertEqual((pos["N"], pos["J"], pos["E"], pos["U"], pos["U_minus_E"]), (3, 2, 1, 2, 1))
        self.assertEqual(pos["E_over_J"]["exact"], "1/2")
        self.assertEqual(pos["sufficiency_threshold"], 1)
        self.assertTrue(pos["E_sufficient_for_group_inadequacy"])
        va = shared["S_VA"]["by_class"]["positive"]
        self.assertEqual((va["E"], va["U"]), (0, 0))
        self.assertIn("G is also wrong", shared["S_VA"]["note"])
        self.assertIn("No implication for G", shared["S_CB"]["note"])


class CorrectionTests(SyntheticTestCase):
    def test_directional_corrections_on_the_ba_scale(self):
        spec = load_spec()
        registry = build_registry(spec)

        def label_of(k):
            if (k.model_key, k.template_id, k.item_id) == ("terra_5_6", "cm_paraphrase_1", "SYN1"):
                return 0
            return truth(k)

        data = fx.build_input(spec, n_items=6, label_of=label_of)
        result = directional_corrections(spec, registry, build_vectors(data, registry), data,
                                         sample_b(data).members)
        self.assertEqual(result["n_pairs"], 36)
        pair = next(p for p in result["pairs"]
                    if p["pair"] == ("va_s::terra_5_6::cm_base", "va_s::terra_5_6::cm_paraphrase_1"))
        forward = pair["va_s::terra_5_6::cm_base->va_s::terra_5_6::cm_paraphrase_1"]
        backward = pair["va_s::terra_5_6::cm_paraphrase_1->va_s::terra_5_6::cm_base"]
        self.assertEqual((forward["n_positive"], forward["C"]), (1, Fraction(1, 6)))
        self.assertEqual(backward["C"], 0)
        self.assertEqual((pair["observed_correction"], pair["reciprocal"]), (True, False))


class SimilarityTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def pairs(self, values):
        return [{"pair": tuple(sorted(k)), "noncorrespondence": {"balanced": {"total": v}}}
                for k, v in values.items()]

    def test_fewer_than_two_adequate_is_not_satisfied(self):
        result = practical_similarity(self.spec, {"a": status("a", SATISFIED),
                                                  "b": status("b", NOT_SATISFIED)},
                                      {"a": status("a", SATISFIED), "b": status("b", SATISFIED)}, [])
        self.assertEqual(result.status, NOT_SATISFIED)

    def test_the_whole_group_counts_no_favourable_subgroup(self):
        adequacy = {k: status(k, SATISFIED) for k in "abc"}
        proximity = {k: status(k, SATISFIED) for k in "abc"}
        pairs = self.pairs({("a", "b"): Fraction(0), ("a", "c"): Fraction(1, 10),
                            ("b", "c"): Fraction(0)})
        result = practical_similarity(self.spec, adequacy, proximity, pairs,
                                      distance=lambda x, y: 0.0)
        self.assertEqual(result.status, NOT_SATISFIED, "a and b alone would pass; the group does not")

    def test_known_failure_beats_unknown_membership_and_unknown_stays_unknown(self):
        adequacy = {k: status(k, SATISFIED) for k in "abc"}
        proximity = {"a": status("a", SATISFIED), "b": status("b", SATISFIED),
                     "c": status("c", NOT_EVALUABLE)}
        failing = self.pairs({("a", "b"): Fraction("0.03"), ("a", "c"): Fraction(0),
                              ("b", "c"): Fraction(0)})
        self.assertEqual(practical_similarity(self.spec, adequacy, proximity, failing,
                                              distance=lambda x, y: 0.0).status, NOT_SATISFIED)
        passing = self.pairs({("a", "b"): Fraction(0), ("a", "c"): Fraction(0),
                              ("b", "c"): Fraction(0)})
        self.assertEqual(practical_similarity(self.spec, adequacy, proximity, passing,
                                              distance=lambda x, y: 0.0).status, NOT_EVALUABLE)

    def test_missing_coefficient_distances_leave_similarity_not_evaluable(self):
        adequacy = {k: status(k, SATISFIED) for k in "ab"}
        proximity = {k: status(k, SATISFIED) for k in "ab"}
        pairs = self.pairs({("a", "b"): Fraction(0)})
        self.assertEqual(practical_similarity(self.spec, adequacy, proximity, pairs).status,
                         NOT_EVALUABLE)
        self.assertEqual(practical_similarity(self.spec, adequacy, proximity, pairs,
                                              distance=lambda x, y: 0.41).status, SATISFIED)


class OverallTests(SyntheticTestCase):
    def test_none_adequate_only_when_every_procedure_is_a_known_failure(self):
        adequacy = {"a": status("a", NOT_SATISFIED), "b": status("b", SATISFIED)}
        pending = {"a": status("a", NOT_EVALUABLE), "b": status("b", NOT_EVALUABLE)}
        self.assertEqual(overall_adequacy(adequacy, pending)["summary"], "unresolved")
        failing = {"a": status("a", NOT_SATISFIED), "b": status("b", NOT_SATISFIED)}
        self.assertEqual(overall_adequacy(adequacy, failing)["summary"], "none_adequate")
        mixed = {"a": status("a", NOT_EVALUABLE), "b": status("b", SATISFIED)}
        self.assertEqual(overall_adequacy(adequacy, mixed)["summary"], "at_least_one_adequate")


class EvidenceTableTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        # Twelve items. Each of the nine VA cells is wrong on its own item (SYN01..SYN09),
        # so G corrects every one; CB always predicts 0.
        cells = [(m, t) for m in MODELS for t in PROMPTS]

        def label_of(k):
            if k.template_id.startswith("cb_"):
                return 0
            index = cells.index((k.model_key, k.template_id))
            return 1 - truth(k) if k.item_id == f"SYN{index + 1:02d}" else truth(k)

        cls.data = fx.build_input(cls.spec, n_items=12, label_of=label_of)

    def evaluate(self, **kwargs):
        return evaluate_annotation_framework(self.spec, self.data, run_bootstrap=False, **kwargs)

    def test_g_passes_annotation_criteria_but_waits_for_downstream(self):
        result = self.evaluate()
        g = "va_g::s_p_m"
        self.assertEqual(result["adequacy"][g].status, SATISFIED)
        self.assertEqual(result["g_margins"]["g_minus_best_all_30"].value, Fraction(1, 12))
        self.assertEqual(result["g_omissions"]["conclusion"].status, SATISFIED)
        table = result["evidence_table"]
        self.assertEqual(table["A4_adequate_advantageous_aggregate"].status, NOT_EVALUABLE)
        self.assertEqual(table["A1_adequate_stable_leader"].status, NOT_SATISFIED,
                         "a known failure (margin) decides even with downstream pending")
        self.assertEqual(table["A3_compensating_errors"].status, SATISFIED)
        # CB always predicts 0: every positive is a shared CB error, which is sufficient
        # for group-wide inadequacy, so A6 holds through its shared-failure branch. S_ALL
        # also contains the VA configurations, which are right on almost every positive.
        a6 = table["A6_shared_errors_or_none_adequate"]
        self.assertEqual(a6.status, SATISFIED)
        self.assertEqual(a6.value["groups_with_sufficient_shared_failure"], ["S_CB"])
        for row in ("B1_human_validation", "B2_downstream_sensitivity", "B3_resources",
                    "B4_inferential_stakes"):
            self.assertEqual(table[row].status, NOT_EVALUABLE)

    def test_supplied_proximity_completes_the_aggregate_row(self):
        registry = build_registry(self.spec)
        proximity = {p.procedure_id: status(p.procedure_id, SATISFIED) for p in registry.primary}
        table = self.evaluate(proximity=proximity)["evidence_table"]
        self.assertEqual(table["A4_adequate_advantageous_aggregate"].status, SATISFIED)
        self.assertEqual(table["A5_unresolved_differences"].status, NOT_SATISFIED,
                         "a preference is established")
        self.assertEqual(table["A6_shared_errors_or_none_adequate"].status, SATISFIED,
                         "the CB shared failure does not depend on proximity")

    def test_compensating_errors_never_enter_overall_adequacy(self):
        import inspect
        self.assertEqual(list(inspect.signature(overall_adequacy).parameters),
                         ["adequacy", "proximity"])
        result = self.evaluate()
        self.assertEqual(result["evidence_table"]["A3_compensating_errors"].status, SATISFIED)
        for pid, conclusion in result["overall_adequacy"]["per_procedure"].items():
            self.assertEqual(set(conclusion.value),
                             {f"annotation_adequacy::{pid}", f"human_proximity::{pid}"})

    def test_firth_evidence_enters_through_a_downstream_result(self):
        from src.chapter3.chapter4_v2.firth import FAILED, USABLE, DownstreamResult, FitAssessment
        registry = build_registry(self.spec)

        def downstream(human_status):
            fits = {"HUMAN": FitAssessment("HUMAN", human_status, coefficient=1.0, ci=(0.0, 2.0))}
            for p in registry.primary:
                fits[p.procedure_id] = FitAssessment(p.procedure_id, USABLE, coefficient=1.1,
                                                     ci=(0.1, 2.1))
            return DownstreamResult(None, fits, {})

        table = self.evaluate(downstream=downstream(USABLE))["evidence_table"]
        self.assertEqual(table["A4_adequate_advantageous_aggregate"].status, SATISFIED)
        table = self.evaluate(downstream=downstream(FAILED))["evidence_table"]
        self.assertEqual(table["A4_adequate_advantageous_aggregate"].status, NOT_EVALUABLE)
        with self.assertRaises(ValueError):
            self.evaluate(downstream=downstream(USABLE), proximity={})

    def test_a6_without_sufficient_shared_failure_follows_overall_adequacy(self):
        from src.chapter3.chapter4_v2.framework import evidence_table

        def table(summary):
            ok = status("x", SATISFIED)
            return evidence_table(
                leader=None, adequacy={"g": ok}, proximity={"g": ok}, standalone=None,
                leave_one_out=None, g_id="g", g_margin_all_30=ok, g_omissions=ok,
                similarity=ok, corrections={"any_observed": False, "any_reciprocal": False,
                                            "any_stronger": False},
                found_differences={"annotation_differences": [], "downstream_differences": [],
                                   "downstream_distance_unavailable": 0},
                shared={"S_CB": {"by_class": {"positive": {
                    "E_sufficient_for_group_inadequacy": False,
                    "U_sufficient_for_group_inadequacy": False}}}},
                overall={"summary": summary})["A6_shared_errors_or_none_adequate"].status

        self.assertEqual(table("unresolved"), NOT_EVALUABLE)
        self.assertEqual(table("at_least_one_adequate"), NOT_SATISFIED)
        self.assertEqual(table("none_adequate"), SATISFIED)

    def test_every_row_carries_value_rule_sample_status_and_reason(self):
        for row in self.evaluate()["evidence_table"].values():
            record = row.as_record()
            self.assertEqual(set(record), {"name", "value", "rule", "sample", "comparator",
                                           "status", "reason"})
            self.assertIn(record["status"], (SATISFIED, NOT_SATISFIED, NOT_EVALUABLE))


class PlannedCheckTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def check(self, data, ids, counts):
        return planned_benchmark_check(data, sample_b(data), planned_item_ids=ids,
                                       planned_counts=counts)

    def test_a_match_with_the_planned_list_and_counts(self):
        data = fx.build_input(self.spec, n_items=4)
        result = self.check(data, ["SYN1", "SYN2", "SYN3", "SYN4"],
                            {"n_items": 4, "positives": 2, "negatives": 2})
        self.assertEqual((result["status"], result["differences"]), ("matches_plan", []))

    def test_differences_are_visible_and_change_nothing(self):
        rows = fx.make_item_rows(4)
        rows[0]["HUMAN"] = "?"
        data = fx.build_input(self.spec, item_rows=rows)
        b_before = sample_b(data).members
        result = self.check(data, ["SYN2", "SYN3", "SYN4", "SYN5"],
                            {"n_items": 4, "positives": 2, "negatives": 2})
        self.assertEqual(result["status"], "differs_from_plan")
        self.assertEqual(result["actual"]["human_not_binary"], ["SYN1"])
        self.assertEqual(result["integrity_discrepancies"],
                         [{"item_id": "SYN1", "issue": "member of B without a binary HUMAN class"}])
        self.assertEqual(result["scoring_of_members_without_binary_human"], "not decided (D-SAMP-02)")
        self.assertEqual((result["missing_from_data"], result["not_in_plan"]), (["SYN5"], ["SYN1"]))
        self.assertTrue(any("positives" in d for d in result["differences"]))
        self.assertEqual(sample_b(data).members, b_before)

    def test_the_framework_output_always_carries_the_check(self):
        data = fx.build_input(self.spec, n_items=4)
        result = evaluate_annotation_framework(self.spec, data, run_bootstrap=False)
        check = result["planned_benchmark_check"]
        self.assertEqual(check["planned"]["n_items"], 250)
        self.assertEqual(check["status"], "differs_from_plan", "a synthetic fixture is not B")


class MissingCountTests(SyntheticTestCase):
    def test_per_procedure_missing_counts_by_class_and_reason(self):
        spec = load_spec()
        registry = build_registry(spec)
        data = fx.build_input(spec, states={SlotKey("SYN1", "terra_5_6", "cm_base", 1): "parse_error",
                                            SlotKey("SYN2", "terra_5_6", "cb_t3_cot", 1): "absent"})
        counts = missing_by_procedure(build_vectors(data, registry), data,
                                      sample_b(data).members, "B")
        self.assertEqual(counts["cb::terra_5_6::cb_t3_cot"]["missing_by_class"],
                         {"positive": 0, "negative": 1})
        self.assertEqual(counts["cb::terra_5_6::cb_t3_cot"]["missing_by_reason"],
                         {"slot_planned_unobserved": 1})
        self.assertEqual(counts["va_g::s_p_m"]["missing_by_reason"], {"g_outside_i27": 1})
        self.assertEqual(counts["va_s::terra_5_6::cm_base"]["missing"], 1)
        self.assertEqual(len(counts), 31 + 27 + 3)
