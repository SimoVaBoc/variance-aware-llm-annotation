"""Provider adapter tests. Every client is injected and no socket is opened."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = PROJECT_ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fakes import (  # noqa: E402
    FakeAnthropicClient,
    FakeOpenAIClient,
    RateLimitError,
    StatusError,
    anthropic_response,
    openai_response,
    openai_response_object,
)
from src.chapter3.providers import (  # noqa: E402
    ADAPTER_REGISTRY,
    AnthropicAdapter,
    DeepSeekAdapter,
    FatalProviderError,
    MissingCredentialError,
    OpenAIAdapter,
    OpenRouterAdapter,
    ProviderRequest,
    RetryableProviderError,
    api_key_env_var_for,
    build_adapter,
    classify_exception,
    resolve_api_key,
)


def request(**overrides):
    defaults = dict(
        api_model="gpt-5.6-terra",
        system_prompt="Return exactly one binary classification label: 0 or 1.",
        user_prompt="Prompt\n\nCampaign text",
        max_output_tokens=16,
        temperature=None,
        settings={"reasoning_effort": "none", "max_output_tokens": 16, "temperature": None},
    )
    defaults.update(overrides)
    return ProviderRequest(**defaults)


class AdapterInterfaceTests(unittest.TestCase):
    def test_every_configured_provider_has_an_adapter(self):
        self.assertEqual(
            set(ADAPTER_REGISTRY),
            {"openai", "anthropic", "deepseek", "openrouter", "huggingface"},
        )

    def test_each_adapter_declares_its_own_key_variable(self):
        self.assertEqual(api_key_env_var_for("openai"), "OPENAI_API_KEY")
        self.assertEqual(api_key_env_var_for("anthropic"), "ANTHROPIC_API_KEY")
        self.assertEqual(api_key_env_var_for("deepseek"), "DEEPSEEK_API_KEY")

    def test_adapter_requires_an_injected_client(self):
        with self.assertRaises(ValueError):
            OpenAIAdapter(None)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(FatalProviderError):
            build_adapter("mistral", object())

    def test_all_adapters_return_the_same_response_shape(self):
        openai = OpenAIAdapter(FakeOpenAIClient([openai_response("1")]))
        anthropic = AnthropicAdapter(FakeAnthropicClient([anthropic_response("1")]))
        deepseek = DeepSeekAdapter(FakeOpenAIClient([openai_response("1", model="deepseek-v4-pro")]))

        for adapter in (openai, anthropic, deepseek):
            response = adapter.complete(request())
            self.assertEqual(response.text, "1")
            self.assertIsNotNone(response.api_model_returned)
            self.assertIsNotNone(response.provider_request_id)
            self.assertIsInstance(response.input_tokens, int)
            self.assertIsInstance(response.output_tokens, int)
            self.assertIn("model", response.request_settings)


class OpenAIAdapterTests(unittest.TestCase):
    def test_payload_uses_the_documented_surface(self):
        client = FakeOpenAIClient([openai_response("0")])
        OpenAIAdapter(client).complete(request())
        (call,) = client.calls
        self.assertEqual(call["model"], "gpt-5.6-terra")
        self.assertEqual(call["max_completion_tokens"], 16)
        self.assertEqual(call["reasoning_effort"], "none")
        self.assertEqual(call["messages"][0]["role"], "system")
        self.assertEqual(call["messages"][1]["role"], "user")

    def test_null_temperature_is_not_sent(self):
        client = FakeOpenAIClient([openai_response("0")])
        OpenAIAdapter(client).complete(request(temperature=None))
        self.assertNotIn("temperature", client.calls[0])

    def test_explicit_temperature_is_sent(self):
        client = FakeOpenAIClient([openai_response("0")])
        OpenAIAdapter(client).complete(request(temperature=0.0))
        self.assertEqual(client.calls[0]["temperature"], 0.0)

    def test_metadata_is_preserved(self):
        client = FakeOpenAIClient([openai_response("1")])
        response = OpenAIAdapter(client).complete(request())
        self.assertEqual(response.api_model_returned, "gpt-5.6-terra-2026-01-01")
        self.assertEqual(response.provider_request_id, "req-openai-1")
        self.assertEqual(response.system_fingerprint, "fp_abc123")
        self.assertEqual(response.input_tokens, 120)
        self.assertEqual(response.output_tokens, 1)
        self.assertEqual(response.stop_reason, "stop")

    def test_attribute_style_sdk_objects_are_supported(self):
        client = FakeOpenAIClient([openai_response_object("1")])
        response = OpenAIAdapter(client).complete(request())
        self.assertEqual(response.text, "1")
        self.assertEqual(response.provider_request_id, "req-openai-1")
        self.assertEqual(response.input_tokens, 120)

    def test_empty_choices_is_fatal(self):
        payload = openai_response("1")
        payload["choices"] = []
        client = FakeOpenAIClient([payload])
        with self.assertRaises(FatalProviderError):
            OpenAIAdapter(client).complete(request())


class AnthropicAdapterTests(unittest.TestCase):
    def test_payload_uses_the_messages_surface(self):
        client = FakeAnthropicClient([anthropic_response("1")])
        AnthropicAdapter(client).complete(
            request(api_model="claude-sonnet-5", settings={"thinking": "disabled"})
        )
        (call,) = client.calls
        self.assertEqual(call["model"], "claude-sonnet-5")
        self.assertEqual(call["max_tokens"], 16)
        self.assertEqual(call["thinking"], {"type": "disabled"})
        self.assertEqual(call["system"], request().system_prompt)
        self.assertEqual(call["messages"], [{"role": "user", "content": request().user_prompt}])

    def test_non_default_sampling_is_omitted_when_null(self):
        client = FakeAnthropicClient([anthropic_response("1")])
        AnthropicAdapter(client).complete(request(temperature=None))
        self.assertNotIn("temperature", client.calls[0])

    def test_text_blocks_are_concatenated(self):
        payload = anthropic_response("1")
        payload["content"] = [{"type": "text", "text": "1"}, {"type": "text", "text": ""}]
        client = FakeAnthropicClient([payload])
        response = AnthropicAdapter(client).complete(request())
        self.assertEqual(response.text, "1")

    def test_missing_text_block_is_fatal(self):
        payload = anthropic_response("1")
        payload["content"] = [{"type": "thinking", "thinking": "..."}]
        client = FakeAnthropicClient([payload])
        with self.assertRaises(FatalProviderError):
            AnthropicAdapter(client).complete(request())


class DeepSeekAdapterTests(unittest.TestCase):
    def test_uses_max_tokens_not_max_completion_tokens(self):
        client = FakeOpenAIClient([openai_response("1")])
        DeepSeekAdapter(client).complete(
            request(api_model="deepseek-v4-pro", settings={"thinking": "disabled"})
        )
        (call,) = client.calls
        self.assertEqual(call["max_tokens"], 16)
        self.assertNotIn("max_completion_tokens", call)
        self.assertEqual(call["thinking"], {"type": "disabled"})


class OpenRouterAdapterTests(unittest.TestCase):
    def test_registered_with_its_own_key_variable(self):
        self.assertEqual(api_key_env_var_for("openrouter"), "OPENROUTER_API_KEY")

    def test_uses_the_openai_compatible_surface_with_max_tokens(self):
        client = FakeOpenAIClient([openai_response("1", model="deepseek/deepseek-chat")])
        OpenRouterAdapter(client).complete(request(api_model="deepseek/deepseek-chat"))
        (call,) = client.calls
        self.assertEqual(call["model"], "deepseek/deepseek-chat")
        self.assertEqual(call["max_tokens"], 16)
        self.assertNotIn("max_completion_tokens", call)

    def test_openrouter_extensions_travel_in_extra_body(self):
        """The typed OpenAI client rejects them as top-level keyword arguments."""

        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(
            request(
                settings={
                    "reasoning": "disabled",
                    "openrouter_provider_only": ["DeepSeek"],
                }
            )
        )
        (call,) = client.calls
        self.assertNotIn("reasoning", call)
        self.assertNotIn("provider", call)
        self.assertIn("extra_body", call)

    def test_reasoning_is_disabled_with_the_openrouter_parameter(self):
        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(request(settings={"reasoning": "disabled"}))
        (call,) = client.calls
        self.assertEqual(call["extra_body"]["reasoning"], {"enabled": False})
        self.assertNotIn("reasoning_effort", call)

    def test_reasoning_object_is_omitted_when_not_disabled(self):
        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(request(settings={}))
        extra_body = client.calls[0]["extra_body"]
        self.assertNotIn("reasoning", extra_body)
        self.assertNotIn("provider", extra_body)

    def test_usage_accounting_is_always_requested(self):
        """Telemetry, not generation: it asks for the credited cost back."""

        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(request(settings={}))
        self.assertEqual(client.calls[0]["extra_body"]["usage"], {"include": True})

    def test_upstream_provider_can_be_pinned_with_fallbacks_off(self):
        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(
            request(
                settings={
                    "openrouter_provider_only": ["DeepSeek"],
                    "openrouter_allow_fallbacks": False,
                }
            )
        )
        (call,) = client.calls
        self.assertEqual(
            call["extra_body"]["provider"], {"only": ["DeepSeek"], "allow_fallbacks": False}
        )

    def test_fallbacks_default_to_off_when_a_provider_is_pinned(self):
        """Pinning must not silently permit a fallback to another backend."""

        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(
            request(settings={"openrouter_provider_only": ["DeepSeek"]})
        )
        self.assertIs(client.calls[0]["extra_body"]["provider"]["allow_fallbacks"], False)

    def test_no_routing_block_when_no_provider_is_pinned(self):
        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(request(settings={"reasoning": "disabled"}))
        self.assertNotIn("provider", client.calls[0].get("extra_body", {}))

    def test_null_temperature_is_not_sent(self):
        client = FakeOpenAIClient([openai_response("1")])
        OpenRouterAdapter(client).complete(request(temperature=None))
        self.assertNotIn("temperature", client.calls[0])

    def test_records_the_upstream_provider_that_served_the_call(self):
        payload = openai_response("1", model="deepseek/deepseek-chat")
        payload["provider"] = "DeepSeek"
        client = FakeOpenAIClient([payload])
        response = OpenRouterAdapter(client).complete(request())
        self.assertEqual(response.upstream_provider, "DeepSeek")
        self.assertEqual(response.api_model_returned, "deepseek/deepseek-chat")

    def test_missing_upstream_provider_is_not_invented(self):
        client = FakeOpenAIClient([openai_response("1")])
        response = OpenRouterAdapter(client).complete(request())
        self.assertIsNone(response.upstream_provider)

    def test_first_party_adapters_report_no_upstream_router(self):
        client = FakeOpenAIClient([openai_response("1")])
        self.assertIsNone(OpenAIAdapter(client).complete(request()).upstream_provider)


class ErrorClassificationTests(unittest.TestCase):
    def test_rate_limit_status_is_retryable(self):
        error = classify_exception(StatusError("slow down", 429))
        self.assertIsInstance(error, RetryableProviderError)
        self.assertEqual(error.status_code, 429)

    def test_server_error_is_retryable(self):
        self.assertIsInstance(classify_exception(StatusError("boom", 503)), RetryableProviderError)

    def test_bad_request_is_fatal(self):
        self.assertIsInstance(classify_exception(StatusError("bad", 400)), FatalProviderError)

    def test_authentication_error_is_fatal(self):
        self.assertIsInstance(classify_exception(StatusError("nope", 401)), FatalProviderError)

    def test_known_transient_class_names_are_retryable(self):
        self.assertIsInstance(classify_exception(RateLimitError("limit")), RetryableProviderError)

    def test_builtin_transport_errors_are_retryable(self):
        self.assertIsInstance(classify_exception(TimeoutError("timeout")), RetryableProviderError)
        self.assertIsInstance(classify_exception(ConnectionError("reset")), RetryableProviderError)

    def test_unknown_errors_default_to_fatal(self):
        self.assertIsInstance(classify_exception(ValueError("odd")), FatalProviderError)

    def test_adapter_wraps_client_exceptions(self):
        client = FakeOpenAIClient([StatusError("slow down", 429)])
        with self.assertRaises(RetryableProviderError):
            OpenAIAdapter(client).complete(request())

    def test_error_messages_never_include_a_key(self):
        error = classify_exception(StatusError("invalid api key sk-secret-value", 401))
        self.assertIsInstance(error, FatalProviderError)
        # The adapter does not inject credentials into messages; it only
        # forwards the provider's own text.
        self.assertNotIn("OPENAI_API_KEY", str(error))


class CredentialTests(unittest.TestCase):
    def test_key_is_read_from_the_environment(self):
        self.assertEqual(resolve_api_key("OPENAI_API_KEY", {"OPENAI_API_KEY": "sk-test"}), "sk-test")

    def test_missing_key_raises_without_revealing_a_value(self):
        with self.assertRaises(MissingCredentialError) as context:
            resolve_api_key("OPENAI_API_KEY", {})
        self.assertIn("OPENAI_API_KEY", str(context.exception))
        self.assertIn("environment", str(context.exception))

    def test_blank_key_is_treated_as_missing(self):
        with self.assertRaises(MissingCredentialError):
            resolve_api_key("ANTHROPIC_API_KEY", {"ANTHROPIC_API_KEY": "   "})

    def test_key_value_is_not_echoed_in_the_error(self):
        with self.assertRaises(MissingCredentialError) as context:
            resolve_api_key("DEEPSEEK_API_KEY", {"DEEPSEEK_API_KEY": ""})
        self.assertNotIn("sk-", str(context.exception))


if __name__ == "__main__":
    unittest.main()
