"""Framework bootstrap: determinism and structure, fixed comparators, interval rules.

No test pins a value of the random stream: they compare the implementation with
a reference written from the specification, check structure, and check that a
different draw order is detected by the index hash.
"""

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import LabelVector, build_vectors
from src.chapter3.chapter4_v2.comparisons import G_MARGINS, g_comparators
from src.chapter3.chapter4_v2.framework_bootstrap import (
    BootstrapError,
    FrameworkReplicates,
    draw_stratified,
    draws_for,
    percentile_interval,
    run_framework_bootstrap,
)
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b
from src.chapter3.chapter4_v2.scores import score_vector
from src.chapter3.chapter4_v2.spec import load_spec

POS = ["P3", "P1", "P2"]
NEG = ["N2", "N4", "N1", "N3", "N5"]


class DrawTests(SyntheticTestCase):
    def test_same_seed_same_indices_different_seed_different(self):
        a = draw_stratified(POS, NEG, 20261024, 200)
        b = draw_stratified(POS, NEG, 20261024, 200)
        c = draw_stratified(POS, NEG, 20261025, 200)
        self.assertEqual(a.sha256(), b.sha256())
        self.assertTrue(np.array_equal(a.indices, b.indices))
        self.assertNotEqual(a.sha256(), c.sha256())

    def test_ids_are_lexicographic_within_class_positives_first(self):
        draws = draw_stratified(POS, NEG, 1, 3)
        self.assertEqual(draws.item_order, ("P1", "P2", "P3", "N1", "N2", "N3", "N4", "N5"))

    def test_stream_matches_the_specified_order(self):
        draws = draw_stratified(POS, NEG, 20261024, 50)
        rng = np.random.Generator(np.random.PCG64(20261024))
        for r in range(50):
            self.assertTrue(np.array_equal(draws.indices[r, :3],
                                           rng.integers(0, 3, size=3, dtype=np.int64)))
            self.assertTrue(np.array_equal(draws.indices[r, 3:] - 3,
                                           rng.integers(0, 5, size=5, dtype=np.int64)))

    def test_a_vectorised_draw_order_changes_the_hash(self):
        draws = draw_stratified(POS, NEG, 20261024, 50)
        rng = np.random.Generator(np.random.PCG64(20261024))
        alternative = np.hstack([rng.integers(0, 3, size=(50, 3), dtype=np.int64),
                                 3 + rng.integers(0, 5, size=(50, 5), dtype=np.int64)])
        self.assertFalse(np.array_equal(alternative, draws.indices))

    def test_class_sizes_and_multiplicities_are_preserved(self):
        draws = draw_stratified(POS, NEG, 7, 400)
        self.assertTrue(((draws.indices[:, :3] >= 0) & (draws.indices[:, :3] < 3)).all())
        self.assertTrue(((draws.indices[:, 3:] >= 3) & (draws.indices[:, 3:] < 8)).all())
        weights = draws.weights()
        self.assertTrue((weights[:, :3].sum(axis=1) == 3).all())
        self.assertTrue((weights[:, 3:].sum(axis=1) == 5).all())
        for r in (0, 17, 399):
            self.assertTrue(np.array_equal(weights[r], np.bincount(draws.indices[r], minlength=8)))
        self.assertGreater((weights > 1).sum(), 0, "campaigns drawn twice keep their multiplicity")

    def test_both_classes_are_required(self):
        with self.assertRaises(BootstrapError):
            draw_stratified([], NEG, 1, 2)

    def test_the_specification_fixes_seed_and_size(self):
        spec = load_spec()
        data = fx.build_input(spec, n_items=4)
        draws = draws_for(spec, data, sample_b(data).members)
        self.assertEqual((draws.seed, draws.n_replications), (20261024, 10000))
        meta = draws.metadata()
        self.assertEqual(meta["generator"], "numpy.random.Generator(numpy.random.PCG64(seed))")
        self.assertIn("numpy", meta["software"])

    def test_saved_indices_reload_with_their_hash_and_never_overwrite(self):
        root = Path(tempfile.mkdtemp(prefix="synthetic_boot_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        draws = draw_stratified(POS, NEG, 3, 20)
        record = draws.save(root)
        reloaded = np.load(root / "bootstrap_indices.npy", allow_pickle=False)
        self.assertTrue(np.array_equal(reloaded, draws.indices))
        meta = json.loads((root / "bootstrap_draws.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["indices_sha256"], draws.sha256())
        self.assertEqual(meta["item_order"], list(draws.item_order))
        self.assertEqual(record["seed"], 3)
        with self.assertRaises(BootstrapError):
            draws.save(root)


class IntervalTests(SyntheticTestCase):
    def test_percentile_interval_uses_linear_interpolation(self):
        interval = percentile_interval(np.arange(101, dtype=float), [0.025, 0.975])
        self.assertEqual((interval["low"], interval["high"]), (2.5, 97.5))
        self.assertTrue(interval["available"])

    def test_one_undefined_replicate_suppresses_the_interval(self):
        values = np.r_[np.zeros(9999), np.nan]
        interval = percentile_interval(values, [0.025, 0.975])
        self.assertFalse(interval["available"])
        self.assertIsNone(interval["low"])
        self.assertEqual(interval["n_defined"], 9999)


class ReplicateTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

        # Twelve items, odd ones positive. Terra's zero-shot CB is right except on SYN01
        # (a positive); Terra's base VA prompt is right except on SYN02 (a negative). Both
        # have BA 11/12, so they tie as best of 30 and the CB identity names it. All other
        # configurations predict 0. In replicates the two comparators move apart.
        def label_of(k):
            truth = int(k.item_id[3:]) % 2
            if (k.model_key, k.template_id) == ("terra_5_6", "cb_t3_zero_shot"):
                return 0 if k.item_id == "SYN01" else truth
            if (k.model_key, k.template_id) == ("terra_5_6", "cm_base"):
                return 1 if k.item_id == "SYN02" else truth
            return 0

        cls.data = fx.build_input(cls.spec, n_items=12, label_of=label_of)
        cls.vectors = build_vectors(cls.data, cls.registry)
        cls.members = sample_b(cls.data).members
        cls.primary = [p.procedure_id for p in cls.registry.primary]
        cls.scores = {pid: score_vector(cls.vectors[pid], cls.data, cls.members, "B")
                      for pid in cls.primary}
        cls.comparators = g_comparators(cls.registry, cls.scores)
        cls.draws = draws_for(cls.spec, cls.data, cls.members)
        cls.result = run_framework_bootstrap(
            cls.spec, cls.data, cls.draws, cls.vectors, cls.primary, cls.scores,
            {name: (cls.registry.g.procedure_id, cls.comparators[name]) for name in G_MARGINS})
        cls.reps = FrameworkReplicates(cls.draws, cls.data)

    def ba(self, pid):
        return self.reps.scores(self.vectors[pid])["ba"]

    def test_original_sample_weights_reproduce_the_point_scores(self):
        for pid in self.primary:
            point = self.scores[pid]
            record = self.result["procedures"][pid]
            self.assertAlmostEqual(record["ba"]["point_estimate"]["value"], float(point.ba))

    def test_comparators_stay_fixed_at_their_original_identity(self):
        cb_best = self.comparators["g_minus_best_cb"].procedure_id
        va_best = self.comparators["g_minus_best_va_post_s"].procedure_id
        self.assertEqual((cb_best, va_best), ("cb::terra_5_6::cb_t3_zero_shot",
                                              "va_s::terra_5_6::cm_base"))
        record = self.result["margins"]["g_minus_best_cb"]
        self.assertEqual(record["comparator"], cb_best)
        self.assertTrue(record["comparator_fixed_from_original_sample"])

    def test_margin_intervals_use_the_fixed_comparator_in_every_replicate(self):
        g = self.registry.g.procedure_id
        for name in G_MARGINS:
            fixed = self.comparators[name].procedure_id
            expected = percentile_interval(self.ba(g) - self.ba(fixed), [0.025, 0.975])
            self.assertEqual(self.result["margins"][name]["interval"], expected, name)
        # Re-searching the best of 30 in each replicate would change replicate values.
        ids = [p.procedure_id for p in self.registry.primary if p.kind in ("cb", "va_post_s")]
        searched = self.ba(g) - np.max([self.ba(pid) for pid in ids], axis=0)
        fixed = self.ba(g) - self.ba(self.comparators["g_minus_best_all_30"].procedure_id)
        self.assertTrue((searched != fixed).any())

    def test_third_margin_is_the_minimum_only_at_the_point_estimate(self):
        g = self.registry.g.procedure_id
        m_cb = self.ba(g) - self.ba(self.comparators["g_minus_best_cb"].procedure_id)
        m_va = self.ba(g) - self.ba(self.comparators["g_minus_best_va_post_s"].procedure_id)
        fixed30 = self.comparators["g_minus_best_all_30"].procedure_id
        m_30 = self.ba(g) - self.ba(fixed30)
        # The fixed best-of-30 identity is the CB comparator (tie named by the smaller ID).
        self.assertEqual(fixed30, self.comparators["g_minus_best_cb"].procedure_id)
        self.assertTrue(np.array_equal(m_30, m_cb))
        # At the point estimate it is the minimum of the two arm margins...
        points = {n: self.scores[g].ba - self.comparators[n].ba for n in G_MARGINS}
        self.assertEqual(points["g_minus_best_all_30"],
                         min(points["g_minus_best_cb"], points["g_minus_best_va_post_s"]))
        # ...but not in every replicate.
        differs = m_30 != np.minimum(m_cb, m_va)
        self.assertTrue(differs.any())
        self.assertFalse(differs.all())

    def test_kappa_interval_is_suppressed_when_some_replicates_are_undefined(self):
        # Labels only on SYN01 (positive, labelled 1) and SYN02 (negative, labelled 0):
        # kappa is 1 when both are drawn and undefined when only one class appears.
        labels = {i: None for i in self.data.design.item_ids}
        labels.update({"SYN01": 1, "SYN02": 0})
        sparse = LabelVector("synthetic_sparse", "cb", labels,
                             {i: "slot_planned_unobserved" for i, v in labels.items() if v is None})
        values = self.reps.kappa(sparse)
        self.assertTrue(np.isnan(values).any())
        self.assertFalse(np.isnan(values).all())
        interval = percentile_interval(values, [0.025, 0.975])
        self.assertFalse(interval["available"])
        self.assertTrue(0 < interval["defined_share"] < 1)

    def test_a_non_kappa_statistic_undefined_in_some_replicates_has_no_interval(self):
        # Extension of the brief's kappa rule to every statistic. A valid-support ratio
        # (correct / valid) of a vector labelled only on SYN01 and SYN02 has a zero
        # denominator whenever neither campaign is drawn.
        labels = {i: None for i in self.data.design.item_ids}
        labels.update({"SYN01": 1, "SYN02": 1})
        vector = LabelVector("synthetic_sparse", "cb", labels,
                             {i: "slot_planned_unobserved" for i, v in labels.items() if v is None})
        valid, _, correct = self.reps._arrays(vector)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = (self.reps.weights @ correct) / (self.reps.weights @ valid)
        self.assertTrue(np.isnan(ratio).any())
        self.assertFalse(np.isnan(ratio).all())
        interval = percentile_interval(ratio, [0.025, 0.975])
        self.assertFalse(interval["available"])
        self.assertIsNone(interval["high"])
        self.assertTrue(0 < interval["defined_share"] < 1)

    def test_records_state_their_conditioning_and_the_draw_hash(self):
        self.assertTrue(self.result["conditional_on_selected_comparators"])
        self.assertTrue(self.result["decisions_use_point_estimates"])
        self.assertEqual(self.result["draws"]["indices_sha256"], self.draws.sha256())
        self.assertEqual(self.result["draws"]["n_replications"], 10000)
