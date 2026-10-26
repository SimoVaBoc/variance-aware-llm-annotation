"""Undefined Cohen's kappa is NA, never 1: historical counts, pairwise, against HUMAN, bootstrap.

Kappa against HUMAN is computed exactly by ``framework.kappa_exact(vector, None, ...)``
(reported as ``kappa_vs_human_B`` by the annotation framework) and, per replicate,
by ``FrameworkReplicates.kappa(vector)`` in the framework bootstrap. Pairwise kappa
is ``kappa_exact(a, b, ...)`` in the 465-pair table.
"""

import numpy as np

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.bootstrap import kappa_from_counts
from src.chapter3.chapter4_v2.aggregation import LabelVector, build_vectors
from src.chapter3.chapter4_v2.annotation_framework import evaluate_annotation_framework
from src.chapter3.chapter4_v2.framework import kappa_exact, pair_table
from src.chapter3.chapter4_v2.framework_bootstrap import (
    FrameworkReplicates,
    draws_for,
    percentile_interval,
)
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b
from src.chapter3.chapter4_v2.spec import load_spec


def counts(tp, tn, fp, fn):
    return kappa_from_counts({k: np.array([v], dtype=float)
                              for k, v in zip(("tp", "tn", "fp", "fn"), (tp, tn, fp, fn))})[0]


class HistoricalCountsTests(SyntheticTestCase):
    def test_constant_equal_labellings_and_empty_support_are_nan(self):
        self.assertTrue(np.isnan(counts(5, 0, 0, 0)))
        self.assertTrue(np.isnan(counts(0, 5, 0, 0)))
        self.assertTrue(np.isnan(counts(0, 0, 0, 0)))

    def test_defined_cases(self):
        self.assertEqual(counts(3, 2, 0, 0), 1.0)
        self.assertEqual(counts(0, 0, 5, 0), 0.0, "constant but opposite labellings: pe = 0")


class KappaTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)
        cls.data = fx.build_input(cls.spec, n_items=6, label_of=lambda k: 0)
        cls.members = sample_b(cls.data).members
        cls.vectors = build_vectors(cls.data, cls.registry)

    def positives_only(self):
        """Labelled 1 on the positives only; missing on every negative."""
        labels = {i: (1 if self.data.items[i].human == 1 else None) for i in self.members}
        return LabelVector("synthetic_positive_only", "cb", labels,
                           {i: "slot_planned_unobserved" for i, v in labels.items() if v is None})

    def test_pairwise_kappa_of_two_constant_equal_vectors_is_none(self):
        pairs = pair_table(self.registry, self.vectors, self.data, self.members)
        self.assertTrue(all(p["kappa"] is None for p in pairs), "every vector is constant 0")
        self.assertTrue(all(p["kappa_support"] == 6 for p in pairs))

    def test_kappa_against_human_is_none_when_the_support_has_one_class_only(self):
        # Every valid label agrees with HUMAN, which a naive reading would call kappa = 1.
        kappa, support = kappa_exact(self.positives_only(), None, self.data, self.members)
        self.assertIsNone(kappa)
        self.assertEqual(support, 3)

    def test_kappa_against_human_is_reported_by_the_framework(self):
        result = evaluate_annotation_framework(self.spec, self.data, run_bootstrap=False)
        record = result["kappa_vs_human_B"]["cb::terra_5_6::cb_t3_cot"]
        self.assertEqual(record["kappa"], 0, "constant label against varying HUMAN: defined, 0")
        self.assertEqual(record["valid_paired_support"], 6)
        self.assertEqual(len(result["kappa_vs_human_B"]), 31)

    def test_bootstrap_kappa_against_human_is_nan_never_one(self):
        reps = FrameworkReplicates(draws_for(self.spec, self.data, self.members), self.data)
        values = reps.kappa(self.positives_only())
        self.assertTrue(np.isnan(values).all())
        self.assertTrue(np.isnan(reps.kappa(self.positives_only(), original=True)).all())
        interval = percentile_interval(values, [0.025, 0.975])
        self.assertFalse(interval["available"])
        self.assertEqual(interval["defined_share"], 0.0)
