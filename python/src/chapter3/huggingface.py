"""Constants, tariffs and capability evidence for the Hugging Face router route.

This module is deliberately free of adapter logic and imports nothing else from
the package, so :mod:`chapter3.providers` can depend on it without a cycle.

The route it describes is a **second, parallel** way of reaching the DeepSeek
model. It does not replace the OpenRouter/Baidu route and does not inherit any
of its verified properties. The two routes share a nominal model name and
nothing else: a different gateway, a different serving provider, a different
billing account and a different, weaker response contract. Results produced
through them are not interchangeable and must never be pooled.

Every fact recorded here was read from a free Hugging Face metadata endpoint or
from the published API reference on 2026-09-30. Anything the metadata cannot
settle is marked ``unverified_requires_live_smoke`` rather than inferred from
the fact that the model is served at all.
"""

from __future__ import annotations

from typing import Any, Mapping


# --------------------------------------------------------------------------
# Routing identity
# --------------------------------------------------------------------------

GATEWAY = "huggingface_router"
ROUTER_BASE_URL = "https://router.huggingface.co/v1"
TOKEN_ENV_VAR = "HF_TOKEN"

# The Hub repository that the route targets. The dated suffix is part of the
# identity: an undated id would let the provider move between checkpoints.
HUB_MODEL_ID = "deepseek-ai/DeepSeek-V4-Pro-0813"

# Selection policies the router accepts in place of a provider name. Every one
# of them delegates the choice of backend to Hugging Face, at request time, by a
# criterion that can change between calls. All are refused.
POLICY_SUFFIXES = frozenset({"auto", "fastest", "cheapest", "preferred"})

#: The response header that names the backend that actually served the call.
#: The documented response *body* carries no provider field, so this header is
#: the only routing evidence the route offers. It is read, never assumed.
PROVIDER_HEADER = "x-inference-provider"

#: Where a recorded value came from. A figure stated in the body, a figure
#: stated in a header and a figure we computed ourselves are three different
#: kinds of evidence, and collapsing them would hide which one was available.
PROVIDER_SOURCE_BODY = "response_body:provider"
PROVIDER_SOURCE_HEADER = f"response_header:{PROVIDER_HEADER}"

#: DeepInfra returns ``usage.estimated_cost``. The name is the provider's own:
#: it is what they expect to bill, not a settled charge, and it is recorded as
#: reported-but-estimated rather than as a credited cost.
COST_SOURCE = "provider_usage_estimated_cost"

# Providers that served HUB_MODEL_ID when the metadata was read. Membership is
# recorded for provenance; it is not a promise that the set is stable.
SERVING_PROVIDERS = ("baseten", "deepinfra", "novita", "together")


# --------------------------------------------------------------------------
# Tariff snapshot
# --------------------------------------------------------------------------

TARIFF_SNAPSHOT_ID = "hf_router_v1_models_2026-09-30"
TARIFF_SNAPSHOT_SOURCE = "GET https://router.huggingface.co/v1/models"
TARIFF_SNAPSHOT_RETRIEVED_AT = "2026-09-30"
TARIFF_UNIT = "usd_per_million_tokens"

# Read verbatim from the router listing on the snapshot date. Hugging Face bills
# routed requests at the provider's own rate with no markup, so these are the
# rates that would be charged; they are not a quote and can change without
# notice, which is why an estimate built from them is never reported as a cost.
TARIFFS: dict[str, dict[str, float]] = {
    "baseten": {"input": 1.32, "output": 3.96},
    "deepinfra": {"input": 1.30, "output": 2.60},
    "novita": {"input": 1.32, "output": 3.96},
    "together": {"input": 1.32, "output": 3.96},
}

# Context length and measured serving characteristics from the same listing.
# Latency and throughput are Hugging Face's own measurements at a point in time.
PROVIDER_PROFILE: dict[str, dict[str, Any]] = {
    "baseten": {
        "status": "live",
        "provider_model_id": "deepseek-ai/DeepSeek-V4-Pro-0813",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_structured_output": False,
        "first_token_latency_ms": 353.0,
        "throughput_tokens_per_second": 70.67,
    },
    "deepinfra": {
        "status": "live",
        "provider_model_id": "deepseek-ai/DeepSeek-V4-Pro-0813",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_structured_output": True,
        "first_token_latency_ms": 536.0,
        "throughput_tokens_per_second": 42.27,
    },
    "novita": {
        "status": "live",
        # Novita exposes the model under its own lower-case identifier. The
        # dated suffix is preserved, but the mapping is the provider's, not the
        # Hub's, so a silent remap on their side would not be visible here.
        "provider_model_id": "deepseek/deepseek-v4-pro-0813",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_structured_output": False,
        "first_token_latency_ms": 1542.0,
        "throughput_tokens_per_second": 49.46,
    },
    "together": {
        "status": "live",
        "provider_model_id": "deepseek-ai/DeepSeek-V4-Pro-0813",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_structured_output": False,
        "first_token_latency_ms": 787.4,
        "throughput_tokens_per_second": 133.94,
    },
}


# --------------------------------------------------------------------------
# Capability evidence
# --------------------------------------------------------------------------

VERIFIED = "verified_from_hub_metadata"
DOCUMENTED = "documented_in_router_api_reference"
ABSENT = "absent_from_documented_response_schema"
UNVERIFIED = "unverified_requires_live_smoke"

# What the free metadata and the published reference do and do not settle.
# A parameter appearing in the router's request schema means the router accepts
# it, not that the selected provider honours it: the router is a proxy and the
# reference states that support and defaults are provider and model dependent.
CAPABILITY_EVIDENCE: dict[str, dict[str, Any]] = {
    "exact_0813_version": {
        "status": VERIFIED,
        "evidence": (
            "inferenceProviderMapping lists all four providers as status 'live' for the "
            "dated repository deepseek-ai/DeepSeek-V4-Pro-0813."
        ),
    },
    "chat_completion_task": {
        "status": VERIFIED,
        "evidence": "Every provider entry declares task 'conversational'.",
    },
    "system_message": {
        "status": DOCUMENTED,
        "evidence": (
            "The messages schema takes an arbitrary role string; a system message is "
            "part of the OpenAI-compatible surface. Provider-side acceptance of a "
            "system message under a one-token output cap is not stated."
        ),
    },
    "temperature_0_and_1": {
        "status": DOCUMENTED,
        "evidence": (
            "temperature is documented as a number between 0 and 2. Whether a provider "
            "honours exactly 0 or silently clamps it is not stated, and the model card "
            "recommends temperature 1.0 for agentic use."
        ),
    },
    "max_tokens_1_and_16": {
        "status": DOCUMENTED,
        "evidence": (
            "max_tokens is documented with no stated minimum. That a provider accepts "
            "the value 1 rather than rejecting or raising it is not stated."
        ),
    },
    "reasoning_disable": {
        "status": UNVERIFIED,
        "evidence": (
            "The router documents reasoning_effort with common values none, minimal, "
            "low, medium, high, xhigh, and states that support and defaults are "
            "provider and model dependent. The model card for DeepSeek-V4-Pro-0813 "
            "documents reasoning_effort with the values low, high and max only, and "
            "documents no mechanism for disabling reasoning. No metadata establishes "
            "that reasoning can be switched off on this route."
        ),
    },
    "reasoning_token_reporting": {
        "status": ABSENT,
        "evidence": (
            "The documented usage object contains prompt_tokens, completion_tokens and "
            "total_tokens only. There is no completion_tokens_details and no "
            "reasoning_tokens field, so a claim that reasoning did not run cannot be "
            "checked against the documented response."
        ),
    },
    "effective_provider_identification": {
        "status": ABSENT,
        "evidence": (
            "The documented response body has no provider field. The provider "
            "registration guide suggests an Inference-Id response header, which is an "
            "opaque request identifier and not a provider name, and which the OpenAI "
            "SDK surfaces only through with_raw_response."
        ),
    },
    "token_usage": {
        "status": DOCUMENTED,
        "evidence": "usage.prompt_tokens, usage.completion_tokens, usage.total_tokens.",
    },
    "finish_reason": {
        "status": DOCUMENTED,
        "evidence": "choices[].finish_reason is in the documented response body.",
    },
    "cost_in_response": {
        "status": ABSENT,
        "evidence": (
            "No cost field is documented in the response body or as a response header. "
            "Spending is visible only on the Hugging Face billing page, so per-call "
            "cost cannot be read back and a live budget guard cannot be driven by it."
        ),
    },
    "version_pinning": {
        "status": UNVERIFIED,
        "evidence": (
            "The dated repository is pinned, but no provider discloses the "
            "quantization or the serving stack behind it, and Novita remaps the id to "
            "its own namespace. Weight-level identity across providers is not stated."
        ),
    },
    "fallback_suppression": {
        "status": DOCUMENTED,
        "evidence": (
            "Automatic failover is documented as applying to automatic provider "
            "selection. Naming a provider in the model id selects that provider. That "
            "no silent substitution can occur once a provider is named is not stated, "
            "and cannot be checked from the response because no provider is returned."
        ),
    },
}


# --------------------------------------------------------------------------
# Reasoning gate
# --------------------------------------------------------------------------

# The OpenRouter/Baidu route sends ``reasoning: {"enabled": false}`` and reads
# ``reasoning_tokens = 0`` back. Neither half of that contract has a verified
# equivalent here, so the configuration must state, in one of these values, what
# it has decided to do. There is no default: a route that silently guessed would
# make the two arms look comparable when they are not.
REASONING_CONTROL_KEY = "huggingface_reasoning_control"

#: Send nothing and record that reasoning behaviour is unknown.
REASONING_OMITTED = "omitted_and_recorded_as_unverified"
#: Send an explicit reasoning_effort, whose value the configuration must supply.
REASONING_EFFORT = "reasoning_effort"

REASONING_CONTROLS = frozenset({REASONING_OMITTED, REASONING_EFFORT})

# Values the router documents as common. The model card for this model documents
# only low, high and max, so anything else may be rejected or silently ignored.
DOCUMENTED_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
MODEL_CARD_REASONING_EFFORTS = ("low", "high", "max")


class RouteConfigurationError(ValueError):
    """The route was asked to do something its evidence does not support."""


def split_model_and_provider(api_model: str) -> tuple[str, str]:
    """Split ``repo/name:provider`` into the Hub id and the pinned provider.

    Raises when no provider is pinned, or when what follows the colon is a
    selection policy rather than a provider. A policy would let Hugging Face
    pick the backend per request, which is exactly the property the design
    needs to exclude.
    """

    if not isinstance(api_model, str) or not api_model.strip():
        raise RouteConfigurationError("The Hugging Face route needs a model id.")

    model = api_model.strip()
    head, separator, tail = model.rpartition(":")
    if not separator:
        raise RouteConfigurationError(
            f"Model id {model!r} pins no provider. The Hugging Face route requires an "
            f"explicit '<repository>:<provider>' id, for example "
            f"'{HUB_MODEL_ID}:deepinfra'. Without it the router selects a backend per "
            f"request and the served weights are not held constant."
        )

    provider = tail.strip().lower()
    if not head.strip():
        raise RouteConfigurationError(f"Model id {model!r} names no repository.")
    if provider in POLICY_SUFFIXES:
        raise RouteConfigurationError(
            f"Model id {model!r} uses the selection policy {provider!r}. A policy "
            f"delegates the backend choice to the router at request time, so the "
            f"provider is not held constant. Name a provider instead."
        )
    if not provider:
        raise RouteConfigurationError(f"Model id {model!r} has an empty provider suffix.")
    return head.strip(), provider


def estimate_cost(
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """Estimate the credited cost from observed tokens and the tariff snapshot.

    Returns None when the provider is outside the snapshot or when either token
    count is missing. The caller must keep the result in a field of its own: it
    is an estimate from a dated price list, never a reported cost.
    """

    tariff = TARIFFS.get(provider)
    if tariff is None:
        return None
    if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
        return None
    if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
        return None
    return (
        input_tokens * tariff["input"] + output_tokens * tariff["output"]
    ) / 1_000_000.0


def unverified_aspects() -> tuple[str, ...]:
    """Aspects that the free metadata could not settle, in a stable order."""

    return tuple(
        sorted(
            name
            for name, entry in CAPABILITY_EVIDENCE.items()
            if entry["status"] in {UNVERIFIED, ABSENT}
        )
    )


def reasoning_gate_status() -> dict[str, Any]:
    """Whether the route can reproduce the OpenRouter reasoning contract.

    The contract has two halves: reasoning is switched off, and the response
    proves it. Both must hold. The second half fails on the documented schema
    alone, which is why the gate cannot be cleared by argument.
    """

    disable = CAPABILITY_EVIDENCE["reasoning_disable"]
    report = CAPABILITY_EVIDENCE["reasoning_token_reporting"]
    cleared = disable["status"] == VERIFIED and report["status"] not in {ABSENT, UNVERIFIED}
    return {
        "cleared": cleared,
        "can_disable_reasoning": disable["status"],
        "can_observe_reasoning_tokens": report["status"],
        "openrouter_contract": "reasoning={'enabled': False} accepted, reasoning_tokens=0 reported",
        "conclusion": (
            "Not equivalent to the OpenRouter/Baidu route. Neither half of the "
            "reasoning contract is established by the free metadata."
        )
        if not cleared
        else "Equivalent on the reasoning contract.",
    }


def route_metadata(api_model: str, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The routing facts a record must carry, derived from the request alone.

    This states what was *asked for*. What actually served the call is a
    separate question that the response, not this function, has to answer.
    """

    hub_model, provider = split_model_and_provider(api_model)
    return {
        "gateway": GATEWAY,
        "gateway_base_url": ROUTER_BASE_URL,
        "requested_model": hub_model,
        "requested_provider": provider,
        "model_id_sent": api_model.strip(),
        "allow_fallbacks": False,
        "credential_env_var": TOKEN_ENV_VAR,
        "tariff_snapshot_id": TARIFF_SNAPSHOT_ID,
        "reasoning_control": (settings or {}).get(REASONING_CONTROL_KEY),
    }
