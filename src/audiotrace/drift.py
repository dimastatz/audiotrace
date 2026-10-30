"""Run-level distributional drift for noisy continuous metrics (PRD 0009 Part B).

Per-call tolerances (:mod:`audiotrace.check`) are brittle for signals measured
from audio: one call's quality score wobbles for reasons nobody controls. This
module compares the *distribution* of each continuous metric across a run of
calls with the baseline run, using the Population Stability Index (PSI) as the
gate and KL divergence as a second, reported-only view.

Binning is fit to the baseline: quantile edges, with the bin count scaled to
the sample (about four calls per bin, between 2 and 10 bins), and every bin
smoothed by half a call so empty bins don't blow up the logarithms. Runs
smaller than :data:`MIN_DRIFT_CALLS` aren't scored — the statistic is noise.

Pure standard library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from audiotrace.models import CallReport
from audiotrace.report import summarize

# Metrics compared as distributions. Hard/binary events (frustration, drop-off,
# compliance) stay gated per call in check.py, where pinpointing matters.
DRIFT_METRICS = ("quality_score", "sentiment", "speaking_pace_wpm", "response_p95_ms", "cost_usd")

# PSI above 0.25 is the conventional "significant shift"; 0.1–0.25 "moderate".
DEFAULT_DRIFT_THRESHOLDS: dict[str, float] = dict.fromkeys(DRIFT_METRICS, 0.25)

MIN_DRIFT_CALLS = 10
CALLS_PER_BIN = 4
MAX_BINS = 10
SMOOTHING = 0.5


@dataclass(frozen=True)
class DriftResult:
    """Distribution drift of one metric between the baseline and current runs."""

    key: str
    psi: float
    kl: float
    threshold: float
    baseline_mean: float
    current_mean: float

    @property
    def drifted(self) -> bool:
        return self.psi > self.threshold + 1e-12


def _edges(values: list[float], bins: int) -> list[float]:
    """Interior bin edges at the baseline's quantiles (deduplicated)."""
    ordered = sorted(values)
    edges: list[float] = []
    for i in range(1, bins):
        q = ordered[min(len(ordered) - 1, round(i * len(ordered) / bins))]
        if not edges or q > edges[-1]:
            edges.append(q)
    if ordered[0] == ordered[-1]:  # constant baseline: separate below / equal / above
        edges = [ordered[0], math.nextafter(ordered[0], math.inf)]
    return edges


def _histogram(values: list[float], edges: list[float]) -> list[float]:
    counts = [SMOOTHING] * (len(edges) + 1)
    for v in values:
        counts[sum(1 for e in edges if v >= e)] += 1
    total = sum(counts)
    return [c / total for c in counts]


def psi_kl(baseline: list[float], current: list[float]) -> tuple[float, float]:
    """PSI and KL(current ‖ baseline) over baseline-quantile bins."""
    bins = max(2, min(MAX_BINS, len(baseline) // CALLS_PER_BIN))
    edges = _edges(baseline, bins)
    p = _histogram(baseline, edges)
    q = _histogram(current, edges)
    psi = sum((qi - pi) * math.log(qi / pi) for pi, qi in zip(p, q))
    kl = sum(qi * math.log(qi / pi) for pi, qi in zip(p, q))
    return psi, kl


def _values(reports: dict[str, CallReport], key: str) -> list[float]:
    out: list[float] = []
    for report in reports.values():
        metric = next(m for m in summarize(report) if m.key == key)
        out.append(float(metric.value))
    return out


def drift(
    current: dict[str, CallReport],
    baseline: dict[str, CallReport],
    thresholds: dict[str, float] | None = None,
) -> list[DriftResult] | None:
    """Per-metric drift between two runs, or ``None`` when either run has fewer
    than :data:`MIN_DRIFT_CALLS` calls."""
    if min(len(current), len(baseline)) < MIN_DRIFT_CALLS:
        return None
    thr = thresholds if thresholds is not None else DEFAULT_DRIFT_THRESHOLDS
    results: list[DriftResult] = []
    for key, threshold in thr.items():
        base = _values(baseline, key)
        cur = _values(current, key)
        psi, kl = psi_kl(base, cur)
        results.append(
            DriftResult(
                key=key,
                psi=psi,
                kl=kl,
                threshold=threshold,
                baseline_mean=sum(base) / len(base),
                current_mean=sum(cur) / len(cur),
            )
        )
    return results
