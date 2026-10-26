#!/usr/bin/env python3
"""Validate and materialize the offline Chapter 3 experimental design."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from src.chapter3.design import (  # noqa: E402
    ManifestExists,
    build_task_manifest,
    load_config,
    profile_dataset,
    select_pilot_tasks,
    write_manifest,
)


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "chapter3_experiment.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "runs" / "manifests" / "chapter3_tasks.csv"
DEFAULT_PILOT_MANIFEST = PROJECT_ROOT / "runs" / "manifests" / "chapter3_pilot_tasks.csv"


def _display(path: Path) -> str:
    """Repository-relative when possible; an output outside the repository is shown as is."""

    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate", "profile-data", "build-manifest", "build-pilot-manifest"),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Overwrite an existing manifest. Refused by default: existing manifests "
            "are referenced by hash. Use only for a deliberate, approved replacement."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(args.config)

    if args.command == "profile-data":
        print(json.dumps(profile_dataset(config, PROJECT_ROOT), indent=2, sort_keys=True))
        return 0

    tasks, metadata = build_task_manifest(config, PROJECT_ROOT)
    if args.command == "validate":
        output = {
            "config": str(args.config.relative_to(PROJECT_ROOT)),
            "design": metadata,
            "dataset": profile_dataset(config, PROJECT_ROOT),
            "status": "valid",
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0

    if args.command == "build-pilot-manifest":
        pilot_count = config["execution"]["pilot_item_count"]
        tasks, pilot_items = select_pilot_tasks(tasks, pilot_count)
        metadata = {
            **metadata,
            "manifest_type": "technical_pilot",
            "n_items": pilot_count,
            "n_tasks": len(tasks),
            "pilot_item_ids": pilot_items,
            "reuse_in_final_analysis": config["execution"][
                "reuse_pilot_outputs_in_final_analysis"
            ],
        }
        if args.output == DEFAULT_MANIFEST:
            args.output = DEFAULT_PILOT_MANIFEST

    try:
        manifest_path, metadata_path = write_manifest(
            tasks, metadata, args.output, force=args.force
        )
    except ManifestExists as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "manifest": _display(manifest_path),
                "metadata": _display(metadata_path),
                **metadata,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
