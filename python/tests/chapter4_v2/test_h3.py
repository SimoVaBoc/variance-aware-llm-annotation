"""H3: point contrast on the common I27, uniform mean of 27 components, inference disabled."""

import copy
import json
from fractions import Fraction

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.h3 import h3_inference, h3_point_contrast
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.pending import DecisionPending
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b, sample_i27
from src.chapter3.chapter4_v2.spec import DEFAULT_SPEC_PATH, SpecError, load_spec, spec_from_mapping
from src.chapter3.chapter4_v2.analysis_status import COMPUTED, NOT_COMPUTABLE

MODELS = ("terra_5_6", "sonnet_5", "deepseek_v4_pro")
PROMPTS = ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")
COMPONENTS = [(m, t, s) for m in MODELS for t in PROMPTS for s in (1, 2, 3)]


def truth(item):
    return int(item[3:]) % 2


class ContrastTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def run_h3(self, label_of, n=12, states=None, rows=None):
        data = fx.build_input(self.spec, n_items=n, item_rows=rows, label_of=label_of,
                              states=states)
        vectors = build_vectors(data, self.registry)
        b = sample_b(data)
        i27 = sample_i27(data, b)
        return data, vectors, i27, h3_point_contrast(data, self.registry, vectors, b, i27)

    def test_delta_is_ba_of_g_minus_the_uniform_mean_of_27_component_bas(self):
        # Component k is wrong only on campaign SYN{(k mod 9) + 1}; G corrects every error.
        def label_of(k):
            index = COMPONENTS.index((k.model_key, k.template_id, k.sample_index)) \
                if k.template_id.startswith("cm_") else None
            if index is not None and k.item_id == f"SYN{index % 9 + 1:02d}":
                return 1 - truth(k.item_id)
            return truth(k.item_id)

        data, vectors, i27, result = self.run_h3(label_of)
        self.assertEqual(result["status"], COMPUTED)
        members = list(i27.members)
        pos = [i for i in members if truth(i) == 1]
        neg = [i for i in members if truth(i) == 0]
        bas = []
        for m, t, s in COMPONENTS:
            labels = {i: data.slots[SlotKey(i, m, t, s)].label for i in members}
            sens = Fraction(sum(labels[i] == 1 for i in pos), len(pos))
            spec_ = Fraction(sum(labels[i] == 0 for i in neg), len(neg))
            bas.append((sens + spec_) / 2)
        expected = 1 - sum(bas, Fraction(0)) / 27
        self.assertEqual(Fraction(result["delta_ba"]["exact"]), expected)
        self.assertEqual(result["ba_g"]["exact"], "1/1")
        self.assertEqual(result["n_components"], 27)
        self.assertFalse(result["framework_margin_applied"])
        self.assertEqual([key for key in result if "margin" in key], ["framework_margin_applied"],
                         "no margin value or margin status is produced for H3")

    def test_opposite_class_contributions_add_up_to_delta(self):
        # SYN01 (positive): hierarchy gives 0 though 19 of 27 components say 1 (G loses
        # sensitivity). Each component is also wrong on one negative, which G corrects.
        def label_of(k):
            if not k.template_id.startswith("cm_"):
                return 0
            if k.item_id == "SYN01":
                if k.model_key == "terra_5_6" or k.template_id == "cm_paraphrase_2":
                    return 1
                return 1 if k.sample_index == 1 else 0
            index = COMPONENTS.index((k.model_key, k.template_id, k.sample_index))
            negatives = [f"SYN{j:02d}" for j in range(2, 13, 2)]
            if k.item_id == negatives[index % 6]:
                return 1
            return truth(k.item_id)

        _, _, _, result = self.run_h3(label_of)
        sens = Fraction(result["sensitivity_contribution"]["exact"])
        spec_ = Fraction(result["specificity_contribution"]["exact"])
        self.assertLess(sens, 0)
        self.assertGreater(spec_, 0)
        self.assertEqual(sens + spec_, Fraction(result["delta_ba"]["exact"]))

    def test_only_the_common_i27_campaigns_are_used_and_exclusions_reported(self):
        states = {SlotKey("SYN03", "sonnet_5", "cm_base", 2): "parse_error"}
        _, _, i27, result = self.run_h3(lambda k: truth(k.item_id), states=states)
        self.assertNotIn("SYN03", i27.members)
        self.assertEqual(result["coverage"]["I27"], {"positive": 5, "negative": 6})
        self.assertEqual(result["coverage"]["excluded_from_I27"], 1)
        self.assertIn("va_terminal_invalid", result["coverage"]["exclusion_reason_counts"])
        self.assertEqual(result["delta_ba"]["exact"], "0/1")

    def test_an_absent_class_makes_the_contrast_not_computable(self):
        rows = fx.make_item_rows(6)
        for row in rows:
            row["HUMAN"] = "0"
        _, _, _, result = self.run_h3(lambda k: 0, n=6, rows=rows)
        self.assertEqual(result["status"], NOT_COMPUTABLE)
        self.assertIsNone(result["delta_ba"])


class InferenceTests(SyntheticTestCase):
    def test_inference_cannot_execute_while_its_decision_is_pending(self):
        spec = load_spec()
        with self.assertRaises(DecisionPending) as caught:
            h3_inference(spec, "any", "arguments", n_resamples=10000)
        self.assertIn("D-H3-02", str(caught.exception))

    def test_a_specification_cannot_enable_it_without_a_decision(self):
        raw = json.loads(DEFAULT_SPEC_PATH.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(raw)
        mutated["modules"]["h3_inference"]["enabled"] = True
        with self.assertRaises(SpecError):
            spec_from_mapping(mutated)
