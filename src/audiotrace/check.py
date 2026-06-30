"""Regression gating: compare a run of golden calls against a committed baseline.

This is the CI build gate of the Phase M wedge. ``check()`` takes freshly
analyzed reports and a baseline run, reuses :func:`audiotrace.report.diff` to
find per-call drift, and flags anything that moved past its tolerance. The
``audiotrace`` console script wraps this over a directory of recordings; the
GitHub Action wraps that for CI.

Pure standard library + the existing models and report layer; no new deps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from audiotrace.models import CallReport
from audiotrace.report import diff


@dataclass(frozen=True)
class Threshold:
    """Allowed worsening for one metric before a regression fails the gate.

    A regression is tolerated when the magnitude of the worse-direction change
    is within ``abs`` (an absolute amount) or ``rel`` (a fraction of the
    baseline value), whichever is larger. The defaults of 0 mean any regression
    fails.
    """

    abs: float = 0.0
    rel: float = 0.0


# Per-metric tolerance. Keys match the metric keys from audiotrace.report.
# Metrics not listed use a zero-tolerance Threshold() — any regression fails
# (frustration, drop-off, compliance flags: no slack).
DEFAULT_THRESHOLDS: dict[str, Threshold] = {
    "quality_score": Threshold(abs=0.05),
    "sentiment": Threshold(abs=0.10),
    "response_p95_ms": Threshold(rel=0.15),
    "cost_usd": Threshold(rel=0.20),
    "interruptions": Threshold(abs=1),
}


@dataclass(frozen=True)
class Regression:
    """A metric that drifted past its tolerance on a specific call."""

    call_id: str
    key: str
    label: str
    before: float
    after: float
    change: float
    allowed: float


@dataclass(frozen=True)
class CheckResult:
    """The outcome of gating a run against a baseline."""

    regressions: list[Regression]
    checked: int
    skipped: list[str]

    @property
    def passed(self) -> bool:
        """True when no regression breached its tolerance."""
        return not self.regressions


def _allowed(threshold: Threshold, before: float) -> float:
    """The largest worsening tolerated for ``before`` under ``threshold``."""
    return max(threshold.abs, threshold.rel * abs(before))


def check(
    current: dict[str, CallReport],
    baseline: dict[str, CallReport],
    thresholds: dict[str, Threshold] | None = None,
) -> CheckResult:
    """Gate a run of analyzed calls against a baseline run.

    For each call present in both runs, every metric that regressed (moved in
    the worse direction) beyond its tolerance becomes a :class:`Regression`.
    Calls missing from the baseline are skipped (reported, not failed) so new
    fixtures don't break the build.

    Args:
        current: Freshly analyzed reports, keyed by call id.
        baseline: The committed baseline reports, keyed by call id.
        thresholds: Per-metric tolerances; ``None`` uses DEFAULT_THRESHOLDS.

    Returns:
        A :class:`CheckResult`.
    """
    thr = thresholds if thresholds is not None else DEFAULT_THRESHOLDS
    regressions: list[Regression] = []
    skipped: list[str] = []
    checked = 0
    for call_id in sorted(current):
        base = baseline.get(call_id)
        if base is None:
            skipped.append(call_id)
            continue
        checked += 1
        for delta in diff(base, current[call_id]):
            if not delta.regressed:
                continue
            allowed = _allowed(thr.get(delta.key, Threshold()), delta.before)
            if abs(delta.change) > allowed + 1e-9:
                regressions.append(
                    Regression(
                        call_id=call_id,
                        key=delta.key,
                        label=delta.label,
                        before=delta.before,
                        after=delta.after,
                        change=delta.change,
                        allowed=allowed,
                    )
                )
    return CheckResult(regressions=regressions, checked=checked, skipped=skipped)


def write_baseline(reports: dict[str, CallReport], path: str | Path) -> Path:
    """Persist a run of reports as a baseline JSON file, keyed by call id."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {call_id: report.model_dump() for call_id, report in reports.items()}
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def load_baseline(path: str | Path) -> dict[str, CallReport]:
    """Load a baseline JSON file back into CallReports, keyed by call id."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {call_id: CallReport.model_validate(report) for call_id, report in data.items()}


def format_result(result: CheckResult) -> str:
    """A one-line headline plus a line per regression, for CI logs."""
    if result.passed:
        head = f"PASS — {result.checked} call(s) checked, no regressions"
    else:
        head = (
            f"FAIL — {len(result.regressions)} regression(s) "
            f"across {result.checked} call(s) checked"
        )
    lines = [head]
    for reg in result.regressions:
        lines.append(
            f"  {reg.call_id}: {reg.label} {_num(reg.before)} → {_num(reg.after)} "
            f"(allowed ±{_num(reg.allowed)})"
        )
    if result.skipped:
        lines.append(f"  skipped (no baseline): {', '.join(result.skipped)}")
    return "\n".join(lines)


def _num(value: float) -> str:
    """Drop a trailing ``.0`` so whole numbers read cleanly."""
    return str(int(value)) if value == int(value) else f"{value:g}"
