"""Provenance: plan identity, code state that admits uncommitted files, and a data label."""

import shutil
import tempfile
from pathlib import Path

from _guard import SyntheticTestCase

from src.chapter3.chapter4_v2.provenance import UNAVAILABLE, code_state, output_header
from src.chapter3.chapter4_v2.spec import load_spec


class ProvenanceTests(SyntheticTestCase):
    def test_header_names_spec_code_software_and_data_kind(self):
        header = output_header(load_spec(), synthetic=True)
        for key in ("spec_id", "spec_version", "spec_sha256", "code_commit",
                    "working_tree_modified", "software", "created_utc"):
            self.assertIn(key, header)
        self.assertEqual(header["data_kind"], "synthetic")
        self.assertIn("python", header["software"])

    def test_the_data_kind_must_be_stated(self):
        with self.assertRaises(TypeError):
            output_header(load_spec())  # type: ignore[call-arg]

    def test_outside_a_repository_the_commit_is_reported_unavailable(self):
        root = Path(tempfile.mkdtemp(prefix="synthetic_norepo_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        state = code_state(root)
        self.assertEqual(state["code_commit"], UNAVAILABLE)
        self.assertIsNone(state["working_tree_modified"])
