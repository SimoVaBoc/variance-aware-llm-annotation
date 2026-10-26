"""Entry point of the Chapter 4 consolidated analysis, specification version 2.

Offline and data-free in this implementation stage. The commands read only the
specification and the decision register in ``config/analysis``:

* ``status``: specification identity, code state, module statuses and the open
  decisions that keep modules disabled;
* ``validate``: validate the specification and the register against each other;
* ``render-register``: write ``docs/chapter4_v2/decision_register.md`` from the
  JSON register; ``--check`` compares instead of writing.

There is no empirical command yet. Running the analysis on real data is a
separate, explicitly authorised stage; the input boundary
(:mod:`src.chapter3.chapter4_v2.io_boundary`) refuses empirical bindings unless
the caller authorises them.

Usage, from the repository root::

    python python/scripts/chapter4_v2_analysis.py status
    python python/scripts/chapter4_v2_analysis.py validate
    python python/scripts/chapter4_v2_analysis.py render-register --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from src.chapter3.chapter4_v2.decisions import (  # noqa: E402
    DEFAULT_MARKDOWN_PATH,
    load_register,
    register_problems,
    render_markdown,
)
from src.chapter3.chapter4_v2.provenance import code_state  # noqa: E402
from src.chapter3.chapter4_v2.spec import load_spec  # noqa: E402


def cmd_status(_: argparse.Namespace) -> int:
    spec = load_spec()
    register = load_register()
    decisions = {d["id"]: d for d in register["decisions"]}
    modules = {
        name: {
            "methodological_status": module["methodological_status"],
            "enabled": module["enabled"],
            **({"waiting_on": module["decision_ids"]} if "decision_ids" in module else {}),
        }
        for name, module in spec.data["modules"].items()
    }
    out = {
        **spec.identity(),
        **code_state(PROJECT_ROOT),
        "modules": modules,
        "open_decisions": {i: decisions[i]["title"] for i in spec.data["open_decision_ids"]},
        "empirical_execution": "not enabled in this stage",
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    spec = load_spec()
    problems = register_problems(load_register(), spec)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"valid: {spec.spec_id} {spec.version} sha256 {spec.sha256}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    spec = load_spec()
    rendered = render_markdown(load_register(), spec)
    target = DEFAULT_MARKDOWN_PATH
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != rendered:
            print(f"{target.relative_to(PROJECT_ROOT)} is out of date", file=sys.stderr)
            return 1
        print("decision register markdown is up to date")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {target.relative_to(PROJECT_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    render = sub.add_parser("render-register")
    render.add_argument("--check", action="store_true")
    render.set_defaults(func=cmd_render)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
