"""Status of a descriptive analysis, kept apart from the criteria vocabulary.

``satisfied``, ``not_satisfied`` and ``not_evaluable`` (:mod:`.thresholds`) belong to
framework criteria: they say whether a declared rule is met. A descriptive analysis
(an H1 cell, the H3 point contrast, the H4 dispersion contrast) applies no rule, so
it says only whether it could be computed.
"""

from __future__ import annotations

COMPUTED = "computed"
NOT_COMPUTABLE = "not_computable"
ANALYSIS_STATUSES = (COMPUTED, NOT_COMPUTABLE)

__all__ = ["ANALYSIS_STATUSES", "COMPUTED", "NOT_COMPUTABLE"]
