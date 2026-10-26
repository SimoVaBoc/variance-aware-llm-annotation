"""Judging adapter outputs, distances and proximity, H4 and E1. Pure Python: no R.

Adapter outputs are built by hand in the adapter's exchange format (hexadecimal
doubles), so every certification and failure branch is exercised exactly.
"""

import math
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.firth import (
    FAILED,
    POINT_ONLY,
    USABLE,
    DownstreamResult,
    FitAssessment,
    assess,
)
from src.chapter3.chapter4_v2.h4_e1 import e1_points, h4_dispersion, plot_e1, population_sd
from src.chapter3.chapter4_v2.inputs import SlotKey
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b, sample_r
from src.chapter3.chapter4_v2.scores import score_vector
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.analysis_status import COMPUTED, NOT_COMPUTABLE
from src.chapter3.chapter4_v2.thresholds import NOT_EVALUABLE, NOT_SATISFIED, SATISFIED

H = float.hex


def output(coefs=(0.1, -0.5, 0.2), conv=(1e-9, 1e-9, 1e-9), pl=(1e-12, 1e-9, 1e-12, 1e-9),
           pl_iter=(5, 5), ci=(-1.0, 0.3), label_var=0.04, **extra):
    k = len(coefs)
    var = np.eye(k) * 0.04
    var[1, 1] = label_var
    record = {
        "status": "fitted", "warnings": [], "coefficient_names": ["(Intercept)", "LABEL", "lgoal"][:k],
        "coefficients_hex": [H(float(c)) for c in coefs],
        "var_hex": [H(float(v)) for v in var.ravel()],
        "conv_hex": {"loglik_change": H(conv[0]), "max_abs_score": H(conv[1]),
                     "beta_change": H(conv[2])},
        "iter": {"full": 4, "null": 3},
        "label_ci_hex": {"lower": H(ci[0]), "upper": H(ci[1])},
        "label_pl_conv_hex": {"lower_loglik": H(pl[0]), "lower_beta": H(pl[1]),
                              "upper_loglik": H(pl[2]), "upper_beta": H(pl[3])},
        "label_pl_iter": {"lower": pl_iter[0], "upper": pl_iter[1]},
        "firth": True, "flic": False, "method_ci": ["-", "Profile Likelihood", "-"][:k],
    }
    record.update(extra)
    return record


class AssessmentTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def test_certified_fit_with_converged_profile_is_usable_bit_for_bit(self):
        result = assess("x", output(coefs=(0.1, -0.123456789012345678, 0.2)), self.spec)
        self.assertEqual(result.status, USABLE)
        self.assertEqual(result.coefficient.hex(), (-0.123456789012345678).hex())
        self.assertEqual(result.ci, (-1.0, 0.3))

    def test_each_convergence_value_is_checked_and_named(self):
        for index, name in enumerate(("loglik_change", "max_abs_score", "beta_change")):
            conv = [1e-9, 1e-9, 1e-9]
            conv[index] = 1.1e-6
            result = assess("x", output(conv=tuple(conv)), self.spec)
            self.assertEqual(result.status, FAILED, name)
            self.assertEqual(result.reasons, [f"convergence not certified: {name}"])

    def test_tolerances_are_inclusive_and_signs_ignored(self):
        self.assertEqual(assess("x", output(conv=(-1e-6, 1e-6, 1e-6)), self.spec).status, USABLE)

    def test_a_profile_limit_that_fails_leaves_a_descriptive_point(self):
        for kwargs in ({"pl": (1e-3, 1e-9, 1e-12, 1e-9)}, {"pl": (1e-12, 1e-9, 1e-12, 1e-4)},
                       {"pl_iter": (5, 1000)}, {"ci": (-math.inf, 0.3)},
                       {"method_ci": ["-", "Wald", "-"]}):
            result = assess("x", output(**kwargs), self.spec)
            self.assertEqual(result.status, POINT_ONLY, kwargs)
            self.assertIsNone(result.ci)
            self.assertIsNotNone(result.coefficient)

    def test_non_finite_estimates_zero_variance_errors_and_flic_fail(self):
        self.assertEqual(assess("x", output(coefs=(0.1, math.nan, 0.2)), self.spec).status, FAILED)
        self.assertEqual(assess("x", output(label_var=0.0), self.spec).status, FAILED)
        self.assertEqual(assess("x", output(flic=True), self.spec).status, FAILED)
        error = assess("x", {"status": "error", "error": "singular"}, self.spec)
        self.assertEqual((error.status, error.reasons), (FAILED, ["adapter: error: singular"]))
        refused = assess("x", {"status": "refused", "error": "design differs"}, self.spec)
        self.assertEqual(refused.status, FAILED)


def fit(name, status, coefficient=None):
    return FitAssessment(name, status, reasons=[] if status == USABLE else ["synthetic reason"],
                         coefficient=coefficient,
                         ci=(coefficient - 1, coefficient + 1) if status == USABLE else None)


class ProximityTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def result(self, human_status=USABLE, **fits):
        all_fits = {"HUMAN": fit("HUMAN", human_status, 1.0)}
        all_fits.update({k: fit(k, *v) for k, v in fits.items()})
        return DownstreamResult(None, all_fits, {})

    def test_distance_boundary_is_inclusive_on_the_exact_double(self):
        res = self.result(a=(USABLE, 1.41), b=(USABLE, float(np.nextafter(1.41, 2.0))))
        prox = res.proximity(self.spec, ["a", "b"])
        self.assertEqual(res.distance_to_human("a"), 1.41 - 1.0)
        self.assertEqual(prox["a"].status, SATISFIED)
        self.assertEqual(prox["b"].status, NOT_SATISFIED)

    def test_a_human_failure_makes_every_distance_unavailable(self):
        res = self.result(human_status=FAILED, a=(USABLE, 1.0), b=(USABLE, 5.0))
        prox = res.proximity(self.spec, ["a", "b"])
        self.assertTrue(all(c.status == NOT_EVALUABLE for c in prox.values()))
        self.assertIn("HUMAN fit not usable", prox["a"].reason)
        self.assertIsNone(res.distance_to_human("a"))

    def test_a_procedure_failure_affects_only_its_own_distance(self):
        res = self.result(a=(FAILED, None), b=(USABLE, 1.2), c=(POINT_ONLY, 3.0))
        prox = res.proximity(self.spec, ["a", "b", "c"])
        self.assertEqual(prox["a"].status, NOT_EVALUABLE)
        self.assertEqual(prox["b"].status, SATISFIED)
        self.assertEqual(prox["c"].status, NOT_EVALUABLE)
        self.assertEqual(prox["c"].value, {"descriptive_distance": 2.0})
        self.assertIn("descriptive only", prox["c"].reason)

    def test_pairwise_distance_needs_two_usable_fits(self):
        res = self.result(a=(USABLE, 1.0), b=(USABLE, 1.3), c=(POINT_ONLY, 1.1))
        self.assertAlmostEqual(res.pairwise_distance("a", "b"), 0.3)
        self.assertIsNone(res.pairwise_distance("a", "c"))
        self.assertIsNone(res.pairwise_distance("a", "missing"))


class H4Tests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.models, cls.prompts = cls.spec.model_keys, cls.spec.va_template_ids

    def result(self, pre, post, failed=()):
        fits = {"HUMAN": fit("HUMAN", USABLE, 0.0)}
        for (m, p), value in pre.items():
            pid = f"va_s::{m}::{p}"
            fits[pid] = fit(pid, FAILED if pid in failed else USABLE, value)
        for m, value in post.items():
            pid = f"va_sp::{m}"
            fits[pid] = fit(pid, FAILED if pid in failed else USABLE, value)
        return DownstreamResult(None, fits, {})

    def test_sd_uses_denominator_three(self):
        self.assertAlmostEqual(population_sd([0.0, 0.3, 0.6]), math.sqrt(0.06))
        self.assertNotAlmostEqual(population_sd([0.0, 0.3, 0.6]), 0.3)

    def test_grouping_by_prompt_then_models_and_the_three_outcomes(self):
        # Within each prompt the models are 0, 0.3, 0.6 (SD sqrt(0.06), range 0.6);
        # across prompts nothing varies, so pooling all nine would give the same SD
        # only by accident: the second prompt is shifted to make pooling differ.
        pre = {}
        for j, p in enumerate(self.prompts):
            for i, m in enumerate(self.models):
                pre[(m, p)] = 0.3 * i + (1.0 if j == 1 else 0.0)
        post = {m: 0.1 * i for i, m in enumerate(self.models)}
        result = h4_dispersion(self.spec, self.result(pre, post))
        self.assertEqual(result["status"], COMPUTED)
        self.assertAlmostEqual(result["D_pre"], math.sqrt(0.06))
        pooled = population_sd(list(pre.values()))
        self.assertNotAlmostEqual(result["D_pre"], pooled)
        self.assertAlmostEqual(result["D_post"], population_sd([0.0, 0.1, 0.2]))
        self.assertGreater(result["Delta_D"], 0)
        self.assertAlmostEqual(result["percent_contraction"],
                               100 * result["Delta_D"] / result["D_pre"])
        self.assertEqual(result["outcomes"], {"contraction": True, "final_within_tolerance": True,
                                              "contraction_crossing_into_tolerance": True})

    def test_zero_pre_dispersion_gives_no_percentage(self):
        pre = {(m, p): 0.5 for m in self.models for p in self.prompts}
        post = {m: 0.5 for m in self.models}
        result = h4_dispersion(self.spec, self.result(pre, post))
        self.assertEqual(result["D_pre"], 0)
        self.assertIsNone(result["percent_contraction"])
        self.assertFalse(result["outcomes"]["contraction"])

    def test_range_boundary_and_no_crossing_when_already_within(self):
        pre = {(m, p): 0.1 * i for i, m in enumerate(self.models) for p in self.prompts}
        post_on = {m: v for m, v in zip(self.models, (0.0, 0.41, 0.2))}
        on = h4_dispersion(self.spec, self.result(pre, post_on))
        self.assertTrue(on["outcomes"]["final_within_tolerance"])
        self.assertFalse(on["outcomes"]["contraction_crossing_into_tolerance"],
                         "every pre-P range was already within 0.41")
        post_off = {m: v for m, v in zip(self.models, (0.0, float(np.nextafter(0.41, 1)), 0.2))}
        self.assertFalse(h4_dispersion(self.spec, self.result(pre, post_off))[
            "outcomes"]["final_within_tolerance"])

    def test_one_unusable_fit_makes_the_contrast_not_computable(self):
        pre = {(m, p): 0.1 for m in self.models for p in self.prompts}
        post = {m: 0.1 for m in self.models}
        failed = {f"va_sp::{self.models[0]}"}
        result = h4_dispersion(self.spec, self.result(pre, post, failed))
        self.assertEqual(result["status"], NOT_COMPUTABLE)
        self.assertNotIn("D_pre", result)
        self.assertEqual(result["fits"][f"va_sp::{self.models[0]}"]["status"], FAILED)
        self.assertEqual(result["n_fits_required"], 12)


class E1Tests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)
        rows = fx.make_item_rows(8)
        rows[0]["lgoal"] = "nan"  # SYN1, a positive, is in B but not in R
        # VA is right everywhere except on SYN1, where every label is 0 (wrong).
        cls.data = fx.build_input(cls.spec, item_rows=rows,
                                  label_of=lambda k: 0 if k.item_id == "SYN1" else
                                  int(k.item_id[3:]) % 2 if k.template_id.startswith("cm_") else 0)
        cls.vectors = build_vectors(cls.data, cls.registry)
        b = sample_b(cls.data)
        cls.b_members = b.members
        cls.r_members = sample_r(cls.data, b, cls.registry, cls.vectors).members

    def downstream(self, human=USABLE):
        fits = {"HUMAN": fit("HUMAN", human, 0.5)}
        for i, p in enumerate(self.registry.primary):
            status = FAILED if p.procedure_id == "cb::sonnet_5::cb_t3_rot" else USABLE
            fits[p.procedure_id] = fit(p.procedure_id, status, 0.5 + 0.01 * (i % 3))
        return DownstreamResult(None, fits, {})

    def test_both_axes_use_r_and_unavailable_distances_are_listed(self):
        self.assertNotIn("SYN1", self.r_members)
        result = e1_points(self.data, self.registry, self.vectors, self.r_members,
                           self.downstream())
        self.assertEqual(result["sample"], "R")
        g = next(p for p in result["points"] if p["procedure_id"] == "va_g::s_p_m")
        on_r = score_vector(self.vectors["va_g::s_p_m"], self.data, self.r_members, "R").ba
        on_b = score_vector(self.vectors["va_g::s_p_m"], self.data, self.b_members, "B").ba
        self.assertEqual(Fraction(g["ba_R"]["exact"]), on_r)
        self.assertNotEqual(on_r, on_b, "SYN1 makes BA on B differ from BA on R")
        self.assertEqual([u["procedure_id"] for u in result["unavailable"]],
                         ["cb::sonnet_5::cb_t3_rot"])
        self.assertEqual(len(result["points"]) + len(result["unavailable"]), 31)

    def test_coincident_points_keep_every_identity(self):
        result = e1_points(self.data, self.registry, self.vectors, self.r_members,
                           self.downstream())
        shared = [ids for ids in result["coincident_points"] if len(ids) > 1]
        self.assertTrue(shared)
        self.assertEqual(sum(len(ids) for ids in result["coincident_points"]),
                         len({i for ids in result["coincident_points"] for i in ids}))

    def test_a_human_failure_empties_the_plot_and_lists_everything(self):
        result = e1_points(self.data, self.registry, self.vectors, self.r_members,
                           self.downstream(human=FAILED))
        self.assertEqual(result["points"], [])
        self.assertEqual(len(result["unavailable"]), 31)
        self.assertTrue(all(u["reason"] == "HUMAN fit failed" for u in result["unavailable"]))

    def test_the_plot_is_written_only_where_asked_and_says_synthetic(self):
        root = Path(tempfile.mkdtemp(prefix="synthetic_e1_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        result = e1_points(self.data, self.registry, self.vectors, self.r_members,
                           self.downstream())
        path = plot_e1(result, root / "e1.png")
        self.assertTrue(path.is_file() and path.stat().st_size > 0)
        self.assertEqual(result["data_kind"], "synthetic")
