"""Registry and aggregation: 31 fixed IDs, strict 3/3 and 27/27, hierarchy not pooled majority."""

import re

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import (
    REASON_G_OUTSIDE_I27,
    build_vectors,
    complete_majority,
    legacy_two_valid_concordant,
    va_complete_items,
)
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.procedures import (
    KIND_CB,
    KIND_G,
    KIND_VA_POST_S,
    build_registry,
)
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.hierarchy import majority as historical_majority

MODELS = ("terra_5_6", "sonnet_5", "deepseek_v4_pro")
PROMPTS = ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")


class RegistryTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def test_thirty_one_unique_primary_procedures(self):
        primary = self.registry.primary
        self.assertEqual(len(primary), 31)
        self.assertEqual(len({p.procedure_id for p in primary}), 31)
        self.assertEqual([len(self.registry.primary_of_kind(k)) for k in (KIND_CB, KIND_VA_POST_S,
                                                                          KIND_G)], [21, 9, 1])

    def test_ids_follow_the_specified_scheme(self):
        ids = self.registry.by_id()
        self.assertIn("cb::sonnet_5::cb_t3_cot", ids)
        self.assertIn("va_s::deepseek_v4_pro::cm_paraphrase_2", ids)
        self.assertIn("va_g::s_p_m", ids)
        self.assertIn("va_c::terra_5_6::cm_base::s3", ids)
        self.assertIn("va_sp::sonnet_5", ids)
        for p in self.registry.primary:
            self.assertRegex(p.procedure_id, r"^(cb|va_s|va_g)::")

    def test_components_and_within_model_vectors_are_not_primary(self):
        self.assertEqual(len(self.registry.va_components), 27)
        self.assertEqual(len(self.registry.va_post_sp), 3)
        primary_ids = {p.procedure_id for p in self.registry.primary}
        for p in self.registry.va_components + self.registry.va_post_sp:
            self.assertNotIn(p.procedure_id, primary_ids)
            self.assertFalse(p.is_primary)

    def test_coincident_vectors_keep_separate_identities(self):
        data = fx.build_input(self.spec, label_of=lambda k: 0)
        vectors = build_vectors(data, self.registry)
        self.assertEqual(len(vectors), 31 + 27 + 3)
        distinct = {tuple(sorted(v.labels.items())) for v in vectors.values()}
        self.assertEqual(len(distinct), 1, "every vector coincides in this fixture")


class MajorityRuleTests(SyntheticTestCase):
    def test_one_missing_vote_is_missing_under_the_primary_rule_only(self):
        self.assertIsNone(complete_majority([1, 1, None], 3))
        self.assertEqual(legacy_two_valid_concordant([1, 1, None]), 1)
        self.assertIsNone(legacy_two_valid_concordant([1, 0, None]))
        self.assertEqual(complete_majority([1, 1, 0], 3), 1)
        self.assertEqual(complete_majority([0, 1, 0], 3), 0)

    def test_the_primary_rule_refuses_a_wrong_number_of_contributions(self):
        with self.assertRaises(ValueError):
            complete_majority([1, 1], 3)
        with self.assertRaises(ValueError):
            complete_majority([1, 1], 2)


class AggregationTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def test_one_missing_va_call_removes_its_cell_and_g_but_nothing_else(self):
        bad = SlotKey("SYN1", "sonnet_5", "cm_base", 2)
        data = fx.build_input(self.spec, label_of=lambda k: 1, states={bad: "parse_error"})
        vectors = build_vectors(data, self.registry)
        cell = vectors["va_s::sonnet_5::cm_base"]
        self.assertIsNone(cell.label("SYN1"))
        self.assertEqual(cell.missing_reasons["SYN1"], "va_generations_incomplete:terminal_invalid")
        self.assertEqual(cell.label("SYN2"), 1)
        self.assertEqual(vectors["va_s::sonnet_5::cm_paraphrase_1"].label("SYN1"), 1)
        g = vectors["va_g::s_p_m"]
        self.assertIsNone(g.label("SYN1"))
        self.assertEqual(g.missing_reasons["SYN1"], REASON_G_OUTSIDE_I27)
        self.assertEqual(g.label("SYN2"), 1)
        self.assertIsNone(vectors["va_sp::sonnet_5"].label("SYN1"))
        self.assertEqual(vectors["va_sp::terra_5_6"].label("SYN1"), 1)
        self.assertNotIn("SYN1", va_complete_items(data))
        self.assertIsNone(vectors["va_c::sonnet_5::cm_base::s2"].label("SYN1"))
        self.assertEqual(vectors["va_c::sonnet_5::cm_base::s1"].label("SYN1"), 1)

    def test_hierarchy_differs_from_pooled_majority(self):
        # On SYN1. Terra: all nine calls 1. Sonnet and DeepSeek: base and
        # paraphrase_1 voted (1, 0, 0) -> 0, paraphrase_2 voted (1, 1, 1) -> 1,
        # so each of those models aggregates to 0. Hierarchy: 1, 0, 0 -> G = 0.
        # Pooled: 9 + 5 + 5 = 19 ones of 27 -> 1.
        def label_of(key):
            if key.item_id != "SYN1" or key.model_key == "terra_5_6":
                return 1
            if key.template_id == "cm_paraphrase_2":
                return 1
            return 1 if key.sample_index == 1 else 0

        data = fx.build_input(self.spec, label_of=label_of)
        vectors = build_vectors(data, self.registry)
        components = [vectors[f"va_c::{m}::{t}::s{s}"].label("SYN1")
                      for m in MODELS for t in PROMPTS for s in (1, 2, 3)]
        self.assertEqual(sum(components), 19)
        pooled = historical_majority(components).label
        self.assertEqual(pooled, 1)
        self.assertEqual(vectors["va_g::s_p_m"].label("SYN1"), 0)
        self.assertEqual([vectors[f"va_sp::{m}"].label("SYN1") for m in MODELS], [1, 0, 0])

    def test_cb_uses_its_designated_generation_and_keeps_missing_missing(self):
        bad = SlotKey("SYN2", "terra_5_6", "cb_t3_rot", 1)
        data = fx.build_input(self.spec, label_of=lambda k: 1, states={bad: "api_error_only"})
        vector = build_vectors(data, self.registry)["cb::terra_5_6::cb_t3_rot"]
        self.assertIsNone(vector.label("SYN2"))
        self.assertEqual(vector.missing_reasons["SYN2"], "slot_technical_failure")
        self.assertEqual(vector.label("SYN1"), 1)

    def test_every_missing_label_has_a_reason_and_no_reason_without_missing(self):
        states = {SlotKey("SYN3", "deepseek_v4_pro", "cm_paraphrase_1", 3): "absent",
                  SlotKey("SYN4", "terra_5_6", "cb_t3_tot", 1): "parse_error"}
        data = fx.build_input(self.spec, states=states)
        for vector in build_vectors(data, self.registry).values():
            missing = {i for i, label in vector.labels.items() if label is None}
            self.assertEqual(missing, set(vector.missing_reasons), vector.procedure_id)
            for reason in vector.missing_reasons.values():
                self.assertTrue(re.match(r"^(slot_|va_|g_)", reason), reason)
