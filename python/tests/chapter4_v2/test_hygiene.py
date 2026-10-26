"""Repository hygiene for the files meant for review: no local paths, no local config."""

import os
import re
import subprocess
from pathlib import Path

from _guard import PROJECT_ROOT, SyntheticTestCase

def _review_files() -> list[Path]:
    """Every text file of the review package: allowlist sources here, destinations in an export.

    The starting data under ``data/`` (D-EXPORT-03) are left out: the guard forbids opening
    them, and they are checked by their pinned SHA-256 in the export builder instead.
    """

    import json
    entries = json.loads((PROJECT_ROOT / "docs/chapter4_v2/review_export_allowlist.json")
                         .read_text(encoding="utf-8"))["entries"]
    key = "dest" if (PROJECT_ROOT / "EXPORT_MANIFEST.json").is_file() else "source"
    return sorted(PROJECT_ROOT / e[key] for e in entries if not e["dest"].startswith("data/"))


REVIEW_FILES = _review_files()

#: An absolute Windows user-profile path, or this machine's user name, would leak a
#: local identity into the review package. Built from parts so this file itself is clean.
USER_PATH = re.compile(r"[A-Za-z]:[\\/]+" + "Users" + r"[\\/]", re.IGNORECASE)


class HygieneTests(SyntheticTestCase):
    def test_review_files_carry_no_absolute_user_path(self):
        home = Path.home().name.lower()
        self.assertTrue(REVIEW_FILES)
        for path in REVIEW_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(PROJECT_ROOT).as_posix()):
                self.assertIsNone(USER_PATH.search(text))
                if len(home) >= 4:
                    self.assertNotIn(home, text.lower())

    def test_the_local_r_path_config_is_never_tracked(self):
        listed = subprocess.run(["git", "ls-files", "--", "local_paths.json"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=30)
        if listed.returncode != 0:
            self.skipTest("git not available")
        self.assertEqual(listed.stdout.strip(), "")
        if (PROJECT_ROOT / "local_paths.json").exists():
            ignored = subprocess.run(["git", "check-ignore", "-q", "local_paths.json"],
                                     cwd=PROJECT_ROOT, timeout=30)
            self.assertEqual(ignored.returncode, 0, "local_paths.json must be ignored by Git")

    def test_the_firth_path_exists_and_r_is_never_hard_coded(self):
        from src.chapter3.chapter4_v2.firth import ADAPTER, ENV_RSCRIPT
        self.assertTrue(ADAPTER.is_file())
        source = (PROJECT_ROOT / "python/src/chapter3/chapter4_v2/firth.py").read_text(
            encoding="utf-8")
        self.assertIn(ENV_RSCRIPT, source)
        self.assertNotIn("Program Files", source)
        self.assertNotIn(os.sep + "R-4", source)
