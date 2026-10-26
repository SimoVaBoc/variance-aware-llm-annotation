"""Firth fits through the R logistf adapter, and the rules that judge them.

There is no Firth estimator in Python, not even as a cross-check. Python builds
and checks the common design (:mod:`.downstream`), sends it to
``r/firth_adapter.R`` and judges what comes back against the specification.

**Finding R.** ``Rscript`` is located, in order, by the environment variable
``CHAPTER4_V2_RSCRIPT``, by a local untracked ``local_paths.json`` at the
repository root (``{"rscript": "..."}``), or on ``PATH``. Nothing is hard-coded.

**Precision.** Every double crosses the boundary as a hexadecimal string, both
ways, so coefficients reach Python bit for bit.

**Usability** (D-FIRTH-02, operational details proposed in D-FIRTH-05):

* point usable: logistf's three reported convergence values all within the
  specified tolerances (|log-likelihood change| <= lconv, max |score| <= gconv,
  max |beta change| <= xconv), finite coefficients and covariance, positive LABEL
  variance;
* interval usable: for both profile limits of LABEL, |log-likelihood deviation|
  <= the profile lconv, last beta change <= the profile xconv, fewer iterations
  than the profile maxit, and a finite limit;
* ``usable`` needs both; ``point_only`` is descriptive and cannot pass downstream
  adequacy; ``failed`` and ``not_estimable`` carry their reasons.

**Distances.** |beta_j - beta_HUMAN| on the same R, Firth with Firth only. A
HUMAN fit that is not usable makes every distance unavailable; a procedure's
own failure affects only its distance. A failed fit is never evidence of a
difference.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .downstream import CommonDesign, LabelSet, prefit_checks, separation_diagnostic
from .spec import PROJECT_ROOT, AnalysisSpec
from .thresholds import NOT_EVALUABLE, Conclusion, threshold_conclusion

ADAPTER = Path(__file__).resolve().parent / "r" / "firth_adapter.R"
ENV_RSCRIPT = "CHAPTER4_V2_RSCRIPT"
LOCAL_CONFIG = "local_paths.json"
HUMAN = "HUMAN"

USABLE = "usable"
POINT_ONLY = "point_only"
FAILED = "failed"
NOT_ESTIMABLE = "not_estimable"
NOT_RUN = "not_run"


class RUnavailable(RuntimeError):
    """No Rscript with the required logistf could be found or run."""


def find_rscript(root: Path = PROJECT_ROOT) -> str | None:
    env = os.environ.get(ENV_RSCRIPT)
    if env:
        return env if Path(env).is_file() else None
    local = root / LOCAL_CONFIG
    if local.is_file():
        configured = json.loads(local.read_text(encoding="utf-8")).get("rscript")
        if configured and Path(configured).is_file():
            return configured
    return shutil.which("Rscript")


def r_environment(rscript: str | None) -> dict[str, Any]:
    """R and logistf versions, or the reason they are unavailable. Reads no data."""

    if not rscript:
        return {"available": False, "reason": "Rscript not found (env, local config or PATH)"}
    probe = ('cat(R.version.string, "\\n"); '
             'cat(tryCatch(as.character(packageVersion("logistf")), '
             'error = function(e) "absent"), "\\n")')
    try:
        done = subprocess.run([rscript, "--vanilla", "-e", probe], capture_output=True,
                              text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "reason": f"Rscript could not run: {error}"}
    lines = [l.strip() for l in done.stdout.splitlines() if l.strip()]
    if done.returncode != 0 or len(lines) < 2:
        return {"available": False, "reason": "Rscript failed to report versions"}
    return {"available": lines[1] != "absent", "r_version": lines[0], "logistf_version": lines[1],
            "reason": None if lines[1] != "absent" else "logistf is not installed"}


def _controls(spec: AnalysisSpec) -> tuple[dict[str, Any], dict[str, Any]]:
    estimator = spec.data["downstream"]["estimator"]
    c, pl = estimator["control"], estimator["profile_interval"]
    if c["initialisation"] != "zero" or c["method"] != "Newton-Raphson":
        raise ValueError("the adapter implements zero initialisation and Newton-Raphson only")
    control = {"maxit": int(c["maxit"]), "maxhs": int(c["maxhs"]), "maxstep": float(c["maxstep"]),
               "lconv": float(c["lconv"]), "gconv": float(c["gconv"]), "xconv": float(c["xconv"]),
               "collapse": bool(c["collapse"]), "fit": "NR"}
    profile = {"level": float(pl["level"]), "maxit": int(pl["maxit"]), "maxhs": int(pl["maxhs"]),
               "maxstep": float(pl["maxstep"]), "lconv": float(pl["lconv"]),
               "xconv": float(pl["xconv"]), "ortho": bool(pl["ortho"]), "pr": bool(pl["pr"])}
    return control, profile


def run_adapter(spec: AnalysisSpec, design: CommonDesign, requests: Sequence[tuple[str, np.ndarray]],
                rscript: str, timeout: int = 3600) -> dict[str, Any]:
    """One R process for every request. Files live in a temporary folder outside the repository."""

    control, profile = _controls(spec)
    payload = {
        "control": control, "profile_control": profile,
        "y": design.y.tolist(), "control_columns": list(design.control_names),
        "controls_hex": [float(v).hex() for v in design.controls.ravel(order="C")],
        "fits": [{"name": name, "label": np.asarray(label, dtype=int).tolist()}
                 for name, label in requests],
    }
    workdir = Path(tempfile.mkdtemp(prefix="chapter4_v2_firth_"))
    try:
        source, target = workdir / "input.json", workdir / "output.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        done = subprocess.run([rscript, "--vanilla", str(ADAPTER), str(source), str(target)],
                              capture_output=True, text=True, timeout=timeout, check=False)
        if done.returncode != 0 or not target.exists():
            raise RUnavailable(f"the R adapter failed: {done.stderr.strip()[-400:]}")
        return json.loads(target.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _f(value: str | None) -> float | None:
    return None if value is None else float.fromhex(value)


@dataclass
class FitAssessment:
    name: str
    status: str
    reasons: list[str] = field(default_factory=list)
    coefficient: float | None = None
    ci: tuple[float, float] | None = None
    coefficients: dict[str, float] = field(default_factory=dict)
    convergence: dict[str, Any] = field(default_factory=dict)
    prefit: dict[str, Any] = field(default_factory=dict)
    separation: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def point_usable(self) -> bool:
        return self.status in (USABLE, POINT_ONLY)

    def as_record(self) -> dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "reasons": list(self.reasons),
            "label_coefficient": self.coefficient,
            "label_coefficient_hex": None if self.coefficient is None else self.coefficient.hex(),
            "label_ci": None if self.ci is None else list(self.ci),
            "convergence": self.convergence, "prefit": self.prefit,
            "separation": self.separation, "warnings": list(self.warnings),
        }


def assess(name: str, output: Mapping[str, Any], spec: AnalysisSpec) -> FitAssessment:
    """Judge one adapter output against the specification. Pure: no R involved."""

    control, profile = _controls(spec)
    result = FitAssessment(name, FAILED, warnings=list(output.get("warnings") or []))
    if output.get("status") != "fitted":
        result.reasons.append(f"adapter: {output.get('status')}: {output.get('error')}")
        return result
    names = list(output["coefficient_names"])
    coefs = [_f(h) for h in output["coefficients_hex"]]
    result.coefficients = dict(zip(names, coefs))
    k = len(names)
    var = np.array([_f(h) for h in output["var_hex"]], dtype=float).reshape(k, k)
    conv = {key: _f(h) for key, h in output["conv_hex"].items()}
    result.convergence = {"reported": conv, "iterations": output.get("iter"),
                          "tolerances": {"lconv": control["lconv"], "gconv": control["gconv"],
                                         "xconv": control["xconv"]}}
    checks = {
        "loglik_change": abs(conv["loglik_change"]) <= control["lconv"],
        "max_abs_score": abs(conv["max_abs_score"]) <= control["gconv"],
        "beta_change": abs(conv["beta_change"]) <= control["xconv"],
    }
    result.convergence["certified"] = checks
    point_reasons = [f"convergence not certified: {k_}" for k_, ok in checks.items() if not ok]
    if not all(math.isfinite(c) for c in coefs) or not np.isfinite(var).all():
        point_reasons.append("non-finite coefficients or covariance")
    label_variance = float(var[1, 1]) if k > 1 else float("nan")
    if not label_variance > 0:
        point_reasons.append("LABEL variance is not positive")
    if output.get("firth") is not True or output.get("flic") is not False:
        point_reasons.append("the fit is not a plain Firth fit")
    result.coefficient = coefs[1] if k > 1 else None

    pl = output.get("label_pl_conv_hex")
    iters = output.get("label_pl_iter") or {}
    lower, upper = _f(output["label_ci_hex"]["lower"]), _f(output["label_ci_hex"]["upper"])
    interval_reasons = []
    if pl is None:
        interval_reasons.append("no profile convergence record for LABEL")
    else:
        for side in ("lower", "upper"):
            if not abs(_f(pl[f"{side}_loglik"])) <= profile["lconv"]:
                interval_reasons.append(f"{side} limit: log-likelihood target not reached")
            if not abs(_f(pl[f"{side}_beta"])) <= profile["xconv"]:
                interval_reasons.append(f"{side} limit: beta change above xconv")
            if not int(iters.get(side, profile["maxit"])) < profile["maxit"]:
                interval_reasons.append(f"{side} limit: iteration limit reached")
    if not (lower is not None and upper is not None and math.isfinite(lower)
            and math.isfinite(upper)):
        interval_reasons.append("a profile limit is not finite")
    method_ci = output.get("method_ci")
    if not (isinstance(method_ci, list) and len(method_ci) > 1
            and method_ci[1] == "Profile Likelihood"):
        interval_reasons.append("the LABEL interval is not reported as profile likelihood")
    result.convergence["profile"] = {"reported": None if pl is None else
                                     {k_: _f(v) for k_, v in pl.items()},
                                     "iterations": iters}
    result.ci = (lower, upper) if not interval_reasons else None

    if point_reasons:
        result.status, result.reasons = FAILED, point_reasons + interval_reasons
    elif interval_reasons:
        result.status, result.reasons = POINT_ONLY, interval_reasons
    else:
        result.status = USABLE
    return result


@dataclass
class DownstreamResult:
    design: CommonDesign
    fits: dict[str, FitAssessment]
    environment: dict[str, Any]

    @property
    def human(self) -> FitAssessment:
        return self.fits[HUMAN]

    def distance_to_human(self, name: str) -> float | None:
        fit = self.fits[name]
        if self.human.status != USABLE or fit.status != USABLE:
            return None
        return abs(fit.coefficient - self.human.coefficient)

    def pairwise_distance(self, x: str, y: str) -> float | None:
        a, b = self.fits.get(x), self.fits.get(y)
        if a is None or b is None or a.status != USABLE or b.status != USABLE:
            return None
        return abs(a.coefficient - b.coefficient)

    def proximity(self, spec: AnalysisSpec, procedure_ids: Sequence[str]) -> dict[str, Conclusion]:
        limit = spec.data["scores"]["thresholds"]["coefficient_distance_max"]
        rule = f"|beta_j - beta_HUMAN| <= {limit} (Firth, same R)"
        out = {}
        for pid in procedure_ids:
            name = f"human_proximity::{pid}"
            if self.human.status != USABLE:
                out[pid] = Conclusion(name, None, rule, "R", NOT_EVALUABLE,
                                      f"HUMAN fit not usable ({self.human.status}): every distance "
                                      "is unavailable")
                continue
            fit = self.fits[pid]
            if fit.status == POINT_ONLY:
                descriptive = abs(fit.coefficient - self.human.coefficient)
                out[pid] = Conclusion(name, {"descriptive_distance": descriptive}, rule, "R",
                                      NOT_EVALUABLE, "profile interval not usable; the point "
                                      "estimate is descriptive only")
                continue
            out[pid] = threshold_conclusion(name, self.distance_to_human(pid), limit,
                                            kind="at_most", sample="R", rule=rule,
                                            missing_reason=f"fit {fit.status}: "
                                            + "; ".join(fit.reasons[:3]))
        return out


def run_downstream(spec: AnalysisSpec, design: CommonDesign, labels: LabelSet,
                   rscript: str | None = None) -> DownstreamResult:
    """Pre-fit checks and the separation diagnostic in Python; every fit in R."""

    rscript = rscript or find_rscript()
    environment = r_environment(rscript)
    required = spec.data["downstream"]["estimator"]["required_version"]
    if not environment["available"] or environment.get("logistf_version") != required:
        raise RUnavailable(f"R with logistf {required} is required: "
                           f"{environment.get('reason') or environment.get('logistf_version')}")
    fits: dict[str, FitAssessment] = {}
    requests = []
    for name in labels.names:
        label = labels.values[name]
        prefit = prefit_checks(design, label)
        if prefit["estimable"]:
            separation = separation_diagnostic(design.matrix(label), design.y)
            requests.append((name, label))
            fits[name] = FitAssessment(name, NOT_RUN, prefit=prefit, separation=separation)
        else:
            fits[name] = FitAssessment(name, NOT_ESTIMABLE, reasons=prefit["failures"],
                                       prefit=prefit)
    if requests:
        output = run_adapter(spec, design, requests, rscript)
        environment.update({k: output.get(k) for k in ("r_version", "logistf_version",
                                                       "jsonlite_version", "platform",
                                                       "session")})
        for entry in output["fits"]:
            assessed = assess(entry["name"], entry, spec)
            assessed.prefit = fits[entry["name"]].prefit
            assessed.separation = fits[entry["name"]].separation
            fits[entry["name"]] = assessed
    return DownstreamResult(design, fits, environment)


__all__ = [
    "ADAPTER",
    "ENV_RSCRIPT",
    "FAILED",
    "HUMAN",
    "NOT_ESTIMABLE",
    "POINT_ONLY",
    "USABLE",
    "DownstreamResult",
    "FitAssessment",
    "RUnavailable",
    "assess",
    "find_rscript",
    "r_environment",
    "run_adapter",
    "run_downstream",
]
