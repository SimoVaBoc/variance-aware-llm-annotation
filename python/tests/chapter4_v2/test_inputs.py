"""The task-level adapter: four slot states, and integrity errors that are never missing labels."""

import copy

from _guard import SyntheticTestCase

import fixtures as fx
from src.chapter3.chapter4_v2.inputs import (
    SLOT_TECHNICAL_FAILURE,
    SLOT_TERMINAL_INVALID,
    SLOT_UNOBSERVED,
    SLOT_VALID,
    InputIntegrityError,
    SlotKey,
    assemble_input,
    parse_item,
)
from src.chapter3.chapter4_v2.spec import load_spec


class AdapterTests(SyntheticTestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.items = fx.make_item_rows(4)
        cls.item_ids = [row["item_id"] for row in cls.items]
        cls.manifests = fx.make_manifests(cls.spec, cls.item_ids)

    def assemble(self, records, manifests=None, items=None):
        return assemble_input(self.spec, items or self.items, manifests or self.manifests,
                              fx.COLLECTION_MODEL_IDS, records, data_kind="synthetic")

    def va_key(self, item=0, model="sonnet_5", template="cm_base", sample=1):
        return SlotKey(self.item_ids[item], model, template, sample)

    def assert_integrity_error(self, records, fragment, manifests=None):
        with self.assertRaises(InputIntegrityError) as caught:
            self.assemble(records, manifests)
        self.assertTrue(any(fragment in p for p in caught.exception.problems),
                        caught.exception.problems)

    # -- states -------------------------------------------------------------

    def test_complete_valid_run_has_one_valid_slot_per_planned_call(self):
        data = self.assemble(fx.make_records(self.manifests))
        per_item = 3 * (7 + 9)
        self.assertEqual(len(data.slots), per_item * len(self.item_ids))
        self.assertTrue(all(s.state == SLOT_VALID for s in data.slots.values()))
        self.assertEqual(data.data_kind, "synthetic")
        self.assertIn("spec_sha256", data.provenance)

    def test_the_four_states_stay_distinct(self):
        invalid = self.va_key(sample=1)
        failed = self.va_key(sample=2)
        absent = self.va_key(sample=3)
        recovered = self.va_key(template="cm_paraphrase_1")
        records = fx.make_records(self.manifests, label_of=lambda k: 1, states={
            invalid: "parse_error", failed: "api_error_only", absent: "absent",
            recovered: "api_error_then_success"})
        slots = self.assemble(records).slots
        self.assertEqual(slots[invalid].state, SLOT_TERMINAL_INVALID)
        self.assertEqual(slots[failed].state, SLOT_TECHNICAL_FAILURE)
        self.assertEqual(slots[absent].state, SLOT_UNOBSERVED)
        self.assertEqual((slots[recovered].state, slots[recovered].label), (SLOT_VALID, 1))
        self.assertEqual(slots[recovered].n_technical_records, 1)
        for key in (invalid, failed, absent):
            self.assertIsNone(slots[key].label, "a non-valid slot never becomes label 0")

    def test_state_counts_are_reported_by_arm(self):
        records = fx.make_records(self.manifests, states={self.va_key(): "parse_error"})
        counts = self.assemble(records).state_counts()
        self.assertEqual(counts["camuffo"][SLOT_TERMINAL_INVALID], 1)
        self.assertEqual(counts["carlson"][SLOT_TERMINAL_INVALID], 0)

    # -- integrity errors ---------------------------------------------------

    def test_two_terminal_records_for_one_task_are_an_integrity_error(self):
        records = fx.make_records(self.manifests)
        records.append(copy.deepcopy(records[0]))
        self.assert_integrity_error(records, "spent twice")

    def test_a_record_outside_the_plan_is_an_integrity_error(self):
        records = fx.make_records(self.manifests)
        extra = dict(records[0], task_id="synthetic__not_planned")
        self.assert_integrity_error(records + [extra], "not in the plan")

    def test_identity_and_hash_mismatches_are_integrity_errors(self):
        records = fx.make_records(self.manifests)
        records[0] = dict(records[0], item_id=self.item_ids[-1])
        records[1] = dict(records[1], payload_sha256="0" * 64)
        records[2] = dict(records[2], sample_index=2)
        with self.assertRaises(InputIntegrityError) as caught:
            self.assemble(records)
        text = "\n".join(caught.exception.problems)
        for fragment in ("item_id is", "payload_sha256 differs", "sample_index differs"):
            self.assertIn(fragment, text)

    def test_a_stored_label_the_parser_does_not_reproduce_is_refused(self):
        records = fx.make_records(self.manifests)
        records[0] = dict(records[0], raw_response="1", parsed_label=0)
        records[1] = dict(records[1], raw_response="00", parsed_label=0)
        with self.assertRaises(InputIntegrityError) as caught:
            self.assemble(records)
        self.assertEqual(sum("strict parser reads" in p for p in caught.exception.problems), 2)

    def test_a_parse_error_on_a_valid_response_is_refused(self):
        records = fx.make_records(self.manifests)
        records[0] = dict(records[0], status="parse_error", raw_response=" 1 ", parsed_label=None)
        self.assert_integrity_error(records, "parse_error on a response")

    def test_dry_run_and_remediation_records_are_refused(self):
        records = fx.make_records(self.manifests)
        records[0] = dict(records[0], status="dry_run")
        records[1] = dict(records[1], is_remediation=True)
        with self.assertRaises(InputIntegrityError) as caught:
            self.assemble(records)
        text = "\n".join(caught.exception.problems)
        self.assertIn("not an analytical status", text)
        self.assertIn("remediation", text)

    def test_a_planned_slot_missing_from_the_manifest_is_an_integrity_error(self):
        manifests = copy.deepcopy(self.manifests)
        manifests["terra_5_6"] = manifests["terra_5_6"][1:]
        records = fx.make_records(manifests)
        self.assert_integrity_error(records, "absent from the manifests", manifests)

    def test_duplicate_task_ids_and_slots_in_the_manifest_are_refused(self):
        manifests = copy.deepcopy(self.manifests)
        manifests["terra_5_6"].append(dict(manifests["terra_5_6"][0]))
        self.assert_integrity_error([], "duplicate task_id", manifests)
        manifests = copy.deepcopy(self.manifests)
        manifests["terra_5_6"].append(dict(manifests["terra_5_6"][0], task_id="synthetic__dup"))
        self.assert_integrity_error([], "already planned", manifests)

    def test_a_cell_whose_label_order_varies_across_s_is_refused(self):
        manifests = copy.deepcopy(self.manifests)
        row = next(r for r in manifests["sonnet_5"]
                   if r["arm"] == "camuffo" and r["sample_index"] == "2")
        row["label_order"] = "01" if row["label_order"] == "10" else "10"
        self.assert_integrity_error([], "varies its label order", manifests)

    def test_the_collection_model_id_must_match_the_binding(self):
        manifests = copy.deepcopy(self.manifests)
        for row in manifests["deepseek_v4_pro"]:
            row["model_id"] = "deepseek_v4_pro"
        self.assert_integrity_error([], "not the bound collection model", manifests)

    def test_problems_are_collected_in_full_not_one_at_a_time(self):
        records = fx.make_records(self.manifests)
        for i in range(5):
            records[i] = dict(records[i], payload_sha256="f" * 64)
        with self.assertRaises(InputIntegrityError) as caught:
            self.assemble(records)
        self.assertEqual(len(caught.exception.problems), 5)

    # -- items --------------------------------------------------------------

    def test_items_validate_types_without_recoding(self):
        record = parse_item({"item_id": "SYN1", "HUMAN": "1", "success": "0", "lgoal": "9.25",
                             "subcategory": "alpha", "year": "2011"})
        self.assertEqual((record.human, record.success, record.lgoal, record.year),
                         (1, 0, 9.25, "2011"))
        self.assertEqual(record.issues, ())
        bad = parse_item({"item_id": "SYN2", "HUMAN": "yes", "success": "", "lgoal": "inf",
                          "subcategory": " ", "year": None})
        self.assertEqual((bad.human, bad.success, bad.lgoal, bad.subcategory, bad.year),
                         (None, None, None, None, None))
        self.assertEqual(len(bad.issues), 5)

    def test_duplicate_items_are_an_integrity_error(self):
        items = self.items + [dict(self.items[0])]
        with self.assertRaises(InputIntegrityError):
            assemble_input(self.spec, items, self.manifests, fx.COLLECTION_MODEL_IDS, [],
                           data_kind="synthetic")

    def test_data_kind_must_be_declared(self):
        with self.assertRaises(ValueError):
            assemble_input(self.spec, self.items, self.manifests, fx.COLLECTION_MODEL_IDS,
                           fx.make_records(self.manifests), data_kind="")
