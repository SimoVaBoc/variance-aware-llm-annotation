"""The guard itself: private paths are refused before any file is opened."""

import os
import socket
import tempfile
from pathlib import Path

from _guard import PROJECT_ROOT, PrivateDataAccess, SyntheticTestCase, is_blocked


class GuardTests(SyntheticTestCase):
    def test_paths_under_data_and_runs_are_blocked(self):
        for path in (PROJECT_ROOT / "data", PROJECT_ROOT / "data" / "any.csv",
                     PROJECT_ROOT / "runs" / "raw" / "x.jsonl"):
            self.assertTrue(is_blocked(path), path)

    def test_private_folder_is_blocked_wherever_it_lives(self):
        self.assertTrue(is_blocked(Path("C:/elsewhere/Codice_tesi_private/runs/x")))

    def test_other_paths_are_not_blocked(self):
        for path in (PROJECT_ROOT / "python", PROJECT_ROOT / "dataset_notes.md",
                     Path(tempfile.gettempdir()) / "x"):
            self.assertFalse(is_blocked(path), path)

    def test_open_is_refused_before_the_file_is_looked_up(self):
        # The name does not exist: a FileNotFoundError would mean the OS was asked.
        missing = PROJECT_ROOT / "data" / "no_such_file_for_guard_test.csv"
        with self.assertRaises(PrivateDataAccess):
            open(missing, "rb")

    def test_listing_a_private_tree_is_refused(self):
        with self.assertRaises(PrivateDataAccess):
            os.listdir(PROJECT_ROOT / "runs")

    def test_network_is_refused(self):
        with self.assertRaises(AssertionError):
            socket.create_connection(("example.invalid", 80))
