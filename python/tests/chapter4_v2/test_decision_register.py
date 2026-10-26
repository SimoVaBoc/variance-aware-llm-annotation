"""The decision register: vocabulary, dating, open items and the generated Markdown."""

import copy

from _guard import SyntheticTestCase

from src.chapter3.chapter4_v2.decisions import (
    DEFAULT_MARKDOWN_PATH,
    load_register,
    register_problems,
    render_markdown,
)
from src.chapter3.chapter4_v2.spec import load_spec

#: Open items the brief requires to stay visible (SRC-BRIEF §13).
REQUIRED_OPEN = {"D-H3-02", "D-H2-02", "D-H2-03", "D-H2-04", "D-CHRON-01"}


class RegisterTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.register = load_register()

    def problems_after(self, change):
        data = copy.deepcopy(self.register)
        change(data)
        return register_problems(data, self.spec)

    def by_id(self, data=None):
        data = data or self.register
        return {d["id"]: d for d in data["decisions"]}

    def test_the_committed_register_is_valid(self):
        self.assertEqual(register_problems(self.register, self.spec), [])

    def test_the_required_open_decisions_are_unresolved_and_pending(self):
        decisions = self.by_id()
        for decision_id in REQUIRED_OPEN:
            self.assertEqual(decisions[decision_id]["status"], "unresolved", decision_id)
            self.assertIn(decisions[decision_id]["implementation_status"],
                          {"decision_pending", "not_applicable"})

    def test_dates_are_document_dates_never_adoption_dates(self):
        sources = {s["id"]: s["date"] for s in self.spec.data["sources"]}
        sources.update({s["id"]: s["date"] for s in self.register["implementation_sources"]})
        for d in self.register["decisions"]:
            self.assertEqual(d["source_document_date"], sources[d["recorded_in"]], d["id"])
            self.assertFalse([k for k in d if "adoption" in k], d["id"])

    def test_dates_stated_by_a_source_are_kept_apart_and_labelled(self):
        h2 = self.by_id()["D-H2-01"]
        self.assertEqual((h2["recorded_in"], h2["source_document_date"]), ("SRC-H2", "2026-10-25"))
        self.assertEqual(h2["date_stated_by_source"], "2026-10-17")
        self.assertIn("not independently verified", h2["date_note"])
        h3 = self.by_id()["D-H3-01"]
        self.assertEqual((h3["recorded_in"], h3["source_document_date"]), ("SRC-MAP", "2026-10-25"))
        self.assertNotIn("date_stated_by_source", h3)

    def test_a_document_date_that_differs_from_its_source_is_refused(self):
        problems = self.problems_after(
            lambda d: d["decisions"][0].update(source_document_date="2026-10-17"))
        self.assertTrue(any("is not the date of" in p for p in problems))

    def test_an_adoption_date_field_is_refused(self):
        problems = self.problems_after(
            lambda d: d["decisions"][0].update(known_adoption_date="2026-10-25"))
        self.assertTrue(any("no adoption date" in p for p in problems))

    def test_h3_records_both_procedures_and_the_recommendation_without_choosing(self):
        h3 = self.by_id()["D-H3-02"]
        self.assertIn("ordinary paired campaign bootstrap", h3["statement"])
        self.assertIn("HUMAN-stratified", h3["statement"])
        self.assertIn("not a ratified change", h3["recommendation"])
        self.assertEqual(h3["implementation_status"], "decision_pending")

    def test_no_entry_claims_supervisor_approval(self):
        problems = self.problems_after(
            lambda d: d["decisions"][0].update(supervisor_approval="approved by supervisor"))
        self.assertTrue(any("supervisor" in p for p in problems))

    def test_an_unresolved_decision_cannot_be_implemented(self):
        def change(d):
            next(x for x in d["decisions"] if x["id"] == "D-H3-02")[
                "implementation_status"] = "implemented"
        problems = self.problems_after(change)
        self.assertTrue(any("cannot be implemented" in p for p in problems))

    def test_stated_dates_are_iso(self):
        def change(d):
            next(x for x in d["decisions"] if x["id"] == "D-H2-01")[
                "date_stated_by_source"] = "17 October"
        problems = self.problems_after(change)
        self.assertTrue(any("ISO date" in p for p in problems))

    def test_spec_and_register_agree_on_the_open_set(self):
        def change(d):
            next(x for x in d["decisions"] if x["id"] == "D-H2-04")["status"] = "confirmed"
        problems = self.problems_after(change)
        self.assertTrue(any("differ from the register" in p for p in problems))

    def test_every_superseded_rule_points_to_a_confirmed_decision_that_lists_it(self):
        for entry in self.register["historical"]:
            target = self.by_id()[entry["superseded_by"]]
            self.assertEqual(target["status"], "confirmed")
            self.assertIn(entry["id"], target["supersedes"])

    def test_the_markdown_is_the_rendering_of_the_json(self):
        rendered = render_markdown(self.register, self.spec)
        self.assertEqual(DEFAULT_MARKDOWN_PATH.read_text(encoding="utf-8"), rendered)
