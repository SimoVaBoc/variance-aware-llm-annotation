"""Worked example on invented data: the whole Chapter 4 v2 chain, end to end.

Builds a synthetic input (``chapter4_v2.synthetic``), runs the annotation framework
(with the framework bootstrap), H1, the H2 core and the H3 point contrast, and, if R
with logistf 1.26.1 is found, the Firth fits, H4 and E1. Writes a JSON report whose
outputs are keyed to analysis IDs and carry an output tier, plus a short Markdown
summary. Everything is labelled synthetic. No real data, no network.

Usage (from the repository root)::

    python -B python/scripts/chapter4_v2_synthetic_example.py --out <new folder>
    python -B python/scripts/chapter4_v2_synthetic_example.py --out <new folder> --no-r

The output folder must not exist yet. Downstream fits use exactly the specified
controls; under those controls they do not certify convergence (D-FIRTH-03), and the
report says so instead of hiding it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from src.chapter3.chapter4_v2.aggregation import build_vectors  # noqa: E402
from src.chapter3.chapter4_v2.annotation_framework import evaluate_annotation_framework  # noqa: E402
from src.chapter3.chapter4_v2.decisions import load_register  # noqa: E402
from src.chapter3.chapter4_v2.downstream import build_common_design, label_set  # noqa: E402
from src.chapter3.chapter4_v2.firth import (  # noqa: E402
    RUnavailable,
    find_rscript,
    r_environment,
    run_downstream,
)
from src.chapter3.chapter4_v2.h1 import h1_variation  # noqa: E402
from src.chapter3.chapter4_v2.h2 import h2_core  # noqa: E402
from src.chapter3.chapter4_v2.h3 import h3_point_contrast  # noqa: E402
from src.chapter3.chapter4_v2.h4_e1 import e1_points, h4_dispersion, plot_e1  # noqa: E402
from src.chapter3.chapter4_v2.procedures import build_registry  # noqa: E402
from src.chapter3.chapter4_v2.reporting import build_report  # noqa: E402
from src.chapter3.chapter4_v2.samples import sample_b, sample_i27, sample_r  # noqa: E402
from src.chapter3.chapter4_v2.spec import load_spec  # noqa: E402
from src.chapter3.chapter4_v2.synthetic import build_synthetic_input  # noqa: E402

FORBIDDEN_PARTS = {"data", "runs", "Codice_tesi_private"}


def run(out: Path, *, use_r: bool = True, n_items: int = 60, seed: int = 1,
        bootstrap: bool = True) -> dict:
    if out.exists():
        raise FileExistsError(f"refusing to write into an existing folder: {out}")
    if FORBIDDEN_PARTS & set(out.resolve().parts):
        raise ValueError("the example never writes into data/, runs/ or a private folder")
    spec, register = load_spec(), load_register()
    data = build_synthetic_input(spec, n_items=n_items, seed=seed)
    registry = build_registry(spec)
    vectors = build_vectors(data, registry)
    b = sample_b(data)
    i27 = sample_i27(data, b)
    r = sample_r(data, b, registry, vectors)

    downstream, reason = None, None
    if use_r:
        environment = r_environment(find_rscript())
        if environment["available"]:
            try:
                design = build_common_design(data, r.members)
                labels = label_set(design, data, vectors,
                                   [p.procedure_id for p in registry.primary]
                                   + [p.procedure_id for p in registry.va_post_sp])
                downstream = run_downstream(spec, design, labels)
            except (RUnavailable, ValueError) as error:
                reason = f"downstream not run: {error}"
        else:
            reason = f"R with logistf not available: {environment.get('reason')}"
    else:
        reason = "R deliberately not used (--no-r)"

    framework = evaluate_annotation_framework(spec, data, downstream=downstream,
                                              run_bootstrap=bootstrap)
    h4 = h4_dispersion(spec, downstream) if downstream is not None else None
    e1 = e1_points(data, registry, vectors, r.members, downstream) if downstream else None
    report = build_report(spec, register, data, framework, h1_variation(data),
                          h2_core(spec, data), h3_point_contrast(data, registry, vectors, b, i27),
                          downstream=downstream, h4=h4, e1=e1, downstream_reason=reason)
    out.mkdir(parents=True)
    (out / "chapter4_v2_synthetic_report.json").write_text(
        json.dumps(report, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    if e1 is not None and e1["points"]:
        plot_e1(e1, out / "e1_synthetic.png")
    (out / "README_SYNTHETIC.md").write_text(summary(report), encoding="utf-8")
    return report


def summary(report: dict) -> str:
    lines = ["# SYNTHETIC worked example (invented data)", "",
             f"Specification `{report['header']['spec_id']}` {report['header']['spec_version']}, "
             f"sha256 `{report['header']['spec_sha256']}`; code `{report['header']['code_commit']}` "
             f"(modified tree: {report['header']['working_tree_modified']}).", "",
             report["labels"], "", "## Pending modules", "",
             "| Item | Analysis | Decision | Status | Shown instead |", "| --- | --- | --- | --- | --- |"]
    for row in report["pending_status_table"]:
        lines.append(f"| {row['item']} | {row['analysis_id']} | {row['decision_id']} | "
                     f"{row['decision_status']} | {row['shown_instead']} |")
    lines += ["", "## Outputs", "", "| Output | Analysis IDs | Tier | Basis |",
              "| --- | --- | --- | --- |"]
    for entry in report["outputs"]:
        lines.append(f"| {entry['output_id']} | {', '.join(entry['analysis_ids'])} | "
                     f"{entry['output_tier']} | {entry['tier_basis']} |")
    lines += ["", "All values in the JSON report come from invented data.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="new folder for the synthetic report")
    parser.add_argument("--no-r", action="store_true", help="skip the R logistf fits")
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--items", type=int, default=60)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    report = run(Path(args.out), use_r=not args.no_r, n_items=args.items, seed=args.seed,
                 bootstrap=not args.no_bootstrap)
    print(f"wrote {args.out} (data_kind = {report['data_kind']}, "
          f"{len(report['outputs'])} outputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
