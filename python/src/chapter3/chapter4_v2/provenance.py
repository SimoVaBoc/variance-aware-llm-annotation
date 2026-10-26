"""Provenance attached to every analysis output.

An output is traceable only if it names the plan, the code and the software that
produced it. The plan is the specification's ID, version and SHA-256; the code
is the Git commit plus a flag for uncommitted changes, because a commit hash on
a modified tree would claim more than it shows; the software is the interpreter
and the versions of the packages actually imported.

Nothing here reads data. Git is asked only for the commit and the working-tree
status; when Git is unavailable the field says so rather than guessing.
"""

from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from .spec import PROJECT_ROOT, AnalysisSpec

UNAVAILABLE = "unavailable"

#: Packages whose versions are recorded when present.
TRACKED_PACKAGES = ("numpy", "scipy", "pandas", "statsmodels")


def _git(args: list[str], root: Path) -> str | None:
    try:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                   text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def code_state(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Commit and cleanliness of the working tree, or an explicit 'unavailable'."""

    commit = _git(["rev-parse", "HEAD"], root)
    # Untracked files count: a new module that is not committed is still code
    # that ran, and the commit hash alone would not reproduce it.
    status = _git(["status", "--porcelain"], root)
    return {
        "code_commit": commit or UNAVAILABLE,
        "working_tree_modified": None if status is None else bool(status),
    }


def software_versions(packages: Iterable[str] = TRACKED_PACKAGES) -> dict[str, str]:
    versions = {"python": platform.python_version(), "platform": sys.platform}
    for name in packages:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def output_header(spec: AnalysisSpec, *, synthetic: bool,
                  root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """The block written at the top of every output. ``synthetic`` is mandatory."""

    return {
        **spec.identity(),
        **code_state(root),
        "software": software_versions(),
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_kind": "synthetic" if synthetic else "empirical",
    }


__all__ = ["UNAVAILABLE", "code_state", "output_header", "software_versions"]
