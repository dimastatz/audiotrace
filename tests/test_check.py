import json

import pytest

from audiotrace.check import (
    DEFAULT_THRESHOLDS,
    CheckResult,
    Regression,
    Threshold,
    _allowed,
    _num,
    check,
    format_result,
    load_baseline,
    write_baseline,
)
from audiotrace.models import CallReport, Cost, Events, MediaInfo, Quality, Sentiment


def _report(
    *,
    quality_score: float = 0.9,
    sentiment: float = 0.5,
    frustration: bool = False,
    interruptions: int = 1,
    cost: float = 0.10,
) -> CallReport:
    return CallReport(
        media=MediaInfo(
            duration_ms=60_000,
            sample_rate_hz=16000,
            channels=1,
            codec="mp3",
            file_size_bytes=1000,
            file_format="mp3",
            bitrate_kbps=128.0,
        ),
        quality=Quality(overall_score=quality_score, interruptions=interruptions),
        sentiment=Sentiment(overall=sentiment, caller_frustration=frustration),
        cost=Cost(total_usd=cost),
        events=Events(outcome="completed"),
    )


# --- Threshold / _allowed ---


def test_allowed_takes_larger_of_abs_and_rel():
    # abs 0.05 vs rel 0.15*0.9=0.135 -> 0.135 wins
    assert _allowed(Threshold(abs=0.05, rel=0.15), 0.9) == pytest.approx(0.135)


def test_allowed_zero_threshold_is_zero():
    assert _allowed(Threshold(), 100.0) == 0.0


def test_default_thresholds_cover_expected_keys():
    assert set(DEFAULT_THRESHOLDS) == {
        "quality_score",
        "sentiment",
        "response_p95_ms",
        "cost_usd",
        "interruptions",
    }


# --- check ---


def test_check_passes_when_identical():
    result = check({"a": _report()}, {"a": _report()})
    assert result.passed is True
    assert result.checked == 1
    assert result.regressions == []


def test_check_tolerates_small_quality_drop():
    # 0.90 -> 0.87 is a 0.03 drop, within the 0.05 tolerance.
    result = check({"a": _report(quality_score=0.87)}, {"a": _report(quality_score=0.90)})
    assert result.passed is True


def test_check_fails_large_quality_drop():
    # 0.90 -> 0.80 is 0.10, past the 0.05 tolerance.
    result = check({"a": _report(quality_score=0.80)}, {"a": _report(quality_score=0.90)})
    assert result.passed is False
    assert result.regressions[0].key == "quality_score"
    assert result.regressions[0].call_id == "a"


def test_check_zero_tolerance_metric_fails_on_any_regression():
    # frustration flips False->True with no tolerance.
    result = check({"a": _report(frustration=True)}, {"a": _report(frustration=False)})
    keys = {r.key for r in result.regressions}
    assert "caller_frustration" in keys
    assert result.passed is False


def test_check_relative_cost_tolerance():
    # cost 0.10 -> 0.118: allowed = 0.20*0.10 = 0.02; change 0.018 < 0.02 -> ok
    ok = check({"a": _report(cost=0.118)}, {"a": _report(cost=0.10)})
    assert ok.passed is True
    # 0.10 -> 0.13 is +0.03 > 0.02 allowed -> fail
    bad = check({"a": _report(cost=0.13)}, {"a": _report(cost=0.10)})
    assert bad.passed is False


def test_check_interruptions_plus_one_tolerated():
    ok = check({"a": _report(interruptions=2)}, {"a": _report(interruptions=1)})
    assert ok.passed is True
    bad = check({"a": _report(interruptions=4)}, {"a": _report(interruptions=1)})
    assert bad.passed is False


def test_check_ignores_improvements():
    result = check({"a": _report(quality_score=0.99)}, {"a": _report(quality_score=0.80)})
    assert result.passed is True
    assert result.regressions == []


def test_check_skips_calls_missing_from_baseline():
    result = check({"new": _report()}, {})
    assert result.skipped == ["new"]
    assert result.checked == 0
    assert result.passed is True


def test_check_custom_thresholds_override_defaults():
    # With zero tolerance on quality, a 0.03 drop now fails.
    thresholds = {"quality_score": Threshold()}
    result = check(
        {"a": _report(quality_score=0.87)},
        {"a": _report(quality_score=0.90)},
        thresholds,
    )
    assert result.passed is False


def test_check_sorts_and_counts_multiple_calls():
    current = {"b": _report(quality_score=0.80), "a": _report()}
    baseline = {"b": _report(quality_score=0.90), "a": _report()}
    result = check(current, baseline)
    assert result.checked == 2
    assert result.regressions[0].call_id == "b"


# --- baseline round-trip ---


def test_baseline_round_trip(tmp_path):
    reports = {"a": _report(quality_score=0.91), "b": _report(cost=0.2)}
    path = write_baseline(reports, tmp_path / "nested" / "baseline.json")
    assert path.exists()
    loaded = load_baseline(path)
    assert set(loaded) == {"a", "b"}
    assert loaded["a"].quality.overall_score == pytest.approx(0.91)


def test_baseline_file_is_json_keyed_by_call_id(tmp_path):
    path = write_baseline({"call1": _report()}, tmp_path / "baseline.json")
    data = json.loads(path.read_text())
    assert "call1" in data
    assert "quality" in data["call1"]


# --- format_result ---


def test_format_result_pass():
    out = format_result(CheckResult(regressions=[], checked=3, skipped=[]))
    assert out.startswith("PASS")
    assert "3 call(s)" in out


def test_format_result_fail_lists_regressions():
    reg = Regression("a", "quality_score", "Quality score", 0.9, 0.8, -0.1, 0.05)
    out = format_result(CheckResult(regressions=[reg], checked=1, skipped=[]))
    assert out.startswith("FAIL")
    assert "a: Quality score 0.9 → 0.8" in out
    assert "allowed ±0.05" in out


def test_format_result_reports_skipped():
    out = format_result(CheckResult(regressions=[], checked=0, skipped=["new1", "new2"]))
    assert "skipped (no baseline): new1, new2" in out


def test_num_trims_whole_numbers():
    assert _num(5.0) == "5"
    assert _num(0.05) == "0.05"
