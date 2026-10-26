"""The R logistf adapter on synthetic designs. Skipped, never passed, without R + logistf 1.26.1.

One R process serves the whole class. The fits use exactly the specified
controls. On these designs those controls do not certify convergence (see
D-FIRTH-03); the tests record that behaviour instead of working around it.
"""

import random
import unittest

import numpy as np

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.downstream import LabelSet, build_common_design
from src.chapter3.chapter4_v2.firth import (
    FAILED,
    HUMAN,
    NOT_ESTIMABLE,
    find_rscript,
    r_environment,
    run_adapter,
    run_downstream,
)
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b, sample_r
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.thresholds import NOT_EVALUABLE

SPEC = load_spec()
REQUIRED = SPEC.data["downstream"]["estimator"]["required_version"]
ENVIRONMENT = r_environment(find_rscript())
R_READY = ENVIRONMENT["available"] and ENVIRONMENT.get("logistf_version") == REQUIRED
SKIP_REASON = f"R with logistf {REQUIRED} not available: {ENVIRONMENT.get('reason')}"


def synthetic_design(n=40, seed=11):
    rng = random.Random(seed)
    rows = fx.make_item_rows(n)
    for row in rows:
        row["success"] = "1" if rng.random() < 0.45 else "0"
        row["year"] = str(rng.choice([2010, 2011, 2012]))
        row["lgoal"] = f"{rng.uniform(7, 12):.6f}"
    data = fx.build_input(SPEC, item_rows=rows)
    registry = build_registry(SPEC)
    vectors = build_vectors(data, registry)
    r = sample_r(data, sample_b(data), registry, vectors)
    return data, build_common_design(data, r.members)


@unittest.skipUnless(R_READY, SKIP_REASON)
class FirthAdapterTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.design = synthetic_design()
        human = np.array([cls.data.items[i].human for i in cls.design.items])
        cls.labels = LabelSet(
            names=[HUMAN, "separated", "constant"],
            values={HUMAN: human, "separated": cls.design.y.copy(),
                    "constant": np.ones(cls.design.n, dtype=np.int64)})
        cls.result = run_downstream(SPEC, cls.design, cls.labels)
        cls.raw = run_adapter(SPEC, cls.design, [(HUMAN, human)], find_rscript())["fits"][0]

    def test_reference_package_versions_are_recorded(self):
        self.assertEqual(self.result.environment["logistf_version"], REQUIRED)
        self.assertTrue(self.result.environment["r_version"].startswith("R version"))
        session = self.result.environment["session"]
        self.assertTrue(session["logistf_built"].startswith("R "), "the build R version is kept")
        deps = session["installed_dependency_versions"]
        self.assertEqual(deps["logistf"], REQUIRED)
        for name in ("mice", "formula.tools", "Matrix", "jsonlite"):
            self.assertIn(name, deps)
        self.assertIn("logistf", session["loaded_package_versions"])

    def test_the_specified_options_reach_logistf_unchanged(self):
        control = SPEC.data["downstream"]["estimator"]["control"]
        echo = self.raw["control_echo"]
        self.assertEqual((echo["maxit"], echo["maxhs"], echo["maxstep"]),
                         (control["maxit"], control["maxhs"], control["maxstep"]))
        for key in ("lconv", "gconv", "xconv"):
            self.assertEqual(float(echo[key]), float(control[key]))
        self.assertEqual((echo["collapse"], echo["fit"]), (False, "NR"))
        self.assertEqual((self.raw["firth"], self.raw["flic"]), (True, False))
        self.assertEqual(self.raw["method"], "Penalized ML")
        # Reported per coefficient; only LABEL (second) has a profile interval.
        self.assertEqual(self.raw["method_ci"][1], "Profile Likelihood")

    def test_the_design_is_used_exactly_and_no_row_is_dropped(self):
        self.assertTrue(self.raw["design_identical"])
        self.assertEqual(self.raw["n"], self.design.n)
        self.assertEqual(self.raw["coefficient_names"], list(self.design.column_names))

    def test_specified_controls_do_not_certify_convergence_here(self):
        # D-FIRTH-03: with maxhs = 25 the fit runs to maxit without meeting gconv/xconv.
        human = self.result.fits[HUMAN]
        self.assertEqual(human.status, FAILED)
        self.assertTrue(all(r.startswith("convergence not certified") for r in human.reasons))
        self.assertEqual(human.convergence["iterations"]["full"],
                         SPEC.data["downstream"]["estimator"]["control"]["maxit"])
        self.assertIsNotNone(human.coefficient, "the point is reported, flagged, never hidden")

    def test_a_separated_but_identified_design_is_fitted_and_recorded(self):
        separated = self.result.fits["separated"]
        self.assertEqual(separated.separation["separation"], "complete")
        self.assertIn(1, separated.separation["diverging_columns"])
        self.assertTrue(np.isfinite(separated.coefficient))

    def test_a_constant_label_never_reaches_r(self):
        constant = self.result.fits["constant"]
        self.assertEqual(constant.status, NOT_ESTIMABLE)
        # A column of ones also duplicates the intercept, so the rank check fires too.
        self.assertEqual(constant.reasons, ["label_has_no_variation", "design_not_full_rank"])
        self.assertIsNone(constant.coefficient)

    def test_a_human_failure_propagates_to_every_distance(self):
        proximity = self.result.proximity(SPEC, ["separated", "constant"])
        self.assertTrue(all(c.status == NOT_EVALUABLE for c in proximity.values()))
        self.assertTrue(all("HUMAN fit not usable" in c.reason for c in proximity.values()))

    def test_coefficients_arrive_bit_for_bit(self):
        raw_hex = self.raw["coefficients_hex"][1]
        self.assertEqual(self.result.fits[HUMAN].coefficient, float.fromhex(raw_hex))
        self.assertEqual(self.result.fits[HUMAN].coefficient.hex(),
                         float.fromhex(raw_hex).hex())
