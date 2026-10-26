"""Descriptive analyses never borrow the criteria vocabulary."""

import ast

from _guard import PROJECT_ROOT, SyntheticTestCase

from src.chapter3.chapter4_v2.analysis_status import ANALYSIS_STATUSES
from src.chapter3.chapter4_v2.thresholds import STATUSES

DESCRIPTIVE = ("h1.py", "h3.py", "h4_e1.py")
CRITERIA_NAMES = {"SATISFIED", "NOT_SATISFIED", "NOT_EVALUABLE"}


class VocabularyTests(SyntheticTestCase):
    def test_the_two_vocabularies_are_disjoint(self):
        self.assertEqual(set(ANALYSIS_STATUSES) & set(STATUSES), set())

    def test_descriptive_modules_use_no_criteria_status(self):
        for name in DESCRIPTIVE:
            source = (PROJECT_ROOT / "python/src/chapter3/chapter4_v2" / name).read_text(
                encoding="utf-8")
            used = {node.id for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)}
            self.assertEqual(used & CRITERIA_NAMES, set(), name)
            for literal in ('"satisfied"', '"not_satisfied"', '"not_evaluable"'):
                self.assertNotIn(literal, source, name)
