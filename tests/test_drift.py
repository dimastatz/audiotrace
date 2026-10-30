import pytest

from audiotrace.drift import (
    DEFAULT_DRIFT_THRESHOLDS,
    DRIFT_METRICS,
    MIN_DRIFT_CALLS,
    DriftResult,
    _edges,
    drift,
    psi_kl,
)
from audiotrace.models import CallReport, Quality, Sentiment


def _run(scores, sentiment=0.0):
    return {
        f"call_{i}": CallReport(
            quality=Quality(overall_score=s), sentiment=Sentiment(overall=sentiment)
        )
        for i, s in enumerate(scores)
    }


SPREAD = [0.5 + i * 0.02 for i in range(20)]


def test_identical_runs_have_zero_drift():
    psi, kl = psi_kl(SPREAD, SPREAD)
    assert psi == pytest.approx(0.0) and kl == pytest.approx(0.0)


def test_shifted_run_has_large_psi():
    psi, kl = psi_kl(SPREAD, [s - 0.3 for s in SPREAD])
    assert psi > 1.0 and kl > 0.5


def test_small_wobble_stays_under_threshold():
    wobble = [s + (0.005 if i % 2 else -0.005) for i, s in enumerate(SPREAD)]
    psi, _ = psi_kl(SPREAD, wobble)
    assert psi < DEFAULT_DRIFT_THRESHOLDS["quality_score"]


def test_constant_baseline_still_detects_a_change():
    assert _edges([1.0] * 12, 3)[0] == 1.0
    assert psi_kl([1.0] * 12, [1.0] * 12)[0] == pytest.approx(0.0)
    assert psi_kl([1.0] * 12, [2.0] * 12)[0] > 1.0
    assert psi_kl([1.0] * 12, [0.0] * 12)[0] > 1.0


def test_drift_scores_every_metric_and_flags_the_moved_one():
    results = drift(_run([s - 0.3 for s in SPREAD]), _run(SPREAD))
    assert [r.key for r in results] == list(DRIFT_METRICS)
    by_key = {r.key: r for r in results}
    assert by_key["quality_score"].drifted
    assert by_key["quality_score"].baseline_mean == pytest.approx(0.69)
    assert by_key["quality_score"].current_mean == pytest.approx(0.39)
    assert not by_key["sentiment"].drifted


def test_drift_skips_small_runs():
    small = _run(SPREAD[: MIN_DRIFT_CALLS - 1])
    assert drift(small, _run(SPREAD)) is None
    assert drift(_run(SPREAD), small) is None


def test_custom_thresholds_select_metrics():
    results = drift(_run(SPREAD), _run(SPREAD), {"sentiment": 0.1})
    assert results == [
        DriftResult(
            key="sentiment", psi=0.0, kl=0.0, threshold=0.1, baseline_mean=0.0, current_mean=0.0
        )
    ]


# --- wired into check() ---------------------------------------------------------


def test_check_fails_on_distribution_drift_without_per_call_regressions():
    from audiotrace.check import Threshold, check, format_result

    # Every call moves a little (inside the per-call tolerance), but the
    # whole run moves together: only the distribution check catches it.
    base = _run(SPREAD)
    cur = _run([s - 0.08 for s in SPREAD])
    result = check(cur, base, thresholds={"quality_score": Threshold(abs=0.1)})
    assert not result.regressions
    assert [d.key for d in result.drifted] == ["quality_score"]
    assert not result.passed
    text = format_result(result)
    assert text.startswith("FAIL — 0 regression(s) and 1 drifted metric(s) across 20 call(s)")
    assert "drift: quality_score distribution moved (PSI" in text
    assert "mean 0.69 → 0.61" in text


def test_check_drift_can_be_turned_off_and_skips_small_runs():
    from audiotrace.check import Threshold, check

    base = _run(SPREAD)
    cur = _run([s - 0.08 for s in SPREAD])
    loose = {"quality_score": Threshold(abs=0.1)}
    assert check(cur, base, thresholds=loose, drift_thresholds={}).passed
    small = check(_run(SPREAD[:5]), _run(SPREAD[:5]))
    assert small.drift is None and small.passed


def test_check_drift_compares_only_shared_calls():
    from audiotrace.check import check

    base = _run(SPREAD)
    cur = dict(base)
    cur.update({f"new_{i}": CallReport(quality=Quality(overall_score=0.0)) for i in range(20)})
    result = check(cur, base)
    assert result.drifted == [] and len(result.skipped) == 20
