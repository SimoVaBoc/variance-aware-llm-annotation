"""Write the reviewer-facing derived copies of the Chapter 3 files that record observations.

Decision D-EXPORT-03: the review package carries the plan and the code that launches the
calls, but no evidence that a run happened or how it went. For each file below this tool
removes the observed fields (outcomes of probes, smokes and pilots, token counts, real
costs, real-run dates, corrections about earlier reports, paths under ``runs/``) and keeps
every settings field unchanged. Each JSON copy gains a visible ``review_redaction`` field;
the script copy gains a header comment. Both list what was removed, by path or by line of
the original. The specification below names paths and line numbers only, never values.

The originals are frozen and stay untouched; their SHA-256 is pinned, so a changed
original is refused instead of being redacted blindly. The copies are written under
``docs/chapter4_v2/export/redacted/`` and enter the review package through the allowlist
with the original path as destination.

Usage, from the repository root of the working copy (the originals are not exported)::

    python -B python/scripts/chapter4_v2_redact_for_review.py          # write the copies
    python -B python/scripts/chapter4_v2_redact_for_review.py --check  # compare only
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = PROJECT_ROOT / "docs/chapter4_v2/export/redacted"

PURPOSE = ("Reviewer-facing derived copy (decision D-EXPORT-03), not the frozen file. Observed "
           "fields (outcomes of probes, smokes and pilots, token counts, real costs, real-run "
           "dates, corrections about earlier reports, paths under runs/) are removed; every "
           "settings field is unchanged.")
HASH_NOTE = ("Hashes recorded in this file refer to the original files, which are not "
             "distributed; they do not match the derived copies.")

#: SHA-256 of each frozen original. A mismatch stops the tool.
ORIGINALS = {
    "config/chapter3_experiment.json": "3134083a9b284b4e43c517828d82130d6e5364e6d4709272ecc6e2db65b12375",
    "config/experiments/chapter3_comparative_experiment_v2_hf.json": "d5c420abfc24e5cab6fba2885c80830efdbd6481024006056bdfa81808154ae6",
    "config/experiments/chapter3_comparative_experiment_v3_hf_full.json": "c4564df96ffb887c5e558a735383f3c274469a912caee11c2b4e6ae92f3b6961",
    "config/experiments/chapter3_comparative_experiment_v4_first_party_smoke.json": "6c31b67cd89f152f6439dfb37458b3594a8c3423687869e4d47464b43caea16a",
    "config/experiments/chapter3_comparative_experiment_v5_terra_camuffo_cap16_smoke.json": "c5c95145cca912f4031c77e50c35e993264c971bd602e5fb89e728b3bfd6a22b",
    "config/experiments/chapter3_comparative_experiment_v6_terra_pilot.json": "cb2757698e30b5a8173867cd3ca9394397912921a3c9c00fc73dad919f721c96",
    "config/experiments/chapter3_comparative_experiment_v7_terra_full.json": "358de3c2a313f91633bb6477a9be0b6594a6e81cf73e1e5b7e9040f50982c118",
    "config/experiments/chapter3_comparative_experiment_v8_sonnet_pilot.json": "1895f90c055c5706fa5310090a088da96b9408d0f445fe133a1d18b518b3d88f",
    "config/experiments/chapter3_comparative_experiment_v9_sonnet_full.json": "58b9a6aab38784c4f60aa0e34ef38330c2326bd55dbf44f9bfde2608389dba13",
    "config/routes/chapter3_deepseek_hf_route_v1.json": "19b43fdcc639db3630d479c7b11242b671a7672b22ba06ea5dcc3f082d9a820e",
    "config/routes/chapter3_deepseek_hf_route_v2.json": "8a797b2b7f5f46da479f98b679e81ecd0cdedcc3488156d816bcb200e90afd8a",
    "config/routes/chapter3_deepseek_hf_route_v3_full.json": "cbbf4d67f63e6f11fbe5d05b9d3be734ff25f26b7974a49dcd2b50b1938b6d38",
    "config/routes/chapter3_sonnet_anthropic_route_v1.json": "f6f2b94c79179ee28c171f1822b27941e8fbcd38b59a8a0adce846a7eaf6f9fe",
    "config/routes/chapter3_sonnet_anthropic_route_v2.json": "bb8180394bdc02df7a173b1fb57e13e2104bfef4d358f9818305182002d5685f",
    "config/routes/chapter3_sonnet_anthropic_route_v3_pilot.json": "e027af3210465cbe77f5a360b534674ef97e8a408591b0d0ac972581fac6e834",
    "config/routes/chapter3_sonnet_anthropic_route_v4_full.json": "1e7190a61010389998dc38245d55c477696003f8a1138311561bb0c4a5ae024f",
    "config/routes/chapter3_terra_openai_route_v1.json": "83edc64c279c0f492df6fcf73eba198379e684e154f935fb3f1e5d327a976d28",
    "config/routes/chapter3_terra_openai_route_v2.json": "a2053d0d2cd40986650a28d15feb95d445e537735ec2f5d5efc7b60d4431425d",
    "config/routes/chapter3_terra_openai_route_v3_pilot.json": "69ad285a8ff76f4e1cba970c05bd5af5babd863ce4002f44f26a892a705a3e0b",
    "config/routes/chapter3_terra_openai_route_v4_full.json": "3f6b713e78906d961a679a74cfab78539a92354d13d3da44802efd529dc9c85f",
    "python/scripts/chapter3_execute_two_arm.py": "48873814e6d83464d81d6d7032bcda72f2471433474f7aa7399a1a55533455d2",
}

#: Kept out of the package: its two calibration constants are observed values and are
#: the defaults of --chars-per-token and --output-tokens, so removing them would change
#: what the estimator computes.
NOT_REDACTABLE = {
    "python/scripts/chapter3_estimate_cost.py": "ce4186582d2a07a1d4163dc741ccb4a0bbebc8cc66f88ac2e3ffea8944bd95e8",
}

_SMOKE = ["first_party_smoke.status", "first_party_smoke.manifest", "first_party_smoke.outputs"]
_SMOKE_OUTCOME = _SMOKE + ["first_party_smoke.caps"]
_SMOKE_V2 = ["first_party_smoke_v2.status", "first_party_smoke_v2.manifest",
             "first_party_smoke_v2.smoke_v1_log"]
_TERRA_PILOT = ["terra_pilot.status", "terra_pilot.manifest", "terra_pilot.smokes"]
_SONNET_PILOT = ["sonnet_pilot.status", "sonnet_pilot.manifest", "sonnet_pilot.smoke"]
_V2_SCOPE_NOTE = ["scopes.smoke_first_party_v2_terra_camuffo.description"]

#: Paths removed from each JSON file, written as dotted keys with [i] for list positions
#: of the original. A path that does not exist stops the tool.
JSON_REMOVALS: dict[str, list[str]] = {
    "config/chapter3_experiment.json": [
        "models.[2].selection_decision.upstream_not_chosen",
        "models.[2].selection_decision.upstream_eligibility_probe",
        "downstream.specification_decision.replication_evidence",
        "downstream.specification_decision.separation_handling",
    ],
    "config/experiments/chapter3_comparative_experiment_v2_hf.json": [
        "filename_note", "supersedes.note", "route.status", "route.status_note",
    ],
    "config/experiments/chapter3_comparative_experiment_v3_hf_full.json": [
        "status", "supersedes.note", "route.status",
    ],
    "config/experiments/chapter3_comparative_experiment_v4_first_party_smoke.json": [
        "filename_note", *_SMOKE,
    ],
    "config/experiments/chapter3_comparative_experiment_v5_terra_camuffo_cap16_smoke.json": [
        "filename_note", "supersedes.changes.[4]", "deviations_from_camuffo.[7].deviation",
        "execution.max_output_tokens_note", *_V2_SCOPE_NOTE, *_SMOKE_OUTCOME, *_SMOKE_V2,
    ],
    "config/experiments/chapter3_comparative_experiment_v6_terra_pilot.json": [
        "filename_note", "supersedes.changes.[5]", "deviations_from_camuffo.[7].deviation",
        "deviations_from_camuffo.[8].deviation", "execution.max_output_tokens_note",
        *_V2_SCOPE_NOTE, "scopes.pilot_terra_first_party.item_source",
        *_SMOKE_OUTCOME, *_SMOKE_V2, *_TERRA_PILOT,
    ],
    "config/experiments/chapter3_comparative_experiment_v7_terra_full.json": [
        "filename_note", "supersedes.changes.[4]", "deviations_from_camuffo.[7].deviation",
        "deviations_from_camuffo.[8].deviation", "deviations_from_camuffo.[9].deviation",
        "execution.max_output_tokens_note", *_V2_SCOPE_NOTE,
        "scopes.pilot_terra_first_party.item_source", *_SMOKE_OUTCOME, *_SMOKE_V2,
        *_TERRA_PILOT, "terra_full.status", "terra_full.manifest", "terra_full.aggregation",
    ],
    "config/experiments/chapter3_comparative_experiment_v8_sonnet_pilot.json": [
        "filename_note", "supersedes.changes.[1]",
        "scopes.pilot_sonnet_first_party.item_source", *_SMOKE, *_SONNET_PILOT,
    ],
    "config/experiments/chapter3_comparative_experiment_v9_sonnet_full.json": [
        "filename_note", "supersedes.changes.[1]",
        "scopes.pilot_sonnet_first_party.item_source", *_SMOKE, *_SONNET_PILOT,
        "sonnet_full.status", "sonnet_full.manifest", "sonnet_full.aggregation",
    ],
    "config/routes/chapter3_deepseek_hf_route_v1.json": [
        "relationship_to_existing_route.existing_route_artefacts",
        "relationship_to_existing_route.the_openrouter_pilot_remains",
    ],
    "config/routes/chapter3_deepseek_hf_route_v2.json": [
        "supersedes.note", "what_changed_from_v1.[0]", "what_changed_from_v1.[2]", "status",
        "probe_evidence", "tariff_snapshot.cached_input_observed",
        "tariff_snapshot.cached_input_note",
    ],
    "config/routes/chapter3_deepseek_hf_route_v3_full.json": [
        "supersedes.chain.[1].records", "decision.verdict", "decision.basis",
        "decision.decided_by", "decision.decided_utc", "pilot_evidence",
        "interpretive_corrections",
        "status", "counterbalancing_exception.independence_from_labels_and_outcomes.empirical",
        "budget_guard.note", "relationship_to_the_openrouter_run.re:^openrouter_\\d+_calls$",
    ],
    "config/routes/chapter3_sonnet_anthropic_route_v1.json": [],
    "config/routes/chapter3_sonnet_anthropic_route_v2.json": ["supersedes.relationship"],
    "config/routes/chapter3_sonnet_anthropic_route_v3_pilot.json": [
        "supersedes.relationship", "evidence_from_the_smoke",
    ],
    "config/routes/chapter3_sonnet_anthropic_route_v4_full.json": [
        "supersedes.relationship", "client.rate_limits", "evidence",
    ],
    "config/routes/chapter3_terra_openai_route_v1.json": [],
    "config/routes/chapter3_terra_openai_route_v2.json": [
        "supersedes.relationship", "request_settings_on_the_wire.carlson", "observed_in_smoke_v1",
        "documented_capabilities.reasoning_effort_none.status",
        "documented_capabilities.temperature_with_reasoning_none.status",
        "documented_capabilities.max_completion_tokens.status",
        "documented_capabilities.usage_fields.status",
        "documented_capabilities.returned_model_string.status",
        "documented_capabilities.returned_model_string.evidence",
    ],
    "config/routes/chapter3_terra_openai_route_v3_pilot.json": [
        "supersedes.relationship", "evidence_from_the_smokes",
    ],
    "config/routes/chapter3_terra_openai_route_v4_full.json": [
        "supersedes.relationship", "request_settings_on_the_wire.camuffo_cap_note",
        "client.timeout_note", "evidence",
    ],
}

TWO_ARM = "python/scripts/chapter3_execute_two_arm.py"
#: Line edits of the two-arm script, by line of the original: (first, last, new lines).
#: Only comments, the docstring and string constants change.
SCRIPT_EDITS = {
    TWO_ARM: [
        (12, 12, ["temporary drivers used to provide, now written down:"]),
        (106, 118, [
            "    # [review redaction: route-by-route validation history and run statuses removed]",
            '    "deepseek_huggingface_deepinfra": "redacted_for_review",',
            '    "openrouter": "redacted_for_review",',
            '    "terra_openai": "redacted_for_review",',
            '    "sonnet_anthropic": "redacted_for_review",',
        ]),
        (669, 673, ['               "error that stops a segment.")']),
    ],
}
SCRIPT_HEADER = {
    TWO_ARM: [
        "# REVIEW REDACTION (decision D-EXPORT-03). Reviewer-facing derived copy of",
        f"# {TWO_ARM}, not the frozen file.",
        f"# Original SHA-256: {ORIGINALS[TWO_ARM]}",
        "# Removed or neutralised, by line of the original:",
        "#   12        docstring: one phrase removed",
        "#   106-118   comments removed; the four route values of VALIDATION_SCOPE replaced",
        "#             by \"redacted_for_review\"",
        "#   669-673   --help epilog: the route-by-route status sentences removed",
        "# Only comments, the docstring and string constants differ from the original; the",
        "# syntax tree is otherwise identical. No execution contract is included; a contract",
        "# binds the exact files it authorises by SHA-256.",
    ],
}


class RedactionError(RuntimeError):
    """An original changed, or the specification names a path that does not exist."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse(path: str) -> list:
    return [int(t[1:-1]) if t.startswith("[") else t for t in path.split(".")]


def _key(parent, token, path: str):
    """A ``re:`` token names a key by pattern, for key names that themselves record a value."""

    if isinstance(token, str) and token.startswith("re:") and isinstance(parent, dict):
        matches = [k for k in parent if re.fullmatch(token[3:], k)]
        if len(matches) != 1:
            raise RedactionError(f"pattern must match exactly one key: {path}")
        return matches[0]
    return token


def remove_paths(document: dict, paths: list[str]) -> dict:
    """A copy of ``document`` without ``paths`` (original positions; later ones first)."""

    result = copy.deepcopy(document)
    targets = []
    for path in paths:
        tokens = _parse(path)
        parent = result
        for token in tokens[:-1]:
            parent = parent[_key(parent, token, path)]
        last = _key(parent, tokens[-1], path)
        if last not in (parent if isinstance(parent, dict) else range(len(parent))):
            raise RedactionError(f"no such path: {path}")
        targets.append((id(parent), parent, last, path))
    # List positions are removed from the highest down, so earlier positions stay valid.
    for _, parent, key, _ in sorted(targets, key=lambda t: (t[0], -(t[2] if isinstance(t[2], int) else 0))):
        del parent[key]
    return result


def _has_hash_field(node) -> bool:
    if isinstance(node, dict):
        return any("sha256" in str(k) or _has_hash_field(v) for k, v in node.items())
    if isinstance(node, list):
        return any(_has_hash_field(v) for v in node)
    return False


def redact_json(source: str, raw: bytes) -> str:
    document = json.loads(raw.decode("utf-8"))
    removed = JSON_REMOVALS[source]
    kept = remove_paths(document, removed)
    record = {"derived_from": source, "original_sha256": sha256(raw), "purpose": PURPOSE,
              "removed": removed or "nothing: no observed field was found"}
    if _has_hash_field(kept):
        record["hashes_note"] = HASH_NOTE
    return json.dumps({"review_redaction": record, **kept}, indent=2, ensure_ascii=False) + "\n"


def redact_script(source: str, raw: bytes) -> str:
    lines = raw.decode("utf-8").splitlines()
    out = list(lines)
    for first, last, new in sorted(SCRIPT_EDITS[source], reverse=True):
        out[first - 1:last] = new
    out[1:1] = SCRIPT_HEADER[source]
    text = "\n".join(out) + "\n"
    _same_logic(raw.decode("utf-8"), text)
    return text


class _Strings(ast.NodeTransformer):
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant("<str>"), node) if isinstance(node.value, str) else node


def _same_logic(original: str, derived: str) -> None:
    """Refuse unless the two differ only in comments, docstrings and string constants."""

    dump = [ast.dump(_Strings().visit(ast.parse(t))) for t in (original, derived)]
    if dump[0] != dump[1]:
        raise RedactionError("the derived script differs from the original beyond strings")


def build() -> dict[str, str]:
    copies = {}
    for source, pinned in {**ORIGINALS, **NOT_REDACTABLE}.items():
        if sha256((PROJECT_ROOT / source).read_bytes()) != pinned:
            raise RedactionError(f"{source} differs from its pinned original")
    for source in ORIGINALS:
        raw = (PROJECT_ROOT / source).read_bytes()
        copies[source] = (redact_script if source.endswith(".py") else redact_json)(source, raw)
    return copies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args(argv)
    try:
        copies = build()
    except RedactionError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    stale = []
    for source, text in copies.items():
        target = OUT_ROOT / source
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != text:
                stale.append(source)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        print("stale or missing copies:\n- " + "\n- ".join(stale), file=sys.stderr)
        return 1
    print(f"{'checked' if args.check else 'wrote'} {len(copies)} derived copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
