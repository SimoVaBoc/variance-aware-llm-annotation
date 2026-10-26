"""The preservation tool on synthetic trees: exact copies, no overwrite, no deletion."""

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
from pathlib import Path

from _guard import PROJECT_ROOT, SyntheticTestCase

_SPEC = importlib.util.spec_from_file_location(
    "chapter4_v2_preserve_private",
    PROJECT_ROOT / "python/scripts/chapter4_v2_preserve_private.py")
preserve = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(preserve)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = preserve.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class PreserveTests(SyntheticTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="synthetic_preserve_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / "source"
        (self.source / "alpha" / "nested").mkdir(parents=True)
        (self.source / "beta").mkdir()
        (self.source / "alpha" / "one.bin").write_bytes(b"\x00\x01synthetic")
        (self.source / "alpha" / "nested" / "two.txt").write_bytes(b"line\r\nline\n")
        (self.source / "beta" / "three.txt").write_bytes(b"")
        self.target = self.tmp / "private_target"

    def copy(self):
        return run("copy", "--source-root", str(self.source), "--target-root",
                   str(self.target), "--subtree", "alpha", "--subtree", "beta")

    def test_copy_is_byte_identical_and_originals_remain(self):
        code, out, _ = self.copy()
        self.assertEqual(code, 0)
        summary = json.loads(out)
        self.assertEqual(summary["n_files"], 3)
        self.assertEqual(summary["verification"]["copy_matches_source"]["n_different"], 0)
        for rel in ("alpha/one.bin", "alpha/nested/two.txt", "beta/three.txt"):
            self.assertEqual((self.source / rel).read_bytes(), (self.target / rel).read_bytes())
        manifests = list((self.target / "preservation").glob("PRESERVATION_MANIFEST_*.json"))
        self.assertEqual(len(manifests), 1)
        self.assertFalse(json.loads(manifests[0].read_text())["originals_deleted"])

    def test_existing_target_is_never_overwritten(self):
        self.assertEqual(self.copy()[0], 0)
        code, _, err = self.copy()
        self.assertEqual(code, 2)
        self.assertIn("refusing to overwrite", err)

    def test_target_inside_source_is_refused(self):
        code, _, err = run("copy", "--source-root", str(self.source), "--target-root",
                           str(self.source / "inner"), "--subtree", "alpha")
        self.assertEqual(code, 2)
        self.assertIn("outside the source tree", err)

    def test_verify_detects_a_changed_byte(self):
        self.copy()
        inventory = next((self.target / "preservation").glob("*.tsv"))
        self.assertEqual(run("verify", "--root", str(self.target), "--inventory",
                             str(inventory))[0], 0)
        (self.target / "alpha" / "one.bin").write_bytes(b"\x00\x01synthetiC")
        code, out, _ = run("verify", "--root", str(self.target), "--inventory", str(inventory))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["n_different"], 1)

    def test_output_never_names_files(self):
        _, out, _ = self.copy()
        self.assertNotIn("one.bin", out)
        self.assertNotIn("three.txt", out)
