"""Importing the new package reads no data, starts no analysis and makes no call.

The check runs in a fresh interpreter: re-importing inside this process would
create second copies of the modules and their classes, which would corrupt the
rest of the suite.
"""

import json
import os
import subprocess
import sys

from _guard import PYTHON_ROOT, SyntheticTestCase

MODULES = (
    "src.chapter3.chapter4_v2",
    "src.chapter3.chapter4_v2.spec",
    "src.chapter3.chapter4_v2.decisions",
    "src.chapter3.chapter4_v2.provenance",
    "src.chapter3.chapter4_v2.inputs",
    "src.chapter3.chapter4_v2.io_boundary",
    "src.chapter3.chapter4_v2.procedures",
    "src.chapter3.chapter4_v2.aggregation",
    "src.chapter3.chapter4_v2.samples",
    "src.chapter3.chapter4_v2.scores",
    "src.chapter3.chapter4_v2.thresholds",
    "src.chapter3.chapter4_v2.comparisons",
    "src.chapter3.chapter4_v2.framework_bootstrap",
    "src.chapter3.chapter4_v2.robustness",
    "src.chapter3.chapter4_v2.framework",
    "src.chapter3.chapter4_v2.annotation_framework",
    "src.chapter3.chapter4_v2.downstream",
    "src.chapter3.chapter4_v2.firth",
    "src.chapter3.chapter4_v2.h4_e1",
    "src.chapter3.chapter4_v2.pending",
    "src.chapter3.chapter4_v2.h1",
    "src.chapter3.chapter4_v2.h2",
    "src.chapter3.chapter4_v2.h3",
    "src.chapter3.chapter4_v2.analysis_status",
    "src.chapter3.chapter4_v2.reporting",
    "src.chapter3.chapter4_v2.synthetic",
)

PROBE = """
import importlib, json, os, sys
sys.path.insert(0, sys.argv[1])
opened = []
# The one allowed process: Python's platform module (reached through scipy ->
# numpy.testing -> platform.machine) runs `ver` with shell=True on Windows when its WMI
# query fails, which Windows expands to exactly '<COMSPEC> /c "ver"'. Its stdin is the
# null device, the only extra path allowed. Exact matches only; anything else fails.
COMSPEC = os.environ.get("COMSPEC", "cmd.exe")
ALLOWED_COMMAND = COMSPEC + ' /c "ver"'
ALLOWED_PATH = "nul"
def platform_version_probe(args):
    return (len(args) > 1 and args[0] == COMSPEC and args[1] == ALLOWED_COMMAND)
def audit(event, args):
    if event == "open" and args and isinstance(args[0], str):
        if not (os.name == "nt" and args[0] == ALLOWED_PATH):
            opened.append(args[0])
    if event == "subprocess.Popen" and os.name == "nt" and platform_version_probe(args):
        return
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "subprocess.Popen",
                 "os.system"):
        opened.append("EVENT:" + event)
sys.addaudithook(audit)
for name in sys.argv[2:]:
    importlib.import_module(name)
print(json.dumps({"opened": opened, "prefixes": [sys.prefix, sys.base_prefix]}))
"""


class ImportTests(SyntheticTestCase):
    def test_fresh_imports_open_only_source_files_and_start_nothing(self):
        result = subprocess.run([sys.executable, "-I", "-c", PROBE, str(PYTHON_ROOT), *MODULES],
                                capture_output=True, text=True, timeout=120, check=True)
        probe = json.loads(result.stdout)
        opened = probe["opened"]
        self.assertTrue(opened, "the probe saw the imports")
        # Installation files (the standard-library zip probe, package metadata that
        # scipy reads about numpy) belong to the interpreter, not to the analysis.
        installation = tuple(os.path.normcase(os.path.abspath(p)) for p in probe["prefixes"])
        unexpected = [p for p in opened
                      if not p.endswith((".py", ".pyc")) and "__pycache__" not in p
                      and not os.path.normcase(os.path.abspath(p)).startswith(installation)]
        self.assertEqual(unexpected, [])
        self.assertFalse([p for p in opened if p.startswith("EVENT:")],
                         "no connection and no process is started at import")

    def test_the_exception_is_exact_and_any_other_process_or_file_is_caught(self):
        import shutil
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp(prefix="synthetic_probe_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "synthetic_starts_process.py").write_text(
            "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n",
            encoding="utf-8")
        (root / "synthetic_opens_file.py").write_text(
            "open(__file__ + '.txt', 'w').close()\n", encoding="utf-8")
        for module, expected in (("synthetic_starts_process", "EVENT:subprocess.Popen"),
                                 ("synthetic_opens_file", "synthetic_opens_file.py.txt")):
            result = subprocess.run([sys.executable, "-I", "-c", PROBE, str(root), module],
                                    capture_output=True, text=True, timeout=120, check=True)
            opened = json.loads(result.stdout)["opened"]
            self.assertTrue(any(p.endswith(expected) for p in opened), (module, opened))
