"""The review allowlist: complete for the new code, closed to private material."""

import importlib.util
import json

from _guard import PROJECT_ROOT, SyntheticTestCase

ALLOWLIST = PROJECT_ROOT / "docs/chapter4_v2/review_export_allowlist.json"
IN_EXPORT = (PROJECT_ROOT / "EXPORT_MANIFEST.json").is_file()
REDACTED_ROOT = "docs/chapter4_v2/export/redacted/"
LEGACY_CLOSURE = ["python/src/__init__.py", "python/src/chapter3/__init__.py"] + [
    f"python/src/chapter3/{m}.py" for m in ("aggregation", "analysis", "bootstrap", "catalog",
                                            "design", "execution", "first_party", "hierarchy",
                                            "huggingface", "metrics", "providers", "results")]
# D-EXPORT-01: the Chapter 3 tests that run without data/ and runs/, and their helper.
CHAPTER3_TESTS = [f"python/tests/chapter3/{m}.py" for m in (
    "test_catalog", "test_hierarchy", "test_results", "test_providers", "test_manifest",
    "test_runner_row_settings", "_fakes")]
# D-EXPORT-03: the starting inputs, and nothing else under data/.
STARTING_DATA = ["data/test_sample.csv", "data/prompt_variations.csv",
                 "data/prompt_creation_template.txt"]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / f"python/scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tool():
    return load_script("chapter4_v2_build_review_export")


class AllowlistTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads(ALLOWLIST.read_text(encoding="utf-8"))["entries"]
        cls.dests = {e["dest"] for e in cls.entries}
        cls.redaction = load_script("chapter4_v2_redact_for_review")

    def test_every_new_file_and_the_import_closure_are_listed(self):
        new = [p for base in ("python/src/chapter3/chapter4_v2", "python/tests/chapter4_v2")
               for p in (PROJECT_ROOT / base).rglob("*")
               if p.is_file() and "__pycache__" not in p.parts]
        new += list((PROJECT_ROOT / "python/scripts").glob("chapter4_v2_*.py"))
        for path in new:
            self.assertIn(path.relative_to(PROJECT_ROOT).as_posix(), self.dests)
        for path in LEGACY_CLOSURE:
            self.assertIn(path, self.dests)
        for path in ("README.md", "LICENSE", "requirements-review.txt", ".gitignore",
                     "docs/chapter4_v2/reviewer_guide.md",
                     "config/analysis/chapter4_analysis_spec_v2.json"):
            self.assertIn(path, self.dests)

    def test_nothing_private_or_historical_is_listed(self):
        tool = load_tool()
        for e in self.entries:
            self.assertEqual(tool.check_entry(e["source"], e["dest"]), [], e)
        names = {e["source"].rsplit("/", 1)[-1] for e in self.entries}
        for forbidden in ("AI_disclosure.md", "CLAUDE.md", "local_paths.json", "regression.py"):
            self.assertNotIn(forbidden, names)
        self.assertFalse([e for e in self.entries if e["source"].startswith(
            ("runs/", "docs/chapter3", "docs/sources/", "config/execution/"))])

    def test_only_the_selected_chapter3_tests_are_listed(self):
        listed = sorted(e["source"] for e in self.entries
                        if e["source"].startswith("python/tests/chapter3/"))
        self.assertEqual(listed, sorted(CHAPTER3_TESTS))
        for e in self.entries:
            if e["source"].startswith("python/tests/chapter3/"):
                self.assertEqual(e["dest"], e["source"])

    def test_only_the_starting_data_are_listed_under_data(self):
        under_data = sorted(e["source"] for e in self.entries
                            if e["source"].startswith("data/") or e["dest"].startswith("data/"))
        self.assertEqual(under_data, sorted(STARTING_DATA))
        self.assertEqual(sorted(load_tool().STARTING_DATA), sorted(STARTING_DATA))
        for e in self.entries:
            if e["source"] in STARTING_DATA:
                self.assertEqual(e["dest"], e["source"])

    def test_observation_files_enter_only_as_redacted_copies(self):
        sources = {e["source"] for e in self.entries}
        originals = set(self.redaction.ORIGINALS)
        self.assertEqual(len(originals), 21)
        self.assertEqual(sources & (originals | set(self.redaction.NOT_REDACTABLE)), set())
        by_dest = {e["dest"]: e["source"] for e in self.entries}
        for original in originals:
            self.assertEqual(by_dest.get(original), REDACTED_ROOT + original)
        for excluded in self.redaction.NOT_REDACTABLE:
            self.assertNotIn(excluded, self.dests)

    def test_every_redacted_copy_says_what_was_removed(self):
        for original in self.redaction.ORIGINALS:
            path = PROJECT_ROOT / (original if IN_EXPORT else REDACTED_ROOT + original)
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=original):
                if original.endswith(".json"):
                    record = json.loads(text)["review_redaction"]
                    self.assertEqual(record["derived_from"], original)
                    self.assertEqual(record["original_sha256"], self.redaction.ORIGINALS[original])
                    self.assertIn("removed", record)
                else:
                    self.assertIn("REVIEW REDACTION (decision D-EXPORT-03)", text.splitlines()[1])

    def test_the_redacted_copies_are_current(self):
        if IN_EXPORT:
            self.skipTest("the frozen originals are not part of the review package")
        copies = self.redaction.build()
        for original, text in copies.items():
            with self.subTest(file=original):
                self.assertEqual((PROJECT_ROOT / REDACTED_ROOT / original).read_text(encoding="utf-8"),
                                 text)

    def test_the_refusal_rules(self):
        tool = load_tool()
        for bad in ("data/x.csv", "data/README.md", "runs/raw/a.txt", "../outside.py",
                    "/abs/path.py", "AI_disclosure.md", "x/local_paths.json",
                    "a/__pycache__/m.pyc", "z.zip"):
            self.assertTrue(tool.check_entry(bad, "ok.txt"), bad)
        self.assertEqual(tool.check_entry("data/test_sample.csv", "data/test_sample.csv"), [])
        self.assertTrue(tool.check_entry("data/test_sample.csv", "elsewhere/test_sample.csv"))
        self.assertTrue(tool.check_entry("ok.txt", "data/test_sample.csv"))
        for original in list(self.redaction.ORIGINALS) + list(self.redaction.NOT_REDACTABLE):
            self.assertTrue(tool.check_entry(original, original), original)

    def test_sources_or_exported_files_exist(self):
        # Existence is checked with stat only; no file under data/ is opened.
        if IN_EXPORT:
            for dest in self.dests:
                self.assertTrue((PROJECT_ROOT / dest).is_file(), dest)
        else:
            for e in self.entries:
                self.assertTrue((PROJECT_ROOT / e["source"]).is_file(), e["source"])
