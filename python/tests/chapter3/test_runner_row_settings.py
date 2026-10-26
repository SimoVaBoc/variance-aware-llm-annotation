"""The two-arm runner takes its per-call settings from the manifest row.

The two arms send different caps and different temperatures, so those belong to
the row, not to the model. The model-level ``request_settings`` stays a fallback
for the single-arm manifests, which carry no per-row values.

Everything here is offline. The provider client is a fake, and one test patches
``socket.socket`` to prove no call leaves the process.
"""

import socket
import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fakes import FakeOpenAIClient, openai_response  # noqa: E402
from src.chapter3.execution import (  # noqa: E402
    RetryPolicy,
    execute_task,
    max_output_tokens_for,
    temperature_for,
)
from src.chapter3.providers import OpenAIAdapter, ProviderRequest  # noqa: E402


CAMUFFO_ROW = {
    "task_id": "chapter3_psm_v2__deepseek_v4_pro__cm_base__s01__CB001",
    "item_id": "CB001",
    "model_id": "deepseek_v4_pro",
    "api_model_requested": "deepseek/deepseek-v4-pro-0813",
    "prompt_id": "cm_base",
    "replicate_id": "1",
    "arm": "camuffo",
    "label_order": "10",
    "max_output_tokens": "1",
    "temperature_requested": "1",
    "text_sha256": "a" * 64,
    "prompt_sha256": "b" * 64,
    "config_sha256": "c" * 64,
}

CARLSON_ROW = dict(
    CAMUFFO_ROW,
    task_id="chapter3_psm_v2__deepseek_v4_pro__cb_t3_zero_shot__s01__CB001",
    prompt_id="cb_t3_zero_shot",
    arm="carlson",
    label_order=None,
    max_output_tokens="16",
    temperature_requested="0",
)

# What a single-arm manifest row looks like: no per-row settings at all.
LEGACY_ROW = {key: value for key, value in CAMUFFO_ROW.items()
              if key not in {"max_output_tokens", "temperature_requested", "arm", "label_order"}}

GLOBAL_SETTINGS = {"max_output_tokens": 16, "temperature_requested": 0.0}


def run_one(row, script, settings=GLOBAL_SETTINGS):
    client = FakeOpenAIClient(script)
    adapter = OpenAIAdapter(client)
    request = ProviderRequest(
        api_model=row["api_model_requested"],
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=max_output_tokens_for(row, settings),
        temperature=temperature_for(row, settings),
        settings={},
    )
    record = execute_task(
        row,
        adapter,
        request,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        sleep=lambda _: None,
        jitter_source=lambda: 0.0,
    )
    return record, client.responder.calls


class CapTests(unittest.TestCase):
    def test_a_camuffo_row_sends_a_cap_of_one(self):
        _, calls = run_one(CAMUFFO_ROW, [openai_response("1")])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_completion_tokens"], 1)

    def test_a_carlson_row_sends_a_cap_of_sixteen(self):
        _, calls = run_one(CARLSON_ROW, [openai_response("0")])
        self.assertEqual(calls[0]["max_completion_tokens"], 16)

    def test_the_row_cap_beats_the_global_setting(self):
        """The global value is 16; the Camuffo row must still send 1."""

        self.assertEqual(GLOBAL_SETTINGS["max_output_tokens"], 16)
        self.assertEqual(max_output_tokens_for(CAMUFFO_ROW, GLOBAL_SETTINGS), 1)
        _, calls = run_one(CAMUFFO_ROW, [openai_response("1")])
        self.assertEqual(calls[0]["max_completion_tokens"], 1)

    def test_a_legacy_row_falls_back_to_the_model_setting(self):
        self.assertEqual(max_output_tokens_for(LEGACY_ROW, GLOBAL_SETTINGS), 16)

    def test_a_blank_cell_is_treated_as_absent(self):
        """A manifest read back from CSV yields empty strings, not None."""

        blank = dict(CAMUFFO_ROW, max_output_tokens="")
        self.assertEqual(max_output_tokens_for(blank, GLOBAL_SETTINGS), 16)

    def test_the_record_reports_the_cap_actually_used(self):
        record, _ = run_one(CAMUFFO_ROW, [openai_response("1")])
        self.assertEqual(record["max_output_tokens"], 1)


class TemperatureTests(unittest.TestCase):
    def test_the_two_arms_send_their_own_temperature(self):
        _, camuffo_calls = run_one(CAMUFFO_ROW, [openai_response("1")])
        _, carlson_calls = run_one(CARLSON_ROW, [openai_response("0")])
        self.assertEqual(camuffo_calls[0]["temperature"], 1.0)
        self.assertEqual(carlson_calls[0]["temperature"], 0.0)

    def test_an_absent_temperature_omits_the_parameter(self):
        """Where the control is unavailable, nothing is simulated."""

        row = dict(CAMUFFO_ROW, temperature_requested=None)
        self.assertIsNone(temperature_for(row, {}))
        _, calls = run_one(row, [openai_response("1")], settings={})
        self.assertNotIn("temperature", calls[0])

    def test_the_record_reports_what_went_on_the_wire(self):
        record, _ = run_one(CAMUFFO_ROW, [openai_response("1")])
        self.assertEqual(record["temperature_requested"], 1.0)
        self.assertEqual(record["temperature_parameter_sent"], 1.0)

    def test_an_omitted_parameter_is_recorded_as_such(self):
        row = dict(CAMUFFO_ROW, temperature_requested=None)
        record, _ = run_one(row, [openai_response("1")], settings={})
        self.assertIsNone(record["temperature_parameter_sent"])
        self.assertEqual(record["temperature_control"], "unavailable_or_omitted")


class FinishReasonTests(unittest.TestCase):
    def test_finish_reason_is_recorded_on_a_success(self):
        record, _ = run_one(CAMUFFO_ROW, [openai_response("1", finish_reason="stop")])
        self.assertEqual(record["finish_reason"], "stop")
        self.assertTrue(record["finish_reason_reported"])

    def test_finish_reason_is_recorded_on_a_parse_error(self):
        """A one-token cap makes truncation a plausible cause of a parse error."""

        record, _ = run_one(
            CAMUFFO_ROW, [openai_response("Th", finish_reason="length")]
        )
        self.assertEqual(record["status"], "parse_error")
        self.assertEqual(record["finish_reason"], "length")
        self.assertTrue(record["finish_reason_reported"])
        self.assertEqual(record["raw_response"], "Th")

    def test_an_unreported_finish_reason_is_null_not_invented(self):
        record, _ = run_one(CAMUFFO_ROW, [openai_response("1", finish_reason=None)])
        self.assertIsNone(record["finish_reason"])
        self.assertFalse(record["finish_reason_reported"])

    def test_the_field_is_present_even_without_a_completion(self):
        from _fakes import StatusError

        record, _ = run_one(CAMUFFO_ROW, [StatusError("boom", 503)] * 3)
        self.assertEqual(record["status"], "api_error")
        self.assertIn("finish_reason", record)
        self.assertIsNone(record["finish_reason"])
        self.assertFalse(record["finish_reason_reported"])


class NoNetworkTests(unittest.TestCase):
    def test_none_of_this_opens_a_socket(self):
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("no call may leave the process")
        ):
            record, calls = run_one(CARLSON_ROW, [openai_response("0")])
        self.assertEqual(record["parsed_label"], 0)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
