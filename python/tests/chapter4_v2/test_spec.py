"""The specification: identity, internal arithmetic and the pending-module lock."""

import copy
import json
from fractions import Fraction

from _guard import SyntheticTestCase

from src.chapter3.chapter4_v2.spec import (
    DEFAULT_SPEC_PATH,
    SpecError,
    exact,
    load_spec,
    spec_from_mapping,
    spec_problems,
)
from src.chapter3.design import canonical_json_hash


class SpecTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.raw = json.loads(DEFAULT_SPEC_PATH.read_text(encoding="utf-8"))

    def mutated(self, change):
        data = copy.deepcopy(self.raw)
        change(data)
        return spec_problems(data)

    def test_the_committed_spec_is_valid_and_identified_by_its_canonical_hash(self):
        self.assertEqual(spec_problems(self.raw), [])
        self.assertEqual(self.spec.sha256, canonical_json_hash(self.raw))
        self.assertEqual(set(self.spec.identity()), {"spec_id", "spec_version", "spec_sha256"})

    def test_the_hash_ignores_layout_but_not_content(self):
        reordered = dict(reversed(list(self.raw.items())))
        self.assertEqual(spec_from_mapping(reordered).sha256, self.spec.sha256)
        changed = copy.deepcopy(self.raw)
        changed["scores"]["thresholds"]["ba_margin_min"] = "0.031"
        self.assertNotEqual(canonical_json_hash(changed), self.spec.sha256)

    def test_procedure_counts_follow_from_the_design(self):
        self.assertEqual(len(self.spec.model_keys) * len(self.spec.cb_template_ids), 21)
        self.assertEqual(len(self.spec.model_keys) * len(self.spec.va_template_ids), 9)
        problems = self.mutated(lambda d: d["design"]["cb_templates"].pop())
        self.assertTrue(any("primary_counts.cb" in p for p in problems))

    def test_minimum_correct_counts_follow_from_the_thresholds_exactly(self):
        # 0.925 * 218 = 201.65 exactly; a float product can drift either side.
        self.assertEqual(exact("0.925") * 218, Fraction(40330, 200))
        problems = self.mutated(lambda d: d["scores"]["planned_min_correct"].update(negatives=201))
        self.assertTrue(any("planned_min_correct" in p for p in problems))

    def test_shared_error_sufficiency_is_the_budget_plus_one(self):
        self.assertEqual(self.raw["scores"]["shared_error_sufficiency"],
                         {"positives": 9, "negatives": 17})
        problems = self.mutated(
            lambda d: d["scores"]["shared_error_sufficiency"].update(positives=8))
        self.assertTrue(any("shared_error_sufficiency" in p for p in problems))

    def test_thresholds_must_be_decimal_strings(self):
        with self.assertRaises(SpecError):
            exact(0.75)
        problems = self.mutated(lambda d: d["scores"]["thresholds"].update(a_plus_min=0.75))
        self.assertTrue(problems)

    def test_h3_inference_is_disabled_and_cannot_be_enabled_while_pending(self):
        self.assertFalse(self.spec.module_enabled("h3_inference"))
        self.assertEqual(self.spec.module("h3_inference")["methodological_status"],
                         "decision_pending")
        problems = self.mutated(lambda d: d["modules"]["h3_inference"].update(enabled=True))
        self.assertTrue(any("h3_inference" in p and "enabled" in p for p in problems))

    def test_every_pending_module_is_disabled(self):
        for name, module in self.raw["modules"].items():
            if module["methodological_status"] != "confirmed":
                self.assertFalse(module["enabled"], name)

    def test_the_primary_aggregation_cannot_fall_back(self):
        problems = self.mutated(
            lambda d: d["aggregation"].update(va_post_s_required_valid_generations=2))
        self.assertTrue(any("planned generations" in p for p in problems))
        problems = self.mutated(lambda d: d["aggregation"].update(pooled_majority_as_primary=True))
        self.assertTrue(problems)

    def test_firth_has_no_fallback_and_35_fits(self):
        self.assertEqual(self.raw["downstream"]["fits"]["total"], 35)
        problems = self.mutated(
            lambda d: d["downstream"]["estimator"].update(fallback="statsmodels MLE"))
        self.assertTrue(any("fallback" in p for p in problems))

    def test_a_missing_section_is_reported(self):
        problems = self.mutated(lambda d: d.pop("framework_bootstrap"))
        self.assertIn("missing section 'framework_bootstrap'", problems)
