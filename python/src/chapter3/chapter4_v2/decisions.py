"""The decision register: validation against the specification, and its rendering.

The JSON register is authoritative; the Markdown file is generated from it and
checked for drift, never edited by hand. Validation enforces what the brief
asks of the register rather than its layout: a closed status vocabulary, no
claim of supervisor approval, and agreement with the specification on which
decisions are open and which modules they hold back.

Dates are deliberately narrow. ``source_document_date`` is the date of the
document named in ``recorded_in`` and must equal the date that document
carries in the source list; it is never an adoption date, and the register
records no adoption date at all. An earlier date that a source itself states
for a decision is kept apart, in ``date_stated_by_source``, as a statement of
that source rather than a verified fact.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping

from .spec import PROJECT_ROOT, AnalysisSpec

DEFAULT_REGISTER_PATH = PROJECT_ROOT / "config/analysis/chapter4_decision_register_v2.json"
DEFAULT_MARKDOWN_PATH = PROJECT_ROOT / "docs/chapter4_v2/decision_register.md"

STATUSES = ("confirmed", "proposed", "unresolved", "superseded")
IMPLEMENTATION_STATUSES = frozenset(
    {"implemented", "not_started", "decision_pending", "not_applicable", "historical_retained"})
DECISION_FIELDS = (
    "id", "category", "title", "statement", "status", "sources", "version",
    "recorded_in", "source_document_date", "date_note", "decided_by", "supervisor_approval",
    "supersedes", "spec_refs", "implementation_status", "empirical_execution",
)
HISTORICAL_FIELDS = ("id", "title", "statement", "status", "superseded_by",
                     "source_document_date", "date_note", "retained_as")


class RegisterError(ValueError):
    """The register is incomplete or disagrees with the specification."""


def load_register(path: str | Path = DEFAULT_REGISTER_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _valid_date(value: Any) -> bool:
    if value is None:
        return True
    try:
        return dt.date.fromisoformat(str(value)).isoformat() == value
    except ValueError:
        return False


def _resolves(data: Mapping[str, Any], dotted: str) -> bool:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    return True


def register_problems(register: Mapping[str, Any], spec: AnalysisSpec) -> list[str]:
    problems: list[str] = []
    decisions = list(register.get("decisions", []))
    historical = list(register.get("historical", []))
    ids = [d.get("id") for d in decisions + historical]
    if len(ids) != len(set(ids)):
        problems.append("register IDs are not unique")
    by_id = {d.get("id"): d for d in decisions}
    hist_by_id = {h.get("id"): h for h in historical}
    source_dates = {s["id"]: s.get("date") for s in spec.data["sources"]}
    source_dates.update({s["id"]: s.get("date")
                         for s in register.get("implementation_sources", [])})

    for entry in decisions + historical:
        adoption = [k for k in entry if "adoption" in k]
        if adoption:
            problems.append(f"{entry.get('id')}: the register records no adoption date "
                            f"({adoption})")

    for d in decisions:
        where = d.get("id", "<no id>")
        missing = [f for f in DECISION_FIELDS if f not in d]
        if missing:
            problems.append(f"{where}: missing {missing}")
            continue
        if d["recorded_in"] not in source_dates:
            problems.append(f"{where}: recorded_in {d['recorded_in']!r} is not a listed source")
        elif d["source_document_date"] != source_dates[d["recorded_in"]]:
            problems.append(f"{where}: source_document_date is not the date of "
                            f"{d['recorded_in']}")
        if "date_stated_by_source" in d:
            if not _valid_date(d["date_stated_by_source"]) or d["date_stated_by_source"] is None:
                problems.append(f"{where}: date_stated_by_source is not an ISO date")
            if "Stated by the source" not in d["date_note"]:
                problems.append(f"{where}: a date stated by a source must be labelled as such")
        if d["status"] not in STATUSES or d["status"] == "superseded":
            problems.append(f"{where}: status {d['status']!r} is not a current-decision status")
        if d["implementation_status"] not in IMPLEMENTATION_STATUSES:
            problems.append(f"{where}: unknown implementation_status")
        if d["empirical_execution"] != "not_executed":
            problems.append(f"{where}: no empirical execution has been authorised")
        if d["supervisor_approval"] != "not documented":
            problems.append(f"{where}: supervisor approval is not documented in any source")
        if "not an adoption date" not in d["date_note"]:
            problems.append(f"{where}: date_note must say the date is not an adoption date")
        if d["status"] == "confirmed" and d["decided_by"] != "author (researcher)":
            problems.append(f"{where}: a confirmed decision is the author's")
        if d["status"] == "unresolved" and d["implementation_status"] not in {
                "decision_pending", "not_applicable"}:
            problems.append(f"{where}: an unresolved decision cannot be implemented")
        for ref in d["supersedes"]:
            if ref not in hist_by_id:
                problems.append(f"{where}: supersedes unknown entry {ref!r}")
        for ref in d["spec_refs"]:
            if not _resolves(spec.data, ref):
                problems.append(f"{where}: spec_ref {ref!r} does not resolve")

    for h in historical:
        where = h.get("id", "<no id>")
        missing = [f for f in HISTORICAL_FIELDS if f not in h]
        if missing:
            problems.append(f"{where}: missing {missing}")
            continue
        if h["status"] != "superseded":
            problems.append(f"{where}: historical entries are superseded")
        if not _valid_date(h["source_document_date"]):
            problems.append(f"{where}: source_document_date is not an ISO date or null")
        target = by_id.get(h["superseded_by"])
        if target is None:
            problems.append(f"{where}: superseded_by {h['superseded_by']!r} is unknown")
        elif target["status"] != "confirmed" or where not in target["supersedes"]:
            problems.append(f"{where}: must be superseded by a confirmed decision that lists it")

    open_in_spec = set(spec.data["open_decision_ids"])
    unresolved = {d["id"] for d in decisions if d.get("status") == "unresolved"}
    if open_in_spec != unresolved:
        problems.append(f"spec open decisions {sorted(open_in_spec)} differ from the "
                        f"register's unresolved decisions {sorted(unresolved)}")
    for name, module in spec.data["modules"].items():
        for ref in module.get("decision_ids", ()):
            if ref not in by_id:
                problems.append(f"module {name!r} names unknown decision {ref!r}")
    return problems


def validate_register(register: Mapping[str, Any], spec: AnalysisSpec) -> None:
    problems = register_problems(register, spec)
    if problems:
        raise RegisterError("Invalid decision register:\n- " + "\n- ".join(problems))


def _cell(value: Any) -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value) if value else "none"
    return str(value).replace("|", "\\|")


def render_markdown(register: Mapping[str, Any], spec: AnalysisSpec) -> str:
    """The English register, generated. Same input, same bytes."""

    lines = [
        "# Chapter 4 decision register",
        "",
        "<!-- Generated from config/analysis/chapter4_decision_register_v2.json. "
        "Do not edit by hand; run python/scripts/chapter4_v2_analysis.py render-register. -->",
        "",
        f"Register version {register['register_version']}, for specification "
        f"`{spec.spec_id}` version {spec.version} (sha256 `{spec.sha256}`).",
        "",
        "Statuses: **confirmed** (adopted by the author for implementation; not supervisor "
        "approval), **proposed** (not adopted), **unresolved** (open; the affected module is "
        "disabled or shown as pending), **superseded** (historical, kept for provenance). "
        "No entry has been executed on real data under this specification.",
        "",
        register["dating_rule"],
        "",
        "## Summary",
        "",
        "| ID | Title | Status | Implementation | Recorded in (document date) |",
        "| --- | --- | --- | --- | --- |",
    ]
    decisions = register["decisions"]
    for d in decisions:
        lines.append(f"| {d['id']} | {_cell(d['title'])} | {d['status']} | "
                     f"{d['implementation_status']} | {d['recorded_in']} "
                     f"({_cell(d['source_document_date'])}) |")

    titles = {"confirmed": "Confirmed decisions", "proposed": "Proposals (not adopted)",
              "unresolved": "Unresolved decisions"}
    for status, heading in titles.items():
        lines += ["", f"## {heading}", ""]
        for d in (x for x in decisions if x["status"] == status):
            lines += [f"### {d['id']}: {d['title']}", "", d["statement"], ""]
            rows = [
                ("Sources", d["sources"]), ("Version", d["version"]),
                ("Recorded in", d["recorded_in"]),
                ("Source document date", d["source_document_date"]),
                *([("Date stated by the source (not verified)", d["date_stated_by_source"])]
                  if "date_stated_by_source" in d else []),
                ("Date note", d["date_note"]), ("Decided by", d["decided_by"]),
                ("Supervisor approval", d["supervisor_approval"]),
                ("Supersedes", d["supersedes"]), ("Specification", d["spec_refs"]),
                ("Implementation", d["implementation_status"]),
                ("Empirical execution", d["empirical_execution"]),
            ]
            if "recommendation" in d:
                rows.append(("Recommendation", d["recommendation"]))
            if "notes" in d:
                rows.append(("Notes", d["notes"]))
            for earlier in d.get("history", []):
                rows.append(("Earlier status", f"{earlier['status']}, recorded in "
                             f"{earlier['recorded_in']} ({earlier['source_document_date']}), "
                             f"{earlier['decided_by']}"))
            lines += [f"- {label}: {_cell(value)}" for label, value in rows]
            if "row_sources" in d:
                lines += ["- Row sources:"]
                lines += [f"  - {row}: {source}" for row, source in d["row_sources"].items()]
            if "evidence_note" in d:
                note = d["evidence_note"]
                lines += [f"- Evidence note: {note['scope']}"]
                lines += [f"  - {item}" for item in note["items"]]
                lines += [f"  - {note['diagnostics']}", f"  - {note['not_concluded']}"]
            if "options" in d:
                lines += ["- Options for the author:"]
                lines += [f"  {i}. {option}" for i, option in enumerate(d["options"], start=1)]
            if "readings" in d:
                lines += ["- Readings:"]
                for name, reading in d["readings"].items():
                    lines += [f"  - {name}: {reading['rule']} Consequence: {reading['consequence']}"]
            if d.get("author_decision_needed"):
                lines += ["- Author decision needed: yes"]
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    lines += ["", "## Sources", "", "| ID | Title | Date | Kind |", "| --- | --- | --- | --- |"]
    for s in spec.data["sources"]:
        lines.append(f"| {s['id']} | {_cell(s['title'])} | {s['date']} | document |")
    for s in register.get("implementation_sources", []):
        lines.append(f"| {s['id']} | {_cell(s['title'])} | {s['date']} | {_cell(s.get('kind'))} |")

    lines += ["", "## Superseded historical rules and statements", "",
              "| ID | Title | Superseded by | Retained as |", "| --- | --- | --- | --- |"]
    for h in register["historical"]:
        lines.append(f"| {h['id']} | {_cell(h['title'])} | {h['superseded_by']} | "
                     f"{_cell(h['retained_as'])} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_MARKDOWN_PATH",
    "DEFAULT_REGISTER_PATH",
    "RegisterError",
    "load_register",
    "register_problems",
    "render_markdown",
    "validate_register",
]
