"""H1: complete triplets only, the 2/3 identity, partial support apart, no CB comparator."""

import random
from fractions import Fraction
from itertools import combinations, product

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.h1 import h1_variation, triplet_summary
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.analysis_status import COMPUTED, NOT_COMPUTABLE


class IdentityTests(SyntheticTestCase):
    def test_each_binary_triplet_has_zero_or_two_disagreeing_pairs(self):
        for triplet in product((0, 1), repeat=3):
            pairs = sum(a != b for a, b in combinations(triplet, 2))
            self.assertEqual(pairs, 0 if len(set(triplet)) == 1 else 2, triplet)

    def test_the_identity_holds_on_random_synthetic_collections(self):
        rng = random.Random(7)
        for _ in range(200):
            triplets = [tuple(rng.randint(0, 1) for _ in range(3))
                        for _ in range(rng.randint(1, 40))]
            summary = triplet_summary(triplets)
            self.assertEqual(summary["mean_pairwise_disagreement"],
                             Fraction(2, 3) * summary["not_unanimous_proportion"])

    def test_no_triplet_means_no_summary(self):
        summary = triplet_summary([])
        self.assertIsNone(summary["not_unanimous_proportion"])
        self.assertIsNone(summary["mean_pairwise_disagreement"])


class CellTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        # Sonnet base cell: SYN1 (1,0,0), SYN2 (0,0,0), SYN3 incomplete, SYN4 (1,1,1).
        patterns = {"SYN1": (1, 0, 0), "SYN2": (0, 0, 0), "SYN3": (1, 1, 1), "SYN4": (1, 1, 1)}

        def label_of(k):
            if (k.model_key, k.template_id) == ("sonnet_5", "cm_base"):
                return patterns[k.item_id][k.sample_index - 1]
            return 0

        cls.data = fx.build_input(cls.spec, label_of=label_of,
                                  states={SlotKey("SYN3", "sonnet_5", "cm_base", 2): "parse_error"})
        cls.result = h1_variation(cls.data)

    def cell(self, model, template):
        return next(c for c in self.result["cells"]
                    if (c["model_key"], c["template_id"]) == (model, template))

    def test_only_complete_triplets_and_partial_support_apart(self):
        cell = self.cell("sonnet_5", "cm_base")
        self.assertEqual((cell["n_complete"], cell["n_not_unanimous"]), (3, 1))
        self.assertEqual(cell["not_unanimous_proportion"]["exact"], "1/3")
        self.assertEqual(cell["mean_pairwise_disagreement"]["exact"], "2/9")
        self.assertEqual(cell["incomplete"], {"n": 1, "by_valid_count": {2: 1}})
        self.assertEqual(cell["status"], COMPUTED)

    def test_nine_va_cells_and_no_cb_comparator(self):
        self.assertEqual(len(self.result["cells"]), 9)
        self.assertTrue(all(c["template_id"].startswith("cm_") for c in self.result["cells"]))
        self.assertIsNone(self.result["cb_comparator"])
        self.assertEqual(self.result["data_kind"], "synthetic")

    def test_a_cell_without_complete_triplets_is_not_computable(self):
        states = {SlotKey(f"SYN{i}", "terra_5_6", "cm_paraphrase_1", 1): "api_error_only"
                  for i in range(1, 5)}
        result = h1_variation(fx.build_input(self.spec, states=states))
        cell = next(c for c in result["cells"]
                    if (c["model_key"], c["template_id"]) == ("terra_5_6", "cm_paraphrase_1"))
        self.assertEqual((cell["status"], cell["n_complete"]), (NOT_COMPUTABLE, 0))
        self.assertIsNone(cell["not_unanimous_proportion"])
