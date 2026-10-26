"""Guards that make the public synthetic suite provably data-free and offline.

Importing this module installs a process-wide audit hook. From then on, any
attempt to open, list or stat-walk a path under the repository's ``data/`` or
``runs/`` trees, or under a ``Codice_tesi_private`` folder, raises before the
operating system is asked for the file. The hook fires on the path alone, so a
blocked file is never read, not even to discover that it exists.

``SyntheticTestCase`` adds the network block: the methods that open a
connection raise for the duration of each test. The approach mirrors the legacy
``tests/chapter3/_nonetwork.py``; it is restated here so that the public suite
does not depend on the historical test tree, which stays private.
"""

from __future__ import annotations

import os
import socket
import sys
import unittest
from pathlib import Path

#: One BLAS thread, set before numpy is first imported: the suite then runs on a
#: machine with little free memory, and linear algebra is single-threaded and
#: repeatable. An explicit setting in the environment wins.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = PROJECT_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

#: Folder name of the private empirical archive, wherever it is placed.
PRIVATE_FOLDER_NAME = "Codice_tesi_private"

BLOCKED_ROOTS = tuple(
    os.path.normcase(os.path.abspath(p))
    for p in (PROJECT_ROOT / "data", PROJECT_ROOT / "runs")
)

_GUARDED_EVENTS = frozenset({"open", "os.listdir", "os.scandir", "os.walk", "glob.glob"})


class PrivateDataAccess(PermissionError):
    """A synthetic test tried to touch private empirical material."""


def is_blocked(path: object) -> bool:
    """True for paths inside the private trees. Never touches the filesystem."""

    if isinstance(path, int) or path is None:
        return False
    try:
        text = os.fsdecode(path)
    except TypeError:
        return False
    absolute = os.path.normcase(os.path.abspath(text))
    if PRIVATE_FOLDER_NAME.lower() in (part.lower() for part in Path(absolute).parts):
        return True
    for root in BLOCKED_ROOTS:
        if absolute == root or absolute.startswith(root + os.sep):
            return True
    return False


def _audit(event: str, args: tuple) -> None:
    if event in _GUARDED_EVENTS and args and is_blocked(args[0]):
        raise PrivateDataAccess(
            f"{event} on a private path was blocked; the public suite uses synthetic "
            "fixtures only"
        )


if not getattr(sys, "_chapter4_v2_guard_installed", False):
    sys.addaudithook(_audit)
    sys._chapter4_v2_guard_installed = True  # type: ignore[attr-defined]


class SyntheticTestCase(unittest.TestCase):
    """Offline test case: any attempt to open a network connection fails."""

    def setUp(self) -> None:
        super().setUp()
        saved = {
            "connect": socket.socket.connect,
            "connect_ex": socket.socket.connect_ex,
            "create_connection": socket.create_connection,
            "getaddrinfo": socket.getaddrinfo,
        }

        def forbidden(*args, **kwargs):
            raise AssertionError("The synthetic suite is offline; a network connection "
                                 "was attempted.")

        socket.socket.connect = forbidden
        socket.socket.connect_ex = forbidden
        socket.create_connection = forbidden
        socket.getaddrinfo = forbidden

        def restore() -> None:
            socket.socket.connect = saved["connect"]
            socket.socket.connect_ex = saved["connect_ex"]
            socket.create_connection = saved["create_connection"]
            socket.getaddrinfo = saved["getaddrinfo"]

        self.addCleanup(restore)


__all__ = ["PROJECT_ROOT", "PYTHON_ROOT", "PrivateDataAccess", "SyntheticTestCase", "is_blocked"]
