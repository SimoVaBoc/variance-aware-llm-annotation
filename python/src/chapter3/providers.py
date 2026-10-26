"""Provider adapters for the Chapter 3 annotation pipeline.

This module defines one interface that every provider implements and returns a
single normalized response shape. It performs no network I/O by itself and does
not import a provider SDK at import time. Every adapter receives its transport
client through dependency injection, so the whole layer can be exercised with
fake clients and never contacts an external API during tests.

The concrete request shapes below follow the documented chat interfaces for each
provider, but they must be re-verified against the live provider documentation
immediately before the first paid call. See ``docs/chapter3_handoff.md``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Mapping

from . import first_party as fp
from . import huggingface as hf


# Status codes that represent a transient condition rather than a bad request.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# SDK exception class names that are transient across the three providers.
RETRYABLE_EXCEPTION_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "InternalServerError",
        "PoolTimeout",
        "RateLimitError",
        "ReadTimeout",
        "RemoteProtocolError",
        "ServiceUnavailableError",
        "TimeoutException",
    }
)


class ProviderError(RuntimeError):
    """Base class for adapter-level failures.

    ``retryable`` drives the runner's backoff decision. It never indicates that
    a retry produces an additional independent sample.
    """

    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetryableProviderError(ProviderError):
    """A transport, rate-limit or server-side failure worth retrying."""

    retryable: ClassVar[bool] = True


class FatalProviderError(ProviderError):
    """A request-level failure that retrying cannot fix."""

    retryable: ClassVar[bool] = False


class MissingCredentialError(RuntimeError):
    """Raised when a required API key environment variable is absent."""


@dataclass(frozen=True)
class ProviderRequest:
    """A fully resolved single-item annotation request."""

    api_model: str
    # None means the arm sends no system message at all. The Carlson prompts
    # carry their own framing, so adding an empty or null system message would
    # both alter the replication and be rejected by the API schema.
    system_prompt: str | None
    user_prompt: str
    max_output_tokens: int
    temperature: float | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """The common response shape returned by every adapter."""

    text: str
    api_model_returned: str | None = None
    provider_request_id: str | None = None
    system_fingerprint: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None
    # Set when the call goes through an aggregator that reports which upstream
    # provider actually served it. Essential provenance when routing.
    upstream_provider: str | None = None
    # Reported only by some providers. None means "not reported", never zero:
    # absence of the field does not demonstrate that no reasoning was done.
    reasoning_tokens: int | None = None
    reasoning_tokens_reported: bool = False
    # Reported by OpenRouter when the request asks for usage accounting.
    cost: float | None = None
    cost_reported: bool = False
    request_settings: Mapping[str, Any] = field(default_factory=dict)

    # Routing provenance, set by adapters that reach a model through a gateway.
    # These record what was *asked for*, and stay None on a direct first-party
    # call. They never stand in for `upstream_provider`, which records what
    # actually served the request and is left None when nobody says.
    gateway: str | None = None
    requested_model: str | None = None
    requested_provider: str | None = None

    # Where `upstream_provider` was read from. A gateway may name the serving
    # backend in the body, in a header, or nowhere, and the three are not
    # equivalent evidence. None here with a provider set would be a bug.
    upstream_provider_source: str | None = None

    # Where `cost` came from, and whether the provider calls it a settled
    # charge or its own estimate. OpenRouter reports what it credited;
    # DeepInfra reports an `estimated_cost`. Both are "reported", and summing
    # them as though they meant the same thing would overstate the second.
    cost_source: str | None = None
    cost_is_provider_estimate: bool = False

    # Prompt tokens the provider served from cache. They are billed at a lower
    # rate, so a cost reconstructed without them is wrong. None means the
    # provider did not say, which is not the same as zero cached tokens.
    cached_input_tokens: int | None = None

    # The HTTP status of the successful response, when the adapter can see it.
    # A client that only returns a parsed object cannot, so None means "not
    # observed", never "no status". The status of a *failed* call comes from
    # the ProviderError instead, and the runner records whichever it has.
    http_status: int | None = None

    # A price computed locally from token counts and a dated tariff snapshot,
    # for gateways that bill without reporting what they charged. It is kept
    # apart from `cost` on purpose: `cost` is what the provider said it took,
    # this is what we believe it took, and the two must never be summed or
    # substituted for one another. `cost_estimate_basis` names the snapshot.
    cost_estimated: float | None = None
    cost_estimate_basis: str | None = None

    # The usage field the reasoning count was read from, so a count from one API
    # is never mistaken for one from another. None when nothing was reported.
    reasoning_tokens_source: str | None = None

    # Prompt tokens written to the cache on this call, billed differently from
    # both ordinary input and cache reads. None means not reported.
    cache_write_input_tokens: int | None = None

    # Anthropic only: content blocks of type ``thinking`` and
    # ``redacted_thinking`` found in the response. None where the API has no
    # such blocks; zero means the response was inspected and carried none.
    thinking_blocks: int | None = None
    redacted_thinking_blocks: int | None = None


#: Request setting that keeps every sampling parameter off the wire. Used where
#: a provider documents that it rejects non-default values: the parameter is
#: omitted, never simulated, and the record keeps what the design asked for.
SAMPLING_OMIT = "omit"


def sampling_parameters_omitted(settings: Mapping[str, Any]) -> bool:
    """True when the configuration says no sampling parameter may be sent."""

    return settings.get("sampling_parameters") == SAMPLING_OMIT


def temperature_on_the_wire(request: "ProviderRequest") -> float | None:
    """The temperature actually sent for this request, or None if none is."""

    if sampling_parameters_omitted(request.settings):
        return None
    return request.temperature


def chat_messages(request: ProviderRequest) -> list[dict[str, str]]:
    """Build the message list for an OpenAI-style chat request.

    A system message is emitted only when the request carries one. The Carlson
    arm sends none: its published prompts carry their own framing, so a system
    message would alter the replication, and ``content: null`` is not valid
    under the chat schema in any case.
    """

    messages: list[dict[str, str]] = []
    if request.system_prompt is not None:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.user_prompt})
    return messages


def classify_exception(error: BaseException) -> ProviderError:
    """Translate an arbitrary SDK or transport exception into a ProviderError.

    Classification is structural rather than based on imported SDK classes, so
    the adapters stay decoupled from any specific provider package version.
    """

    if isinstance(error, ProviderError):
        return error

    status_code = getattr(error, "status_code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None

    name = type(error).__name__
    message = f"{name}: {error}"

    if status_code is not None:
        if status_code in RETRYABLE_STATUS_CODES:
            return RetryableProviderError(message, status_code=status_code)
        return FatalProviderError(message, status_code=status_code)

    if name in RETRYABLE_EXCEPTION_NAMES or isinstance(error, (TimeoutError, ConnectionError)):
        return RetryableProviderError(message)

    return FatalProviderError(message)


def resolve_api_key(env_var: str, environ: Mapping[str, str] | None = None) -> str:
    """Read an API key from the environment only.

    The key value is never returned in an exception message or logged.
    """

    source = os.environ if environ is None else environ
    value = (source.get(env_var) or "").strip()
    if not value:
        raise MissingCredentialError(
            f"Environment variable {env_var} is not set. "
            "API keys are read from the environment only and are never stored in "
            "the repository or printed."
        )
    return value


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _get(payload: Any, key: str) -> Any:
    """Read ``key`` from either a mapping or an attribute-style SDK object."""

    if isinstance(payload, Mapping):
        return payload.get(key)
    return getattr(payload, key, None)


class ProviderAdapter(ABC):
    """One annotation call for one provider.

    Subclasses translate a :class:`ProviderRequest` into the provider's native
    request, and the provider's native response into a :class:`ProviderResponse`.
    They never parse the label; strict parsing is the runner's responsibility.
    """

    provider: ClassVar[str]
    api_key_env_var: ClassVar[str]

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError(
                f"{type(self).__name__} requires an injected client. "
                "No client is constructed implicitly."
            )
        self.client = client

    @abstractmethod
    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        """Return the exact keyword arguments sent to the provider client."""

    @abstractmethod
    def parse_response(self, payload: Any) -> ProviderResponse:
        """Translate a native provider response into the common shape."""

    @abstractmethod
    def _invoke(self, payload: Mapping[str, Any]) -> Any:
        """Call the injected client. Isolated so tests can assert the surface."""

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload = self.build_payload(request)
        try:
            native = self._invoke(payload)
        except BaseException as error:  # noqa: BLE001 - re-raised as ProviderError
            raise classify_exception(error) from error
        response = self.parse_response(native)
        # `replace` copies every field, so a field added to ProviderResponse is
        # carried through instead of being silently dropped here.
        return replace(response, request_settings=dict(payload))


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI chat completions interface."""

    provider = "openai"
    api_key_env_var = "OPENAI_API_KEY"

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.api_model,
            "messages": chat_messages(request),
            "max_completion_tokens": request.max_output_tokens,
        }
        # A null temperature means "use the documented provider default", which
        # the design records rather than overrides. A configuration that omits
        # sampling parameters sends none, whatever the row asked for.
        temperature = temperature_on_the_wire(request)
        if temperature is not None:
            payload["temperature"] = temperature
        reasoning_effort = request.settings.get("reasoning_effort")
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        return payload

    def _invoke(self, payload: Mapping[str, Any]) -> Any:
        return self.client.chat.completions.create(**payload)

    #: Where the documented Chat Completions usage block keeps each count.
    REASONING_SOURCE: ClassVar[str] = "usage.completion_tokens_details.reasoning_tokens"

    def parse_response(self, payload: Any) -> ProviderResponse:
        choices = _get(payload, "choices") or []
        if not choices:
            raise FatalProviderError("OpenAI response contained no choices")
        message = _get(choices[0], "message")
        text = _get(message, "content") if message is not None else None
        usage = _get(payload, "usage")
        completion_details = _get(usage, "completion_tokens_details") if usage is not None else None
        prompt_details = _get(usage, "prompt_tokens_details") if usage is not None else None
        # Null when absent, never zero: a missing count does not show that no
        # reasoning took place.
        reasoning = (
            _as_int(_get(completion_details, "reasoning_tokens"))
            if completion_details is not None else None
        )
        return ProviderResponse(
            text="" if text is None else str(text),
            api_model_returned=_as_str(_get(payload, "model")),
            provider_request_id=_as_str(_get(payload, "id")),
            system_fingerprint=_as_str(_get(payload, "system_fingerprint")),
            input_tokens=_as_int(_get(usage, "prompt_tokens")) if usage is not None else None,
            output_tokens=(
                _as_int(_get(usage, "completion_tokens")) if usage is not None else None
            ),
            stop_reason=_as_str(_get(choices[0], "finish_reason")),
            reasoning_tokens=reasoning,
            reasoning_tokens_reported=reasoning is not None,
            reasoning_tokens_source=self.REASONING_SOURCE if reasoning is not None else None,
            cached_input_tokens=(
                _as_int(_get(prompt_details, "cached_tokens"))
                if prompt_details is not None else None
            ),
            cache_write_input_tokens=(
                _as_int(_get(prompt_details, "cache_write_tokens"))
                if prompt_details is not None else None
            ),
        )

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = super().complete(request)
        # Only the first-party route is priced here. The gateways that inherit
        # this adapter report or estimate their own cost.
        if self.provider != OpenAIAdapter.provider:
            return response
        snapshot = fp.snapshot_for(self.provider, request.api_model)
        estimated = None if snapshot is None else fp.estimate_openai_cost(
            snapshot,
            prompt_tokens=response.input_tokens,
            completion_tokens=response.output_tokens,
            cached_tokens=response.cached_input_tokens,
            cache_write_tokens=response.cache_write_input_tokens,
        )
        return replace(
            response,
            cost_estimated=estimated,
            cost_estimate_basis=None if estimated is None else snapshot,
        )


class AnthropicAdapter(ProviderAdapter):
    """Adapter for the Anthropic messages interface."""

    provider = "anthropic"
    api_key_env_var = "ANTHROPIC_API_KEY"

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.api_model,
            "messages": [{"role": "user", "content": request.user_prompt}],
            "max_tokens": request.max_output_tokens,
        }
        # Anthropic takes the system prompt as a top-level field. It is omitted
        # entirely when the arm sends none.
        if request.system_prompt is not None:
            payload["system"] = request.system_prompt
        # The temperature is sent only when the configuration allows sampling
        # parameters. Where the provider documents that it rejects non-default
        # values, the configuration sets sampling_parameters to "omit" and
        # temperature, top_p and top_k all stay off the wire.
        temperature = temperature_on_the_wire(request)
        if temperature is not None:
            payload["temperature"] = temperature
        if request.settings.get("thinking") == "disabled":
            payload["thinking"] = {"type": "disabled"}
        return payload

    def _invoke(self, payload: Mapping[str, Any]) -> Any:
        return self.client.messages.create(**payload)

    REASONING_SOURCE: ClassVar[str] = "usage.output_tokens_details.thinking_tokens"
    THINKING_BLOCK_TYPES: ClassVar[tuple[str, str]] = ("thinking", "redacted_thinking")

    def parse_response(self, payload: Any) -> ProviderResponse:
        blocks = _get(payload, "content") or []
        types = [_get(block, "type") for block in blocks]
        thinking = types.count("thinking")
        redacted = types.count("redacted_thinking")
        texts = [
            str(_get(block, "text"))
            for block in blocks
            if _get(block, "type") == "text" and _get(block, "text") is not None
        ]
        if not texts:
            raise FatalProviderError(
                "Anthropic response contained no text block "
                f"(thinking blocks: {thinking}, redacted_thinking blocks: {redacted})"
            )
        usage = _get(payload, "usage")
        details = _get(usage, "output_tokens_details") if usage is not None else None
        # Null when absent, never zero. output_tokens stays the inclusive total.
        reasoning = _as_int(_get(details, "thinking_tokens")) if details is not None else None
        breakdown = _get(usage, "cache_creation") if usage is not None else None
        self._last_cache_write_breakdown = (
            {key: _get(breakdown, key)
             for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")}
            if breakdown is not None else None
        )
        return ProviderResponse(
            text="".join(texts),
            api_model_returned=_as_str(_get(payload, "model")),
            provider_request_id=_as_str(_get(payload, "id")),
            system_fingerprint=None,
            input_tokens=_as_int(_get(usage, "input_tokens")) if usage is not None else None,
            output_tokens=_as_int(_get(usage, "output_tokens")) if usage is not None else None,
            stop_reason=_as_str(_get(payload, "stop_reason")),
            reasoning_tokens=reasoning,
            reasoning_tokens_reported=reasoning is not None,
            reasoning_tokens_source=self.REASONING_SOURCE if reasoning is not None else None,
            cached_input_tokens=(
                _as_int(_get(usage, "cache_read_input_tokens")) if usage is not None else None
            ),
            cache_write_input_tokens=(
                _as_int(_get(usage, "cache_creation_input_tokens")) if usage is not None else None
            ),
            thinking_blocks=thinking,
            redacted_thinking_blocks=redacted,
        )

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self._last_cache_write_breakdown = None
        response = super().complete(request)
        snapshot = fp.snapshot_for(self.provider, request.api_model)
        estimated = None if snapshot is None else fp.estimate_anthropic_cost(
            snapshot,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_read_tokens=response.cached_input_tokens,
            cache_write_tokens=response.cache_write_input_tokens,
            cache_write_breakdown=self._last_cache_write_breakdown,
        )
        return replace(
            response,
            cost_estimated=estimated,
            cost_estimate_basis=None if estimated is None else snapshot,
        )


class DeepSeekAdapter(OpenAIAdapter):
    """Adapter for the DeepSeek chat interface.

    DeepSeek documents an OpenAI-compatible chat completions surface, so the
    response translation is inherited. The exact DeepSeek model is still
    ``proposed_pending_confirmation`` in the frozen configuration, and the
    execution layer refuses live calls until that decision is recorded.
    """

    provider = "deepseek"
    api_key_env_var = "DEEPSEEK_API_KEY"

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload = super().build_payload(request)
        # DeepSeek uses the older max_tokens spelling on its compatible surface.
        payload["max_tokens"] = payload.pop("max_completion_tokens")
        if request.settings.get("thinking") == "disabled":
            payload["thinking"] = {"type": "disabled"}
        return payload


class OpenRouterAdapter(OpenAIAdapter):
    """Adapter for the OpenRouter aggregator.

    OpenRouter exposes an OpenAI-compatible chat completions surface, so the
    request and response translation is inherited. It additionally reports which
    upstream provider served the request, which is recorded because a router can
    dispatch the same model identifier to different backends between calls.
    That weaker version guarantee is a methodological trade-off and must be an
    explicitly recorded choice, not a silent default.
    """

    provider = "openrouter"
    api_key_env_var = "OPENROUTER_API_KEY"

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        settings = request.settings
        payload: dict[str, Any] = {
            "model": request.api_model,
            "messages": chat_messages(request),
            "max_tokens": request.max_output_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        # `reasoning` and `provider` are OpenRouter extensions that the typed
        # OpenAI client rejects as unexpected keyword arguments. They travel in
        # extra_body, which the SDK merges into the JSON request body.
        extra_body: dict[str, Any] = {}

        # OpenRouter uses its own `reasoning` object rather than the OpenAI
        # `reasoning_effort` field. Leaving reasoning on would let the model
        # spend the whole 16-token output budget on hidden reasoning and return
        # empty content, which the strict parser correctly rejects.
        if settings.get("reasoning") == "disabled":
            extra_body["reasoning"] = {"enabled": False}

        # Pinning the upstream provider keeps quantization, sampling defaults
        # and the served weights constant across the whole run. Without it the
        # router may silently move between fp8, fp4 and unknown backends.
        only = settings.get("openrouter_provider_only")
        if only:
            extra_body["provider"] = {
                "only": list(only),
                "allow_fallbacks": bool(settings.get("openrouter_allow_fallbacks", False)),
            }

        # Accounting, not generation. It asks OpenRouter to return the usage
        # block with the credited cost, and changes nothing about how the model
        # is sampled. The manifest's payload_sha256 covers the experimental
        # payload only, so this field does not and must not alter it.
        extra_body["usage"] = {"include": True}

        if extra_body:
            payload["extra_body"] = extra_body
        return payload

    def parse_response(self, payload: Any) -> ProviderResponse:
        response = super().parse_response(payload)
        usage = _get(payload, "usage")

        # Never assume zero. A provider that does not report a figure leaves it
        # null, with the matching *_reported flag false, so that "not reported"
        # stays distinguishable from "reported as none".
        reasoning_tokens = None
        if usage is not None:
            details = _get(usage, "completion_tokens_details")
            if details is not None:
                reasoning_tokens = _as_int(_get(details, "reasoning_tokens"))
            if reasoning_tokens is None:
                reasoning_tokens = _as_int(_get(usage, "reasoning_tokens"))

        cost = None
        if usage is not None:
            raw_cost = _get(usage, "cost")
            if raw_cost is not None:
                try:
                    cost = float(raw_cost)
                except (TypeError, ValueError):
                    cost = None

        upstream = _as_str(_get(payload, "provider"))
        cached = None
        if usage is not None:
            details = _get(usage, "prompt_tokens_details")
            if details is not None:
                cached = _as_int(_get(details, "cached_tokens"))

        return ProviderResponse(
            text=response.text,
            api_model_returned=response.api_model_returned,
            provider_request_id=response.provider_request_id,
            system_fingerprint=response.system_fingerprint,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
            upstream_provider=upstream,
            upstream_provider_source=None if upstream is None else "response_body:provider",
            reasoning_tokens=reasoning_tokens,
            reasoning_tokens_reported=reasoning_tokens is not None,
            cost=cost,
            cost_reported=cost is not None,
            # OpenRouter returns what it credited, not a forecast of it.
            cost_source=None if cost is None else "openrouter_usage_cost_credited",
            cost_is_provider_estimate=False,
            cached_input_tokens=cached,
        )


class HuggingFaceRouterAdapter(OpenAIAdapter):
    """Adapter for the Hugging Face Inference Providers router.

    A second, parallel way of reaching the DeepSeek model, independent of the
    OpenRouter/Baidu route and sharing none of its verified properties. Baidu
    does not serve this model on Hugging Face at all, so the two routes cannot
    reach the same backend even in principle.

    The router is an OpenAI-compatible proxy, so the request and response
    translation is inherited. What it does not inherit is provenance. OpenRouter
    returns the serving provider and the credited cost in the response body; the
    Hugging Face router documents neither. The adapter therefore separates three
    things that are easy to conflate: what was asked for, what the response
    actually states, and what we computed ourselves from a dated price list.

    Everything this adapter refuses, it refuses loudly. A route whose backend or
    reasoning behaviour is chosen by a silent default is worse than no route.
    """

    provider = "huggingface"
    api_key_env_var = hf.TOKEN_ENV_VAR

    # Settings that belong to the OpenRouter route. Accepting them here would
    # quietly produce a request with none of the properties they name.
    FOREIGN_SETTINGS: ClassVar[tuple[str, ...]] = (
        "openrouter_provider_only",
        "openrouter_allow_fallbacks",
        "reasoning",
    )

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self._last_response_headers: dict[str, str] | None = None
        self._last_http_status: int | None = None

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        settings = request.settings
        try:
            _, pinned_provider = hf.split_model_and_provider(request.api_model)
        except hf.RouteConfigurationError as error:
            raise FatalProviderError(str(error)) from error

        for key in self.FOREIGN_SETTINGS:
            if settings.get(key) is not None:
                raise FatalProviderError(
                    f"Setting {key!r} belongs to the OpenRouter route and has no verified "
                    f"equivalent on the Hugging Face router. Sending it would not "
                    f"reproduce the property it names. Configure the Hugging Face route "
                    f"explicitly instead of reusing the OpenRouter settings block."
                )

        # The provider is pinned in the model id, which is what the router
        # reads. Declaring it a second time in the configuration is a
        # cross-check against a model id edited without the settings following.
        declared = settings.get("huggingface_provider")
        if declared is not None and str(declared).strip().lower() != pinned_provider:
            raise FatalProviderError(
                f"Configuration declares huggingface_provider={declared!r} but the model "
                f"id pins {pinned_provider!r}. Refusing a request whose routing the "
                f"configuration describes incorrectly."
            )
        if settings.get("huggingface_allow_fallbacks"):
            raise FatalProviderError(
                "huggingface_allow_fallbacks is set. This route exists to hold the "
                "serving backend constant; fallbacks are never enabled."
            )

        payload: dict[str, Any] = {
            "model": request.api_model.strip(),
            "messages": chat_messages(request),
            # The router documents the older max_tokens spelling.
            "max_tokens": request.max_output_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        # The reasoning gate. There is no default: the configuration states what
        # it decided, or no request is built. See huggingface.reasoning_gate_status.
        control = settings.get(hf.REASONING_CONTROL_KEY)
        if control is None:
            raise FatalProviderError(
                f"The Hugging Face route requires an explicit {hf.REASONING_CONTROL_KEY!r} "
                f"decision, one of {sorted(hf.REASONING_CONTROLS)}. The model card "
                f"documents no way to disable reasoning and the documented response "
                f"reports no reasoning tokens, so neither half of the OpenRouter "
                f"reasoning contract can be assumed here."
            )
        if control not in hf.REASONING_CONTROLS:
            raise FatalProviderError(
                f"Unknown {hf.REASONING_CONTROL_KEY} {control!r}; "
                f"expected one of {sorted(hf.REASONING_CONTROLS)}."
            )
        if control == hf.REASONING_EFFORT:
            effort = settings.get("reasoning_effort")
            if not effort:
                raise FatalProviderError(
                    f"{hf.REASONING_CONTROL_KEY}={control!r} requires an explicit "
                    f"reasoning_effort value. The router documents "
                    f"{list(hf.DOCUMENTED_REASONING_EFFORTS)} as common values and the "
                    f"model card documents {list(hf.MODEL_CARD_REASONING_EFFORTS)}; the "
                    f"adapter will not choose between them."
                )
            payload["reasoning_effort"] = str(effort)
        return payload

    def _invoke(self, payload: Mapping[str, Any]) -> Any:
        """Call the client through its raw-response accessor when it has one.

        The serving provider is named in a response header and nowhere in the
        body, so a client that only ever hands back the parsed object throws
        that provenance away. Going through ``with_raw_response`` keeps it,
        and falls back to the plain call for any client that lacks it, which
        keeps the adapter testable with a simple fake.
        """

        self._last_response_headers = None
        self._last_http_status = None
        completions = self.client.chat.completions
        raw_accessor = getattr(completions, "with_raw_response", None)
        if raw_accessor is None:
            return completions.create(**payload)
        raw = raw_accessor.create(**payload)
        headers = getattr(raw, "headers", None)
        if headers is not None:
            self._last_response_headers = {
                str(key).lower(): str(value) for key, value in dict(headers).items()
            }
        status = getattr(raw, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool):
            self._last_http_status = status
        return raw.parse()

    def parse_response(self, payload: Any) -> ProviderResponse:
        response = super().parse_response(payload)
        usage = _get(payload, "usage")

        # Read only. The router documents no provider field; if a backend passes
        # one through it is recorded, and otherwise this stays None. It is never
        # filled in from the provider we asked for, because the whole point of
        # the field is to show a substitution if one happened.
        upstream = _as_str(_get(payload, "provider"))

        # Likewise: the documented usage object has no reasoning token field. If
        # a provider volunteers one it is recorded; absence stays absence and is
        # never read as a zero.
        reasoning_tokens = None
        if usage is not None:
            details = _get(usage, "completion_tokens_details")
            if details is not None:
                reasoning_tokens = _as_int(_get(details, "reasoning_tokens"))
            if reasoning_tokens is None:
                reasoning_tokens = _as_int(_get(usage, "reasoning_tokens"))

        # DeepInfra returns `usage.estimated_cost`. It is the provider's own
        # figure and it is recorded as reported, with the estimate flag set, so
        # it is never mistaken for a credited charge the way OpenRouter's is.
        cost = None
        cached = None
        if usage is not None:
            raw_cost = _get(usage, "estimated_cost")
            if raw_cost is not None:
                try:
                    cost = float(raw_cost)
                except (TypeError, ValueError):
                    cost = None
            details = _get(usage, "prompt_tokens_details")
            if details is not None:
                cached = _as_int(_get(details, "cached_tokens"))

        return replace(
            response,
            upstream_provider=upstream,
            upstream_provider_source=None if upstream is None else hf.PROVIDER_SOURCE_BODY,
            reasoning_tokens=reasoning_tokens,
            reasoning_tokens_reported=reasoning_tokens is not None,
            cost=cost,
            cost_reported=cost is not None,
            cost_source=None if cost is None else hf.COST_SOURCE,
            cost_is_provider_estimate=cost is not None,
            cached_input_tokens=cached,
        )

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = super().complete(request)
        hub_model, pinned_provider = hf.split_model_and_provider(request.api_model)

        # The header is the route's only statement of which backend served the
        # call. It is used only when the body said nothing, and the source is
        # recorded either way so that "the body said so" and "a header said so"
        # stay distinguishable in the data.
        upstream = response.upstream_provider
        source = response.upstream_provider_source
        if upstream is None:
            from_header = (self._last_response_headers or {}).get(hf.PROVIDER_HEADER)
            if from_header:
                upstream, source = from_header, hf.PROVIDER_SOURCE_HEADER

        # Computed independently of whatever the provider said, so that the two
        # can be compared rather than one standing in for the other.
        estimated = hf.estimate_cost(
            pinned_provider, response.input_tokens, response.output_tokens
        )
        return replace(
            response,
            gateway=hf.GATEWAY,
            requested_model=hub_model,
            requested_provider=pinned_provider,
            upstream_provider=upstream,
            upstream_provider_source=source,
            cost_estimated=estimated,
            cost_estimate_basis=None if estimated is None else hf.TARIFF_SNAPSHOT_ID,
            http_status=self._last_http_status,
        )


ADAPTER_REGISTRY: dict[str, type[ProviderAdapter]] = {
    OpenAIAdapter.provider: OpenAIAdapter,
    AnthropicAdapter.provider: AnthropicAdapter,
    DeepSeekAdapter.provider: DeepSeekAdapter,
    OpenRouterAdapter.provider: OpenRouterAdapter,
    HuggingFaceRouterAdapter.provider: HuggingFaceRouterAdapter,
}


def adapter_class_for(provider: str) -> type[ProviderAdapter]:
    try:
        return ADAPTER_REGISTRY[provider]
    except KeyError:
        raise FatalProviderError(f"No adapter is registered for provider {provider!r}") from None


def build_adapter(provider: str, client: Any) -> ProviderAdapter:
    """Construct an adapter around an already-created client object."""

    return adapter_class_for(provider)(client)


def api_key_env_var_for(provider: str) -> str:
    return adapter_class_for(provider).api_key_env_var
