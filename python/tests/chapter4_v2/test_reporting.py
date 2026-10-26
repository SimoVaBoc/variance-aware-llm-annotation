"""Report arrangement: analysis-ID labels, output tiers, pending table, synthetic example."""

import importlib.util
import json
import re
import shutil
import tempfile
from pathlib import Path

from _guard import PROJECT_ROOT, SyntheticTestCase

from src.chapter3.chapter4_v2.aggregation import build_vectors
from src.chapter3.chapter4_v2.annotation_framework import evaluate_annotation_framework
from src.chapter3.chapter4_v2.decisions import load_register
from src.chapter3.chapter4_v2.h1 import h1_variation
from src.chapter3.chapter4_v2.h2 import h2_core
from src.chapter3.chapter4_v2.h3 import h3_point_contrast
from src.chapter3.chapter4_v2.procedures import build_registry
from src.chapter3.chapter4_v2.reporting import (
    ANALYSIS_IDS,
    CATALOGUE,
    TIERS,
    build_report,
    pending_status_table,
)
from src.chapter3.chapter4_v2.samples import sample_b, sample_i27
from src.chapter3.chapter4_v2.spec import load_spec
from src.chapter3.chapter4_v2.synthetic import build_synthetic_input

SECTION_NUMBER = re.compile(r"(?<![\d.§])4\.\d")


def load_example():
    spec = importlib.util.spec_from_file_location(
        "chapter4_v2_synthetic_example", PROJECT_ROOT / "python/scripts/chapter4_v2_synthetic_example.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogueTests(SyntheticTestCase):
    def test_every_output_has_a_tier_and_only_analysis_id_labels(self):
        ids = [c[0] for c in CATALOGUE]
        self.assertEqual(len(ids), len(set(ids)))
        for output_id, analysis_ids, tier, basis in CATALOGUE:
            self.assertIn(tier, TIERS, output_id)
            self.assertTrue(analysis_ids, output_id)
            self.assertTrue(set(analysis_ids) <= set(ANALYSIS_IDS), output_id)
            self.assertIsNone(SECTION_NUMBER.search(output_id), output_id)
            self.assertTrue(basis.startswith(("SRC-", "proposed")), output_id)

    def test_brief_section_10_placements(self):
        tier = {c[0]: c[2] for c in CATALOGUE}
        for main in ("samples_and_coverage", "performance_profiles_B", "g_margins",
                     "downstream_summary", "h1_cells", "h2_main_table", "h3_point_contrast",
                     "h4_dispersion", "e1_points", "evidence_to_framework_table",
                     "pending_status_table"):
            self.assertEqual(tier[main], "main", main)
        for appendix in ("pairwise_465", "directional_corrections", "downstream_full_fits",
                         "leave_one_out_perturbations", "bootstrap_draws"):
            self.assertEqual(tier[appendix], "appendix", appendix)

    def test_pending_table_reads_the_register(self):
        rows = pending_status_table(load_spec(), load_register())
        decisions = {r["decision_id"]: r for r in rows}
        for decision_id in ("D-H3-02", "D-H2-02", "D-H2-03", "D-H2-04", "D-H2-05", "D-FIRTH-03"):
            self.assertIn(decision_id, decisions)
        register = {d["id"]: d for d in load_register()["decisions"]}
        for row in rows:
            self.assertEqual(row["decision_status"], register[row["decision_id"]]["status"])


class ReportTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        data = build_synthetic_input(cls.spec, n_items=24, seed=3)
        registry = build_registry(cls.spec)
        vectors = build_vectors(data, registry)
        b = sample_b(data)
        cls.report = build_report(
            cls.spec, load_register(), data,
            evaluate_annotation_framework(cls.spec, data, run_bootstrap=False),
            h1_variation(data), h2_core(cls.spec, data),
            h3_point_contrast(data, registry, vectors, b, sample_i27(data, b)),
            downstream=None, downstream_reason="downstream evidence not supplied")

    def test_every_catalogue_entry_is_present_labelled_and_synthetic(self):
        outputs = {o["output_id"]: o for o in self.report["outputs"]}
        self.assertEqual(set(outputs), {c[0] for c in CATALOGUE})
        self.assertTrue(all(o["data_kind"] == "synthetic" for o in outputs.values()))
        self.assertEqual(self.report["header"]["data_kind"], "synthetic")
        json.dumps(self.report)  # serialisable as is

    def test_missing_downstream_is_marked_never_zero(self):
        outputs = {o["output_id"]: o for o in self.report["outputs"]}
        for output_id in ("downstream_summary", "downstream_full_fits", "h4_dispersion", "e1_points"):
            self.assertEqual(outputs[output_id]["content"],
                             {"status": "not_run", "reason": "downstream evidence not supplied"})
        self.assertEqual(outputs["bootstrap_draws"]["content"]["status"], "not_run")

    def test_pending_table_and_proposed_rules_are_visible(self):
        self.assertEqual(len(self.report["pending_status_table"]), 6)
        proposed = {p["decision_id"] for p in self.report["proposed_working_rules"]}
        for decision_id in ("D-FW-04", "D-FIRTH-05", "D-REG-03", "D-CH4-STRUCT"):
            self.assertIn(decision_id, proposed)

    def test_no_label_uses_a_section_number(self):
        for output in self.report["outputs"]:
            self.assertIsNone(SECTION_NUMBER.search(output["output_id"]))
            for analysis_id in output["analysis_ids"]:
                self.assertIn(analysis_id, ANALYSIS_IDS)


class ExampleScriptTests(SyntheticTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="synthetic_example_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_the_example_runs_end_to_end_and_labels_everything_synthetic(self):
        example = load_example()
        report = example.run(self.root / "out", use_r=False, n_items=24, seed=2, bootstrap=False)
        written = json.loads((self.root / "out/chapter4_v2_synthetic_report.json").read_text(
            encoding="utf-8"))
        self.assertEqual(written["data_kind"], "synthetic")
        self.assertEqual(len(written["outputs"]), len(CATALOGUE))
        summary = (self.root / "out/README_SYNTHETIC.md").read_text(encoding="utf-8")
        self.assertTrue(summary.startswith("# SYNTHETIC"))
        self.assertIn("D-FIRTH-03", summary)
        self.assertEqual(report["data_kind"], "synthetic")

    def test_the_example_never_overwrites_or_writes_into_private_trees(self):
        example = load_example()
        (self.root / "exists").mkdir()
        with self.assertRaises(FileExistsError):
            example.run(self.root / "exists", use_r=False, n_items=12, bootstrap=False)
        with self.assertRaises(ValueError):
            example.run(self.root / "runs" / "out", use_r=False, n_items=12, bootstrap=False)
