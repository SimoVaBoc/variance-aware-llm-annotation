"""Tests for the hierarchical aggregation and its missingness rule.

The rule is `researcher_approved`: at least two valid contributions at every
level, majority among three, agreement among two, an explicit null with a
recorded reason otherwise. It is recorded under `aggregation` in the experiment
definition and in `docs/chapter3_decision_memo.md`. These tests pin it, so that
any later change has to be a deliberate one.

The point under test throughout: nothing is ever imputed. A parse error or a
missing output reduces the number of valid contributions and, when that leaves
no majority, produces a null that propagates instead of a silent default.
"""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from src.chapter3.catalog import load_json  # noqa: E402
from src.chapter3.hierarchy import (  # noqa: E402
    AGGREGATION_STATUS,
    MINIMUM_VALID_CONTRIBUTIONS,
    NULL_NO_VALID,
    NULL_TIED,
    NULL_TOO_FEW,
    aggregate_models,
    aggregate_prompts,
    aggregate_samples,
    hierarchical_annotation,
    majority,
    pooled_annotation,
    valid_label,
)


EXPERIMENT_PATH = (
    PROJECT_ROOT / "config" / "experiments" / "chapter3_comparative_experiment_v1.json"
)


def record(item, model, template, sample, label, status="success", order="10"):
    return {
        "item_id": item,
        "model_id": model,
        "template_id": template,
        "camuffo_variant_id": template.replace("cm_", ""),
        "sample_index": sample,
        "label_order": order,
        "status": status,
        "parsed_label": label,
    }


def full_cell(item, model, template, labels):
    return [
        record(item, model, template, index, label, "success" if label is not None else "parse_error")
        for index, label in enumerate(labels, start=1)
    ]


class StatusTests(unittest.TestCase):
    def test_the_rule_is_approved_and_matches_the_config(self):
        self.assertEqual(AGGREGATION_STATUS, "researcher_approved")
        declared = load_json(EXPERIMENT_PATH)["aggregation"]
        self.assertEqual(declared["status"], AGGREGATION_STATUS)
        self.assertEqual(
            declared["minimum_valid_contributions"], MINIMUM_VALID_CONTRIBUTIONS
        )
        self.assertIn("never substituted", declared["rule"])
        self.assertIn("at least two valid contributions", declared["rule"])
        self.assertTrue(declared["missingness"]["parse_error_is_not_replaced"])
        self.assertEqual(
            set(declared["missingness"]["null_reasons"]),
            {NULL_NO_VALID, NULL_TOO_FEW, NULL_TIED},
        )

    def test_the_comparison_is_not_claimed_to_be_causal(self):
        declared = load_json(EXPERIMENT_PATH)["aggregation"]
        self.assertIn(
            "NOT a causal identification", declared["comparison_interpretation"]
        )


class MajorityTests(unittest.TestCase):
    def test_a_clear_majority(self):
        self.assertEqual(majority([1, 1, 0]).label, 1)
        self.assertEqual(majority([0, 0, 1]).label, 0)

    def test_two_valid_labels_that_disagree_are_null(self):
        aggregate = majority([1, 0, None])
        self.assertIsNone(aggregate.label)
        self.assertTrue(aggregate.tied)
        self.assertEqual(aggregate.null_reason, NULL_TIED)
        self.assertEqual(aggregate.n_valid, 2)
        self.assertEqual(aggregate.n_expected, 3)

    def test_no_valid_label_is_null_and_not_tied(self):
        aggregate = majority([None, None, None])
        self.assertIsNone(aggregate.label)
        self.assertFalse(aggregate.tied)
        self.assertEqual(aggregate.null_reason, NULL_NO_VALID)
        self.assertEqual(aggregate.n_valid, 0)

    def test_a_single_survivor_never_decides(self):
        """A lone surviving call is not a majority of anything."""

        for label in (0, 1):
            with self.subTest(label=label):
                aggregate = majority([label, None, None])
                self.assertIsNone(aggregate.label)
                self.assertEqual(aggregate.null_reason, NULL_TOO_FEW)
                self.assertEqual(aggregate.n_valid, 1)
                self.assertFalse(aggregate.as_record()["complete"])

    def test_two_agreeing_valid_labels_decide(self):
        """Two valid votes that agree decide; the third is not filled in."""

        aggregate = majority([0, 0, None])
        self.assertEqual(aggregate.label, 0)
        self.assertEqual(aggregate.votes_0, 2)
        self.assertEqual(aggregate.votes_1, 0)
        self.assertIsNone(aggregate.null_reason)
        self.assertEqual(aggregate.n_valid, 2)
        self.assertEqual(aggregate.n_expected, 3)

    def test_the_record_carries_both_vote_counts(self):
        record = majority([1, 1, 0]).as_record()
        self.assertEqual(record["votes_1"], 2)
        self.assertEqual(record["votes_0"], 1)
        self.assertEqual(record["n_valid"], 3)
        self.assertTrue(record["complete"])
        self.assertIsNone(record["null_reason"])


class ValidLabelTests(unittest.TestCase):
    def test_a_parse_error_carries_no_label(self):
        self.assertIsNone(valid_label({"status": "parse_error", "parsed_label": None}))

    def test_an_api_error_carries_no_label(self):
        self.assertIsNone(valid_label({"status": "api_error", "parsed_label": None}))

    def test_a_success_carries_its_label(self):
        self.assertEqual(valid_label({"status": "success", "parsed_label": 0}), 0)

    def test_a_non_binary_label_on_a_success_is_refused(self):
        self.assertIsNone(valid_label({"status": "success", "parsed_label": 2}))


class LevelTests(unittest.TestCase):
    def test_sample_level_records_its_accounting(self):
        rows = full_cell("CB001", "m1", "cm_base", [1, 1, None])
        (aggregate,) = aggregate_samples(rows)
        self.assertEqual(aggregate["aggregated_label"], 1)
        self.assertEqual(aggregate["n_valid"], 2)
        self.assertEqual(aggregate["n_expected"], 3)
        self.assertFalse(aggregate["complete"])

    def test_sample_level_records_the_label_orders_seen(self):
        rows = [
            record("CB001", "m1", "cm_base", 1, 1, order="10"),
            record("CB001", "m1", "cm_base", 2, 1, order="10"),
            record("CB001", "m1", "cm_base", 3, 0, order="01"),
        ]
        (aggregate,) = aggregate_samples(rows)
        self.assertEqual(aggregate["label_orders"], ["01", "10"])

    def test_a_null_propagates_to_the_prompt_level(self):
        rows = []
        rows += full_cell("CB001", "m1", "cm_base", [1, 0, None])          # null
        rows += full_cell("CB001", "m1", "cm_paraphrase_1", [1, 1, 1])     # 1
        rows += full_cell("CB001", "m1", "cm_paraphrase_2", [0, 0, 0])     # 0
        by_prompt = aggregate_prompts(aggregate_samples(rows))
        (aggregate,) = by_prompt
        self.assertIsNone(aggregate["aggregated_label"])
        self.assertTrue(aggregate["tied"])
        self.assertEqual(aggregate["n_valid"], 2)

    def test_two_agreeing_prompts_decide_despite_a_null(self):
        rows = []
        rows += full_cell("CB001", "m1", "cm_base", [None, None, None])    # null
        rows += full_cell("CB001", "m1", "cm_paraphrase_1", [1, 1, 0])     # 1
        rows += full_cell("CB001", "m1", "cm_paraphrase_2", [1, 0, 1])     # 1
        (aggregate,) = aggregate_prompts(aggregate_samples(rows))
        self.assertEqual(aggregate["aggregated_label"], 1)
        self.assertEqual(aggregate["n_valid"], 2)
        self.assertEqual(aggregate["n_expected"], 3)

    def test_a_lone_surviving_prompt_does_not_decide(self):
        rows = []
        rows += full_cell("CB001", "m1", "cm_base", [1, 1, 1])             # 1
        rows += full_cell("CB001", "m1", "cm_paraphrase_1", [None] * 3)    # null
        rows += full_cell("CB001", "m1", "cm_paraphrase_2", [None] * 3)    # null
        (aggregate,) = aggregate_prompts(aggregate_samples(rows))
        self.assertIsNone(aggregate["aggregated_label"])
        self.assertEqual(aggregate["null_reason"], NULL_TOO_FEW)
        self.assertEqual(aggregate["n_valid"], 1)

    def test_a_cell_with_one_surviving_sample_yields_no_label(self):
        rows = full_cell("CB001", "m1", "cm_base", [1, None, None])
        (aggregate,) = aggregate_samples(rows)
        self.assertIsNone(aggregate["aggregated_label"])
        self.assertEqual(aggregate["null_reason"], NULL_TOO_FEW)

    def test_the_model_level_yields_the_final_annotation(self):
        prompts = [
            {"item_id": "CB001", "model_id": "m1", "aggregated_label": 1},
            {"item_id": "CB001", "model_id": "m2", "aggregated_label": 1},
            {"item_id": "CB001", "model_id": "m3", "aggregated_label": 0},
        ]
        (aggregate,) = aggregate_models(prompts)
        self.assertEqual(aggregate["annotation"], 1)
        self.assertEqual(aggregate["n_valid"], 3)
        self.assertTrue(aggregate["complete"])

    def test_an_item_with_no_valid_label_annotates_to_null(self):
        prompts = [
            {"item_id": "CB001", "model_id": model, "aggregated_label": None}
            for model in ("m1", "m2", "m3")
        ]
        (aggregate,) = aggregate_models(prompts)
        self.assertIsNone(aggregate["annotation"])
        self.assertEqual(aggregate["n_valid"], 0)


class EndToEndTests(unittest.TestCase):
    def build(self, labels_by_cell):
        rows = []
        for (model, template), labels in labels_by_cell.items():
            rows += full_cell("CB001", model, template, labels)
        return rows

    def complete_item(self):
        return self.build(
            {
                (model, template): [1, 1, 0]
                for model in ("m1", "m2", "m3")
                for template in ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")
            }
        )

    def test_a_complete_item_annotates_cleanly(self):
        result = hierarchical_annotation(self.complete_item())
        self.assertEqual(result["status"], "researcher_approved")
        self.assertEqual(len(result["by_sample"]), 9)
        self.assertEqual(len(result["by_prompt"]), 3)
        self.assertEqual(len(result["by_model"]), 1)
        self.assertEqual(result["by_model"][0]["annotation"], 1)
        self.assertEqual(result["n_null_annotations"], 0)

    def test_widespread_parse_errors_surface_as_a_null_not_a_default(self):
        rows = self.build(
            {
                (model, template): [None, None, None]
                for model in ("m1", "m2", "m3")
                for template in ("cm_base", "cm_paraphrase_1", "cm_paraphrase_2")
            }
        )
        result = hierarchical_annotation(rows)
        self.assertIsNone(result["by_model"][0]["annotation"])
        self.assertEqual(result["n_null_annotations"], 1)

    def test_one_lost_call_does_not_change_a_clear_annotation(self):
        rows = self.complete_item()
        rows[0]["status"] = "parse_error"
        rows[0]["parsed_label"] = None
        result = hierarchical_annotation(rows)
        self.assertEqual(result["by_model"][0]["annotation"], 1)
        incomplete = [row for row in result["by_sample"] if not row["complete"]]
        self.assertEqual(len(incomplete), 1)
        self.assertEqual(incomplete[0]["n_valid"], 2)

    def test_the_pooled_check_is_labelled_secondary(self):
        (pooled,) = pooled_annotation(self.complete_item())
        self.assertEqual(pooled["role"], "robustness_check_secondary")
        self.assertEqual(pooled["n_valid"], 27)
        self.assertEqual(pooled["aggregated_label"], 1)

    def test_the_hierarchy_and_the_pooled_check_can_disagree(self):
        """Which is exactly why the pooled majority is only a robustness check.

        One model answering unanimously the other way outvotes two models that
        were split, once every output is thrown into one pot.
        """

        rows = self.build(
            {
                ("m1", "cm_base"): [0, 0, 0],
                ("m1", "cm_paraphrase_1"): [0, 0, 0],
                ("m1", "cm_paraphrase_2"): [0, 0, 0],
                ("m2", "cm_base"): [1, 1, 0],
                ("m2", "cm_paraphrase_1"): [1, 0, 0],
                ("m2", "cm_paraphrase_2"): [1, 1, 0],
                ("m3", "cm_base"): [1, 0, 0],
                ("m3", "cm_paraphrase_1"): [1, 1, 0],
                ("m3", "cm_paraphrase_2"): [1, 0, 1],
            }
        )
        hierarchical = hierarchical_annotation(rows)["by_model"][0]["annotation"]
        (pooled,) = pooled_annotation(rows)
        self.assertEqual(hierarchical, 1)
        self.assertEqual(pooled["aggregated_label"], 0)


if __name__ == "__main__":
    unittest.main()
