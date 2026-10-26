import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = PROJECT_ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from src.chapter3.results import parse_binary_label, validate_result_records  # noqa: E402


def valid_record(task_id="task-1"):
    return {
        "task_id": task_id,
        "item_id": "CB001",
        "model_id": "terra_5_6",
        "api_model_requested": "gpt-5.6-terra",
        "api_model_returned": "gpt-5.6-terra",
        "prompt_id": "zero_shot",
        "replicate_id": 1,
        "raw_response": "1",
        "parsed_label": 1,
        "status": "success",
        "started_at_utc": "2026-09-16T00:00:00Z",
        "completed_at_utc": "2026-09-16T00:00:01Z",
        "latency_ms": 1000,
        "input_tokens": 100,
        "output_tokens": 1,
        "provider_request_id": "request-1",
        "system_fingerprint": None,
        "attempt_count": 1,
        "error_type": None,
        "error_message": None,
        "text_sha256": "text-hash",
        "prompt_sha256": "prompt-hash",
        "config_sha256": "abc",
    }


class Chapter3ResultTests(unittest.TestCase):
    def test_strict_binary_parser(self):
        self.assertEqual(parse_binary_label(" 0\n"), 0)
        self.assertEqual(parse_binary_label("1"), 1)
        for invalid in ("label: 1", "10", "yes", ""):
            with self.assertRaises(ValueError):
                parse_binary_label(invalid)

    def test_valid_results(self):
        report = validate_result_records([valid_record()], {"task-1"})
        self.assertTrue(report["valid"])
        self.assertEqual(report["n_records"], 1)

    def test_duplicate_tasks_are_rejected(self):
        report = validate_result_records([valid_record(), valid_record()])
        self.assertFalse(report["valid"])
        self.assertTrue(any("Duplicate" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
