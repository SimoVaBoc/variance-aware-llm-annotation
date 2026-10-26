#!/usr/bin/env python3
"""Execute the Chapter 3 annotation manifest.

Safety posture:

* The default mode is ``--dry-run``. Nothing is sent to a provider.
* ``--live`` additionally requires ``--max-calls`` and ``--max-usd``.
* ``--mode full`` is refused. The 9,000-call run is not implemented and is
  gated behind the open decision list in ``docs/chapter3_research_design.md``.
* API keys are read from environment variables only and are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from src.chapter3 import huggingface as huggingface_route  # noqa: E402
from src.chapter3.design import load_config  # noqa: E402
from src.chapter3.execution import (  # noqa: E402
    IMPLEMENTED_TEXT_POLICIES,
    TEXT_POLICY_AS_IS,
    BudgetExceeded,
    BudgetPolicy,
    ExecutionBlocked,
    RetryPolicy,
    collect_blockers,
    count_samples_by_cell,
    read_manifest,
    read_records,
    run_manifest,
)
from src.chapter3.providers import (  # noqa: E402
    ProviderAdapter,
    api_key_env_var_for,
    build_adapter,
    resolve_api_key,
)


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "chapter3_experiment.json"
PILOT_MANIFEST = PROJECT_ROOT / "runs" / "manifests" / "chapter3_pilot_tasks.csv"
FULL_MANIFEST = PROJECT_ROOT / "runs" / "manifests" / "chapter3_tasks.csv"
DEFAULT_RAW_DIR = PROJECT_ROOT / "runs" / "raw"
#: SDK-level retries. Zero: the runner owns every attempt and records it.
SDK_MAX_RETRIES = 0
#: Explicit per-request timeout in seconds, applied by both SDKs to connect,
#: read, write and pool alike. Without it the SDK default applies: 600 s for
#: read, write and pool, 5 s for connect. A timeout is an API error with no HTTP
#: status, so it stops the segment like any other; it is never retried.
SDK_TIMEOUT_SECONDS = 120.0


def _os_trust_http_client():
    """Build an HTTP client that verifies TLS against the OS trust store.

    The bundled certifi roots fail on machines where an antivirus or corporate
    proxy terminates TLS with its own root CA, which is installed in the system
    store but not in certifi. Using the OS store keeps full certificate
    verification; it is never disabled.

    Returns None when truststore is unavailable, letting the SDK use its
    default verification rather than silently weakening it.
    """

    try:
        import ssl

        import httpx
        import truststore
    except ImportError:
        return None
    return httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))


def default_live_client(provider: str):
    """Construct a real provider client. Only reached on an approved live run.

    The key is read from the environment inside this function and is never
    returned, logged or attached to the run summary.
    """

    api_key = resolve_api_key(api_key_env_var_for(provider))
    http_client = _os_trust_http_client()

    base_urls = {
        "openai": None,
        "deepseek": "https://api.deepseek.com",
        "openrouter": "https://openrouter.ai/api/v1",
        # The Hugging Face router is a second, parallel route to the DeepSeek
        # model. It is reached with HF_TOKEN, which api_key_env_var_for resolves
        # from the adapter, so an OpenRouter key can never authenticate it.
        "huggingface": huggingface_route.ROUTER_BASE_URL,
    }

    # Both SDKs retry failed requests on their own by default. That would hide
    # extra paid attempts behind one recorded attempt and break the one-attempt
    # operational contract, so SDK retries are switched off: every attempt is
    # the runner's, and is counted.
    if provider == "anthropic":
        from anthropic import Anthropic

        return Anthropic(api_key=api_key, http_client=http_client, max_retries=SDK_MAX_RETRIES,
                         timeout=SDK_TIMEOUT_SECONDS)
    if provider in base_urls:
        from openai import OpenAI

        kwargs: dict = {"api_key": api_key, "http_client": http_client,
                        "max_retries": SDK_MAX_RETRIES, "timeout": SDK_TIMEOUT_SECONDS}
        if base_urls[provider] is not None:
            kwargs["base_url"] = base_urls[provider]
        return OpenAI(**kwargs)
    raise ExecutionBlocked(f"No live client is defined for provider {provider!r}")


def live_adapter_factory(provider: str) -> ProviderAdapter:
    return build_adapter(provider, default_live_client(provider))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--mode",
        choices=("pilot", "full"),
        default="pilot",
        help="pilot uses the 432-task pilot manifest; full is not implemented",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Override the manifest path (defaults to the pilot manifest)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Append-only JSONL log (defaults to runs/raw/<mode>_raw.jsonl)",
    )
    run_mode = parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Default. Plan every call and write dry_run records without contacting a provider",
    )
    run_mode.add_argument(
        "--live",
        dest="live",
        action="store_true",
        default=False,
        help="Send real requests. Requires --max-calls and --max-usd",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="Hard cap on requests for a live run",
    )
    parser.add_argument(
        "--max-usd",
        type=float,
        default=None,
        help="Hard budget cap in USD for a live run",
    )
    parser.add_argument(
        "--text-policy",
        choices=sorted(IMPLEMENTED_TEXT_POLICIES),
        default=TEXT_POLICY_AS_IS,
        help="Source-text handling. No normalization rule is approved, so the text is passed through unchanged",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Do not skip task IDs already recorded as successful",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N pending tasks")
    parser.add_argument(
        "--model-id",
        dest="model_ids",
        action="append",
        default=None,
        metavar="MODEL_ID",
        help=(
            "Restrict the run to one configured model id (repeatable). Use this to "
            "exercise a single provider when only its key is available."
        ),
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--base-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=30.0)
    return parser


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    manifest = args.manifest
    if manifest is None:
        manifest = PILOT_MANIFEST if args.mode == "pilot" else FULL_MANIFEST
    output = args.output
    if output is None:
        suffix = "dry_run" if not args.live else "live"
        output = DEFAULT_RAW_DIR / f"chapter3_{args.mode}_{suffix}.jsonl"
    return Path(manifest), Path(output)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.mode == "full":
        print(
            "Refusing to run the full design. The 9,000-call run is not implemented "
            "and remains blocked by the decision gates in "
            "docs/chapter3_research_design.md section 9.",
            file=sys.stderr,
        )
        return 2

    config = load_config(args.config)
    manifest_path, output_path = resolve_paths(args)

    if not manifest_path.exists():
        print(
            f"Manifest {manifest_path} does not exist. Build it first with:\n"
            "  python python/scripts/chapter3_design.py build-pilot-manifest",
            file=sys.stderr,
        )
        return 2

    budget = None
    if args.live:
        if args.max_calls is None or args.max_usd is None:
            print(
                "A live run requires BOTH --max-calls and --max-usd. "
                "Live execution is disabled by default.",
                file=sys.stderr,
            )
            return 2
        budget = BudgetPolicy(max_calls=args.max_calls, max_usd=args.max_usd)

    retry_policy = RetryPolicy(
        max_attempts=args.max_attempts,
        base_delay_seconds=args.base_delay,
        max_delay_seconds=args.max_delay,
    )

    try:
        summary = run_manifest(
            config=config,
            manifest_path=manifest_path,
            output_path=output_path,
            project_root=PROJECT_ROOT,
            mode=args.mode,
            live=args.live,
            budget=budget,
            adapter_factory=live_adapter_factory if args.live else None,
            text_policy=args.text_policy,
            retry_policy=retry_policy,
            resume=args.resume,
            limit=args.limit,
            model_ids=args.model_ids,
        )
    except (ExecutionBlocked, BudgetExceeded) as error:
        print(str(error), file=sys.stderr)
        return 3

    payload = summary.as_dict()
    payload["manifest"] = str(manifest_path.relative_to(PROJECT_ROOT))
    payload["config_sha256"] = read_manifest(manifest_path)[0]["config_sha256"]

    if not args.live:
        # A dry run reports how many samples a live run would still owe.
        records = read_records(output_path)
        payload["successful_samples_recorded"] = sum(count_samples_by_cell(records).values())
        selected = {row["model_id"] for row in read_manifest(manifest_path)}
        if args.model_ids:
            selected &= set(args.model_ids)
        payload["unresolved_blockers"] = collect_blockers(config, selected)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
