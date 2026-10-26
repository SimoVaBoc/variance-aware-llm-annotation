"""Common design on R, pre-fit checks, SVD rank and the separation LP. No R, no fits."""

import ast
from pathlib import Path

import numpy as np

from _guard import PROJECT_ROOT, SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.downstream import (
    REASON_LABEL_CONSTANT,
    REASON_N_NOT_ABOVE_P,
    REASON_OUTCOME_ONE_CLASS,
    REASON_RANK_DEFICIENT,
    DesignError,
    build_common_design,
    label_set,
    prefit_checks,
    rank_check,
    separation_diagnostic,
)
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.samples import sample_b, sample_r
from src.chapter3.chapter4_v2.spec import load_spec

PACKAGE = PROJECT_ROOT / "python/src/chapter3/chapter4_v2"


def rows_with(n, **columns):
    rows = fx.make_item_rows(n)
    for name, values in columns.items():
        for row, value in zip(rows, values):
            row[name] = str(value)
    return rows


class DesignTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def design_for(self, rows):
        data = fx.build_input(self.spec, item_rows=rows)
        vectors = build_vectors(data, self.registry)
        r = sample_r(data, sample_b(data), self.registry, vectors)
        return data, vectors, r, build_common_design(data, r.members)

    def test_columns_levels_and_references_are_fixed_by_r(self):
        subs = ["beta", "Gamma", "alpha", "beta", "alpha", "Gamma", "beta", "alpha"]
        years = ["2012", "2010", "2011", "2010", "2012", "2011", "2010", "2012"]
        _, _, _, design = self.design_for(rows_with(8, subcategory=subs, year=years))
        # Sorted as strings (code point order): upper case first.
        self.assertEqual(design.levels["subcategory"], ("Gamma", "alpha", "beta"))
        self.assertEqual(design.levels["year"], ("2010", "2011", "2012"))
        self.assertEqual(design.column_names,
                         ("(Intercept)", "LABEL", "lgoal", "subcategory[alpha]",
                          "subcategory[beta]", "year[2011]", "year[2012]"))
        self.assertEqual(design.describe()["reference_levels"],
                         {"subcategory": "Gamma", "year": "2010"})

    def test_lgoal_is_used_as_supplied_and_controls_are_shared(self):
        rows = rows_with(6, lgoal=["9.125", "10.5", "8", "7.75", "11.25", "9"])
        data, _, _, design = self.design_for(rows)
        self.assertEqual(design.controls[:, 0].tolist(),
                         [data.items[i].lgoal for i in design.items])
        self.assertEqual(design.controls[:, 0].tolist(), [9.125, 10.5, 8.0, 7.75, 11.25, 9.0])
        a = design.matrix(np.zeros(design.n))
        b = design.matrix(np.ones(design.n))
        self.assertTrue(np.array_equal(a[:, 2:], b[:, 2:]), "only LABEL changes between fits")
        self.assertTrue((a[:, 0] == 1).all())

    def test_an_empty_r_or_an_unusable_item_is_refused(self):
        data, _, _, _ = self.design_for(fx.make_item_rows(4))
        with self.assertRaises(DesignError):
            build_common_design(data, [])
        rows = fx.make_item_rows(4)
        rows[0]["lgoal"] = "inf"
        data = fx.build_input(self.spec, item_rows=rows)
        with self.assertRaises(DesignError):
            build_common_design(data, ["SYN1", "SYN2"])

    def test_labels_missing_on_r_are_refused(self):
        data, vectors, r, design = self.design_for(fx.make_item_rows(6))
        labels = label_set(design, data, vectors, ["va_g::s_p_m"])
        self.assertEqual(labels.names, ["HUMAN", "va_g::s_p_m"])
        from src.chapter3.chapter4_v2.aggregation import LabelVector
        broken = dict(vectors)
        broken["va_g::s_p_m"] = LabelVector("va_g::s_p_m", "g", {i: None for i in data.items},
                                            {i: "g_outside_i27" for i in data.items})
        with self.assertRaises(DesignError):
            label_set(design, data, broken, ["va_g::s_p_m"])


class PrefitTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.registry = build_registry(cls.spec)

    def design(self, rows):
        data = fx.build_input(self.spec, item_rows=rows)
        vectors = build_vectors(data, self.registry)
        r = sample_r(data, sample_b(data), self.registry, vectors)
        return data, build_common_design(data, r.members)

    def test_each_refusal_reason(self):
        # The fixture's lgoal is linear in the item index and its subcategory follows
        # i mod 3, so regular years or lgoal values can make the design singular (the
        # rank check catches it). These values are irregular on purpose.
        years = [2010, 2011, 2012, 2012, 2011, 2010, 2011, 2010, 2010, 2012]
        lgoal = [9.1, 7.4, 10.8, 8.2, 9.9, 7.7, 11.3, 8.8, 10.1, 9.6]
        data, design = self.design(rows_with(10, year=years, lgoal=lgoal))
        human = np.array([data.items[i].human for i in design.items])
        self.assertTrue(prefit_checks(design, human)["estimable"])
        self.assertIn(REASON_LABEL_CONSTANT, prefit_checks(design, np.ones(design.n))["failures"])
        data, design = self.design(rows_with(10, year=years, lgoal=lgoal, success=[1] * 10))
        self.assertIn(REASON_OUTCOME_ONE_CLASS, prefit_checks(design, human)["failures"])
        data, design = self.design(rows_with(5, year=[2010, 2011, 2012, 2010, 2011]))
        human = np.array([data.items[i].human for i in design.items])
        self.assertIn(REASON_N_NOT_ABOVE_P, prefit_checks(design, human)["failures"])

    def test_a_label_collinear_with_a_control_is_rank_deficient(self):
        # In the default fixture HUMAN equals the year dummy exactly.
        data, design = self.design(fx.make_item_rows(10))
        human = np.array([data.items[i].human for i in design.items])
        result = prefit_checks(design, human)
        self.assertIn(REASON_RANK_DEFICIENT, result["failures"])
        self.assertEqual(result["rank"]["rank"], design.p - 1)

    def test_rank_tolerance_is_max_n_p_eps_smax(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=(20, 4))
        check = rank_check(x)
        s = np.linalg.svd(x, compute_uv=False)
        self.assertEqual(check["tolerance"], 20 * np.finfo(float).eps * s.max())
        self.assertTrue(check["full_rank"])
        nearly = x.copy()
        nearly[:, 3] = nearly[:, 2] + 1e-17 * rng.normal(size=20)
        self.assertFalse(rank_check(nearly)["full_rank"])


class SeparationTests(SyntheticTestCase):
    def design(self, label, y, seed=1):
        rng = np.random.default_rng(seed)
        return np.column_stack([np.ones(len(y)), label, rng.normal(size=len(y))]), np.asarray(y)

    def test_complete_separation_and_its_direction(self):
        label = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        x, y = self.design(label, label)
        result = separation_diagnostic(x, y)
        self.assertEqual(result["separation"], "complete")
        self.assertIn(1, result["diverging_columns"])

    def test_quasi_complete_separation(self):
        label = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        y = np.array([0, 1, 0, 1, 1, 1, 1, 1])
        x = np.column_stack([np.ones(8), label])
        self.assertEqual(separation_diagnostic(x, y)["separation"], "quasi_complete")

    def test_overlap_is_not_separation(self):
        label = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        y = np.array([0, 1, 0, 1, 1, 0, 1, 0])
        x = np.column_stack([np.ones(8), label])
        result = separation_diagnostic(x, y)
        self.assertEqual(result["separation"], "none")
        self.assertEqual(result["diverging_columns"], [])


class NoPythonEstimatorTests(SyntheticTestCase):
    def test_no_module_of_the_new_package_imports_an_estimation_library(self):
        forbidden = {"statsmodels", "sklearn", "firthlogist", "glum"}
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotIn(name.split(".")[0], forbidden, f"{path.name} imports {name}")
