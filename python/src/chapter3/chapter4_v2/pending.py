"""Entry points that exist, stay visible and cannot run until their decision is recorded.

A pending module is not missing and not failed: it is waiting for a decision
named in the register. Calling it raises :class:`DecisionPending` with that
decision, whatever the arguments. The specification cannot enable such a
module while its status is ``decision_pending`` (see :mod:`.spec`), so the
only way to run one is a recorded decision and a new specification version.
"""

from __future__ import annotations

from typing import Any

from .spec import AnalysisSpec


class DecisionPending(RuntimeError):
    """The requested analysis waits for a methodological decision."""


def pending_status(spec: AnalysisSpec, module: str) -> dict[str, Any]:
    entry = spec.module(module)
    return {"module": module, "status": entry["methodological_status"],
            "enabled": bool(entry["enabled"]), "waiting_on": list(entry.get("decision_ids", []))}


def refuse(spec: AnalysisSpec, module: str) -> None:
    """Raise unless the module is enabled; pending modules are never enabled."""

    status = pending_status(spec, module)
    if not status["enabled"]:
        raise DecisionPending(
            f"{module} is {status['status']} and disabled; it waits on "
            f"{', '.join(status['waiting_on']) or 'a recorded decision'}. Nothing was computed.")


__all__ = ["DecisionPending", "pending_status", "refuse"]
