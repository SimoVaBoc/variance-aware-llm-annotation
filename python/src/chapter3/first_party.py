"""Tariff snapshots and local cost estimates for the first-party OpenAI and
Anthropic routes.

Neither first-party API returns a price with the response. The operational
budget guard therefore works on a cost computed locally from the usage block
and a dated, versioned tariff snapshot. That number is an estimate, kept in
``cost_estimated`` with the snapshot id in ``cost_estimate_basis``. It is never
written into ``cost``, which is reserved for what a provider itself reported,
and it is not the bill: invoices are the only record of what was charged.

Token accounting follows each provider's own definitions, so nothing is counted
twice:

* OpenAI: ``prompt_tokens`` includes cached tokens and tokens written to the
  cache; ``completion_tokens`` already includes reasoning tokens.
* Anthropic: ``input_tokens`` covers only the uncached portion; cache writes and
  cache reads are reported separately; ``output_tokens`` already includes
  thinking tokens.

Imports nothing from the package, so it cannot create a cycle.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The cost source the CLI expects on these routes. A local estimate, not a
#: charge reported by the provider.
COST_SOURCE = "local_tariff_estimate"
COST_KIND = "local_estimate_not_billing"
TARIFF_UNIT = "usd_per_million_tokens"

#: How the rates below were read. WebFetch was not available on the retrieval
#: date, so each figure was transcribed from search extracts of the official
#: pages, which are named. Confirm them on the pricing pages before authorising
#: a paid run; a changed figure means a new snapshot id, never an edit.
RETRIEVAL_METHOD = "search_extract_of_official_documentation"
RETRIEVED_AT = "2026-10-21"

OPENAI_TARIFF_SNAPSHOT_ID = "openai_gpt-5.6-terra_2026-10-21"
ANTHROPIC_TARIFF_SNAPSHOT_ID = "anthropic_claude-sonnet-5_2026-10-21"

TARIFFS: dict[str, dict[str, Any]] = {
    OPENAI_TARIFF_SNAPSHOT_ID: {
        "provider": "openai",
        "api_model": "gpt-5.6-terra",
        "input": 2.00,
        "cached_input": 0.20,
        # Writes are billed at 1.25x the uncached input rate for GPT-5.6 and
        # later, in place of the ordinary input charge, not on top of it.
        "cache_write": 2.50,
        "output": 12.00,
        # Above this many prompt tokens the whole request is billed at 2x input
        # and 1.5x output. No call in this design comes near it; past it the
        # estimate is refused rather than priced at the wrong rate.
        "long_context_threshold_input_tokens": 272_000,
        "sources": [
            "https://developers.openai.com/api/docs/models/gpt-5.6-terra",
            "https://developers.openai.com/api/docs/guides/prompt-caching",
        ],
        "caveat": "The launch post still shows the earlier rates of $2.50 input and "
                  "$15.00 output; the model page shows the rates after the 30 July price "
                  "drop, used here. The extract of the model page was partly garbled.",
    },
    ANTHROPIC_TARIFF_SNAPSHOT_ID: {
        "provider": "anthropic",
        "api_model": "claude-sonnet-5",
        "input": 2.00,
        "cache_write_5m": 2.50,
        "cache_write_1h": 4.00,
        "cache_read": 0.20,
        "output": 10.00,
        "sources": [
            "https://platform.claude.com/docs/en/about-claude/pricing",
            "https://platform.claude.com/docs/en/build-with-claude/prompt-caching",
            "https://platform.claude.com/docs/en/models/sonnet-5/overview",
        ],
        "caveat": "One documentation page lists a cache-read rate of $0.10, which belongs "
                  "to Claude Sonnet 5.5, not to Sonnet 5. Batch rates are not used.",
    },
}

#: Which snapshot prices which (route, requested model).
SNAPSHOT_FOR = {
    ("openai", "gpt-5.6-terra"): OPENAI_TARIFF_SNAPSHOT_ID,
    ("anthropic", "claude-sonnet-5"): ANTHROPIC_TARIFF_SNAPSHOT_ID,
}


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def snapshot_for(route: str, api_model: str) -> str | None:
    return SNAPSHOT_FOR.get((route, api_model))


def estimate_openai_cost(
    snapshot_id: str,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    cache_write_tokens: int | None,
) -> float | None:
    """USD estimate for one Chat Completions call. None if it cannot be priced.

    A cache field the provider did not report is taken as zero: those tokens are
    then priced at the ordinary input rate. Cached reads are cheaper than that,
    writes dearer by a quarter; see the route file for what this implies.
    """

    tariff = TARIFFS[snapshot_id]
    prompt, completion = _count(prompt_tokens), _count(completion_tokens)
    if prompt is None or completion is None:
        return None
    if prompt > tariff["long_context_threshold_input_tokens"]:
        return None
    cached = _count(cached_tokens) or 0
    writes = _count(cache_write_tokens) or 0
    uncached = prompt - cached - writes
    if uncached < 0:
        return None
    return (
        uncached * tariff["input"]
        + cached * tariff["cached_input"]
        + writes * tariff["cache_write"]
        + completion * tariff["output"]
    ) / 1_000_000.0


def estimate_anthropic_cost(
    snapshot_id: str,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None,
    cache_write_tokens: int | None,
    cache_write_breakdown: Mapping[str, Any] | None,
) -> float | None:
    """USD estimate for one Messages call. None if it cannot be priced.

    Cache writes are priced by TTL when the breakdown is present. Without it,
    every written token is priced at the dearer one-hour rate, so the estimate
    errs high rather than low.
    """

    tariff = TARIFFS[snapshot_id]
    uncached, output = _count(input_tokens), _count(output_tokens)
    if uncached is None or output is None:
        return None
    reads = _count(cache_read_tokens) or 0
    writes = _count(cache_write_tokens) or 0
    write_cost = writes * tariff["cache_write_1h"]
    if cache_write_breakdown:
        five = _count(cache_write_breakdown.get("ephemeral_5m_input_tokens")) or 0
        hour = _count(cache_write_breakdown.get("ephemeral_1h_input_tokens")) or 0
        if five + hour == writes:
            write_cost = five * tariff["cache_write_5m"] + hour * tariff["cache_write_1h"]
    return (
        uncached * tariff["input"]
        + reads * tariff["cache_read"]
        + write_cost
        + output * tariff["output"]
    ) / 1_000_000.0


__all__ = [
    "ANTHROPIC_TARIFF_SNAPSHOT_ID",
    "COST_KIND",
    "COST_SOURCE",
    "OPENAI_TARIFF_SNAPSHOT_ID",
    "RETRIEVAL_METHOD",
    "RETRIEVED_AT",
    "SNAPSHOT_FOR",
    "TARIFFS",
    "TARIFF_UNIT",
    "estimate_anthropic_cost",
    "estimate_openai_cost",
    "snapshot_for",
]
