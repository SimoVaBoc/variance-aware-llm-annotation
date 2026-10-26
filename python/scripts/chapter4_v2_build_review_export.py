"""Build the review package from an explicit allowlist, never from the working history.

Every file in the export is named one by one in the allowlist
(``docs/chapter4_v2/review_export_allowlist.json``) as a source path in this
repository and a destination path in the export. Nothing else is copied. Sources
under ``runs/``, environments, caches, local configuration, archives and the excluded
documents are refused even if listed. Under ``data/`` only the starting inputs named in
``STARTING_DATA`` pass (decision D-EXPORT-03), each at its own path and only while its
bytes still match the pinned SHA-256; every other path under ``data/`` is refused. The
frozen Chapter 3 files that record observations are refused as sources: they enter only
as the derived copies written by ``chapter4_v2_redact_for_review.py``. Files are copied
byte for byte and re-hashed; ``EXPORT_MANIFEST.json`` records each destination path with its size and
SHA-256 and the source commit. With ``--git`` the export becomes a new repository with
a single commit and a neutral local identity, unrelated to the working history.

The target folder must not exist and must lie outside this repository. Nothing is
pushed or published.

Usage, from the repository root::

    python -B python/scripts/chapter4_v2_build_review_export.py --target <new folder> --git
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = PROJECT_ROOT / "docs/chapter4_v2/review_export_allowlist.json"

FORBIDDEN_PARTS = {"data", "runs", ".venv", "venv", "__pycache__", ".git", ".vscode",
                   "Codice_tesi_private"}
FORBIDDEN_NAMES = {"AI_disclosure.md", "CLAUDE.md", "local_paths.json"}
FORBIDDEN_SUFFIXES = {".zip", ".7z", ".tar", ".gz", ".pyc", ".jsonl", ".env", ".pem", ".key"}


#: Starting inputs that no run generated (D-EXPORT-03): the benchmark dataset and the two
#: prompt source files the configurations refer to. They are not tracked in the working
#: history, so their bytes are pinned here instead. Provenance and redistribution licence
#: are to be confirmed by the author.
STARTING_DATA = {
    "data/test_sample.csv": "bf5f186138be768849ebd3ef9ab84a2ff4288421293e5c7ab597fe99236a8e5c",
    "data/prompt_variations.csv": "8eb3fb89b75a134eed45c63e3cde573e1936efdffc3385a4e33fc74487c60ae1",
    "data/prompt_creation_template.txt": "bf7647d27291886d3a1a9839deed587b30b31e672bd0cea4599112462ac6ab6d",
}


def _frozen_observation_files() -> set[str]:
    """The originals that only their redacted copies may stand in for."""

    spec = importlib.util.spec_from_file_location(
        "chapter4_v2_redact_for_review", Path(__file__).with_name("chapter4_v2_redact_for_review.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.ORIGINALS) | set(module.NOT_REDACTABLE)


FROZEN_OBSERVATION_FILES = _frozen_observation_files()


class ExportRefused(RuntimeError):
    """The allowlist or the target would let private or stray material into the export."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_entry(source: str, dest: str) -> list[str]:
    problems = []
    starting_data = source in STARTING_DATA and dest == source
    if source in FROZEN_OBSERVATION_FILES:
        problems.append(f"source {source!r} records observations; list its redacted copy")
    for label, value in (("source", source), ("dest", dest)):
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts or "\\" in value or not value:
            problems.append(f"{label} {value!r} must be a relative POSIX path")
            continue
        forbidden = FORBIDDEN_PARTS - ({"data"} if starting_data else set())
        if forbidden & set(pure.parts):
            problems.append(f"{label} {value!r} lies in a forbidden folder")
        if pure.name in FORBIDDEN_NAMES or pure.suffix in FORBIDDEN_SUFFIXES:
            problems.append(f"{label} {value!r} is a forbidden file")
    return problems


def load_allowlist(path: Path = ALLOWLIST) -> list[dict[str, str]]:
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    problems = [p for e in entries for p in check_entry(e["source"], e["dest"])]
    dests = [e["dest"] for e in entries]
    if len(dests) != len(set(dests)):
        problems.append("two entries share a destination")
    for e in entries:
        if not (PROJECT_ROOT / e["source"]).is_file():
            problems.append(f"source {e['source']!r} does not exist")
    if problems:
        raise ExportRefused("Invalid allowlist:\n- " + "\n- ".join(problems))
    return entries


def git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def build(target: Path, *, make_git: bool, message: str, provisional: bool = False) -> dict:
    """Copy the allowlist. ``provisional`` allows uncommitted sources but never a repository."""

    target = target.resolve()
    if target.exists():
        raise ExportRefused(f"refusing to write into an existing folder: {target}")
    if PROJECT_ROOT in target.parents or target == PROJECT_ROOT:
        raise ExportRefused("the export must lie outside the working repository")
    if provisional and make_git:
        raise ExportRefused("a provisional build is never made into a repository")
    entries = load_allowlist()
    source_commit = git(["rev-parse", "HEAD"], PROJECT_ROOT)
    tracked = [e["source"] for e in entries if e["source"] not in STARTING_DATA]
    dirty = bool(git(["status", "--porcelain", "--", *tracked], PROJECT_ROOT))
    if dirty and not provisional:
        raise ExportRefused("an allowlisted source differs from the working commit; commit first")
    for e in entries:
        if e["source"] in STARTING_DATA and sha256(PROJECT_ROOT / e["source"]) != STARTING_DATA[e["source"]]:
            raise ExportRefused(f"{e['source']} differs from its pinned SHA-256")
    files = []
    for e in entries:
        src, dst = PROJECT_ROOT / e["source"], target / e["dest"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if sha256(src) != sha256(dst):
            raise ExportRefused(f"copy of {e['source']} does not reproduce its bytes")
        files.append({"path": e["dest"], "size_bytes": dst.stat().st_size, "sha256": sha256(dst)})
    manifest = {"kind": "chapter4_v2_review_export", "built_from_commit": source_commit,
                "provisional_uncommitted_sources": bool(provisional and dirty),
                "allowlist": ALLOWLIST.relative_to(PROJECT_ROOT).as_posix(),
                "n_files": len(files), "files": files,
                "starting_data": sorted(e["dest"] for e in entries if e["source"] in STARTING_DATA),
                "note": "Source code, specification, documentation, synthetic tests and the "
                        "starting data (benchmark dataset and prompt source files; not tracked "
                        "in the working history, pinned by SHA-256 in the builder). No outputs, "
                        "logs or results. Provenance and redistribution licence of the starting "
                        "data are to be confirmed by the author; keep the repository private "
                        "until then."}
    (target / "EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    result = {"target": str(target), "n_files": len(files) + 1, "built_from_commit": source_commit}
    if make_git:
        git(["init", "-q", "-b", "main"], target)
        for key, value in (("core.autocrlf", "false"), ("user.name", "Thesis Review Export"),
                           ("user.email", "thesis-review-export@example.invalid")):
            git(["config", "--local", key, value], target)
        git(["add", "--", "."], target)
        git(["commit", "-q", "-m", message], target)
        result["review_commit"] = git(["rev-parse", "HEAD"], target)
        result["tracked_files"] = len(git(["ls-files"], target).splitlines())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--target", required=True)
    parser.add_argument("--git", action="store_true", help="make the export a new repository")
    parser.add_argument("--message", default="Chapter 4 v2 review package (synthetic only)")
    parser.add_argument("--check", action="store_true", help="validate the allowlist only")
    parser.add_argument("--provisional", action="store_true",
                        help="allow uncommitted sources (for checks only; never with --git)")
    args = parser.parse_args(argv)
    try:
        if args.check:
            print(f"allowlist valid: {len(load_allowlist())} entries")
            return 0
        print(json.dumps(build(Path(args.target), make_git=args.git, message=args.message,
                               provisional=args.provisional), indent=2))
    except ExportRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
