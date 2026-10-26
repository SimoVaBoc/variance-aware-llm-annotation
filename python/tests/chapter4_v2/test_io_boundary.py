"""The I/O boundary: explicit root, relative paths only, strict logs, no empirical default."""

import json
import shutil
import tempfile
from pathlib import Path

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.inputs import SLOT_VALID, InputIntegrityError
from src.chapter3.chapter4_v2.io_boundary import (
    BoundaryError,
    EmpiricalInputNotAuthorised,
    load_task_level_input,
    resolve,
)
from src.chapter3.chapter4_v2.spec import load_spec


class BoundaryTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="synthetic_boundary_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_synthetic_tree_loads_end_to_end_with_input_hashes(self):
        binding = fx.write_tree(self.root, self.spec, n_items=5)
        data = load_task_level_input(self.spec, self.root, binding)
        self.assertEqual(data.data_kind, "synthetic")
        self.assertEqual(len(data.items), 5)
        self.assertTrue(all(s.state == SLOT_VALID for s in data.slots.values()))
        files = data.provenance["input_files_sha256"]
        self.assertIn("data/items.csv", files)
        self.assertEqual(len(files), 1 + 2 * 3)

    def test_campaign_text_is_not_carried_into_the_input(self):
        binding = fx.write_tree(self.root, self.spec, n_items=3)
        data = load_task_level_input(self.spec, self.root, binding)
        self.assertNotIn("placeholder campaign", repr(data))

    def test_an_empirical_binding_is_refused_without_explicit_authorisation(self):
        binding = fx.write_tree(self.root, self.spec, n_items=3, data_kind="empirical")
        with self.assertRaises(EmpiricalInputNotAuthorised):
            load_task_level_input(self.spec, self.root, binding)

    def test_paths_must_stay_inside_the_root(self):
        fx.write_tree(self.root, self.spec, n_items=2)
        for bad in ("../outside.csv", "/abs/items.csv", "C:/x.csv", "data\\items.csv", ""):
            with self.assertRaises(BoundaryError, msg=bad):
                resolve(self.root, bad)
        with self.assertRaises(BoundaryError):
            resolve(self.root, "data/no_such_file.csv")
        self.assertTrue(resolve(self.root, "data/items.csv").is_file())

    def test_an_explicit_root_is_required(self):
        binding = fx.write_tree(self.root, self.spec, n_items=2)
        with self.assertRaises(BoundaryError):
            load_task_level_input(self.spec, "", binding)

    def test_a_malformed_log_line_is_an_integrity_error_not_a_skipped_line(self):
        binding = fx.write_tree(self.root, self.spec, n_items=2)
        log = self.root / "runs/raw/sonnet_5.jsonl"
        log.write_text(log.read_text(encoding="utf-8") + '{"task_id": "trunc', encoding="utf-8")
        with self.assertRaises(InputIntegrityError) as caught:
            load_task_level_input(self.spec, self.root, binding)
        self.assertIn("not valid JSON", caught.exception.problems[0])

    def test_a_binding_must_declare_its_data_kind(self):
        binding = fx.write_tree(self.root, self.spec, n_items=2)
        content = json.loads(binding.read_text(encoding="utf-8"))
        content.pop("data_kind")
        binding.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaises(BoundaryError):
            load_task_level_input(self.spec, self.root, binding)
