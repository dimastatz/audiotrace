import json

import pytest

from audiotrace.models import (
    CallReport,
    Cost,
    Events,
    Latency,
    LatencySpan,
    MediaInfo,
    Quality,
    Sentiment,
)
from audiotrace.report import (
    Metric,
    _as_number,
    _banner,
    _deltas_section,
    _format_value,
    _response_p95_ms,
    _trim,
    diff,
    render_html,
    render_json,
    summarize,
    write_report,
)


def _report(
    *,
    quality_score: float = 0.9,
    sentiment: float = 0.5,
    frustration: bool = False,
    interruptions: int = 1,
    pace: float = 150.0,
    outcome: str = "completed",
    drop_off: bool = False,
    compliance_flags: tuple[str, ...] = (),
    cost: float = 0.12,
    duration_ms: int = 60_000,
    waterfall_ms: tuple[int, ...] = (),
) -> CallReport:
    return CallReport(
        media=MediaInfo(
            duration_ms=duration_ms,
            sample_rate_hz=16000,
            channels=1,
            codec="mp3",
            file_size_bytes=1000,
            file_format="mp3",
            bitrate_kbps=128.0,
        ),
        quality=Quality(
            overall_score=quality_score,
            interruptions=interruptions,
            speaking_pace_wpm=pace,
        ),
        sentiment=Sentiment(overall=sentiment, caller_frustration=frustration),
        events=Events(
            outcome=outcome,
            drop_off=drop_off,
            compliance_flags=list(compliance_flags),
        ),
        cost=Cost(total_usd=cost),
        latency=Latency(
            waterfall=[
                LatencySpan(name="agent_response", start_ms=i * 1000, duration_ms=d)
                for i, d in enumerate(waterfall_ms)
            ]
        ),
    )


# --- summarize ---


def test_summarize_returns_expected_keys():
    keys = {m.key for m in summarize(_report())}
    assert keys == {
        "outcome",
        "quality_score",
        "sentiment",
        "caller_frustration",
        "interruptions",
        "speaking_pace_wpm",
        "response_p95_ms",
        "drop_off",
        "compliance_flags",
        "cost_usd",
        "duration_ms",
    }


def test_summarize_compliance_flags_counts_not_lists():
    metrics = {m.key: m.value for m in summarize(_report(compliance_flags=("pii_exposed", "x")))}
    assert metrics["compliance_flags"] == 2


def test_summarize_handles_missing_media():
    report = _report()
    report.media = None
    metrics = {m.key: m.value for m in summarize(report)}
    assert metrics["duration_ms"] == 0


def test_summarize_rounds_quality_score():
    metrics = {m.key: m.value for m in summarize(_report(quality_score=0.876543))}
    assert metrics["quality_score"] == 0.88


# --- _response_p95_ms ---


def test_response_p95_empty_is_zero():
    assert _response_p95_ms(_report(waterfall_ms=())) == 0


def test_response_p95_single_span():
    assert _response_p95_ms(_report(waterfall_ms=(400,))) == 400


def test_response_p95_nearest_rank():
    # 20 values 100..2000; p95 nearest-rank index = ceil(0.95*20)=19 -> 1900
    durations = tuple(range(100, 2100, 100))
    assert _response_p95_ms(_report(waterfall_ms=durations)) == 1900


# --- diff ---


def test_diff_skips_neutral_and_string_metrics():
    deltas = diff(_report(), _report())
    keys = {d.key for d in deltas}
    assert "outcome" not in keys  # neutral string
    assert "duration_ms" not in keys  # neutral
    assert "quality_score" in keys


def test_diff_flags_quality_regression():
    deltas = {d.key: d for d in diff(_report(quality_score=0.9), _report(quality_score=0.7))}
    assert deltas["quality_score"].regressed is True
    assert deltas["quality_score"].change == pytest.approx(-0.2)


def test_diff_quality_improvement_not_regressed():
    deltas = {d.key: d for d in diff(_report(quality_score=0.7), _report(quality_score=0.9))}
    assert deltas["quality_score"].regressed is False


def test_diff_flags_cost_increase_as_regression():
    deltas = {d.key: d for d in diff(_report(cost=0.1), _report(cost=0.2))}
    assert deltas["cost_usd"].regressed is True


def test_diff_frustration_bool_becomes_regression():
    deltas = {d.key: d for d in diff(_report(frustration=False), _report(frustration=True))}
    assert deltas["caller_frustration"].before == 0.0
    assert deltas["caller_frustration"].after == 1.0
    assert deltas["caller_frustration"].regressed is True


def test_diff_no_change_not_regressed():
    deltas = {d.key: d for d in diff(_report(), _report())}
    assert deltas["quality_score"].regressed is False
    assert deltas["quality_score"].change == 0


def test_diff_missing_baseline_metric_is_skipped():
    base_metrics = [Metric("quality_score", "Quality score", 0.9, "score", True)]
    # A current metric absent from baseline should be dropped by the key lookup.
    from audiotrace import report as report_mod

    original = report_mod.summarize
    calls = {"n": 0}

    def fake_summarize(r):
        calls["n"] += 1
        return base_metrics if calls["n"] == 1 else summarize(r)

    report_mod.summarize = fake_summarize
    try:
        deltas = {d.key: d for d in diff(_report(), _report())}
    finally:
        report_mod.summarize = original
    assert "interruptions" not in deltas
    assert "quality_score" in deltas


# --- render_json ---


def test_render_json_has_summary_and_report_no_deltas():
    data = json.loads(render_json(_report()))
    assert "summary" in data
    assert "report" in data
    assert "deltas" not in data


def test_render_json_includes_deltas_with_baseline():
    data = json.loads(render_json(_report(quality_score=0.7), baseline=_report(quality_score=0.9)))
    assert "deltas" in data
    quality = next(d for d in data["deltas"] if d["key"] == "quality_score")
    assert quality["regressed"] is True


def test_render_json_summary_values_match_metrics():
    report = _report(cost=0.3456)
    data = json.loads(render_json(report))
    assert data["summary"]["cost_usd"] == pytest.approx(0.3456)


# --- render_html ---


def test_render_html_is_standalone_document():
    out = render_html(_report())
    assert out.startswith("<!doctype html>")
    assert "AudioTrace call report" in out
    assert "Change vs. baseline" not in out  # no baseline -> no deltas section


def test_render_html_escapes_outcome():
    out = render_html(_report(outcome="<script>"))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_html_ok_banner_when_no_regressions():
    out = render_html(_report(), baseline=_report())
    assert "No regressions vs. baseline" in out
    assert "Change vs. baseline" in out


def test_render_html_bad_banner_counts_regressions():
    out = render_html(
        _report(quality_score=0.7, cost=0.3), baseline=_report(quality_score=0.9, cost=0.1)
    )
    assert "2 regressions vs. baseline" in out


def test_render_html_single_regression_singular_label():
    out = render_html(_report(quality_score=0.7), baseline=_report(quality_score=0.9))
    assert "1 regression vs. baseline" in out


def test_render_html_improved_metric_marked_and_signed():
    # quality improves 0.7 -> 0.9: positive change, "improved" class, no regression.
    out = render_html(_report(quality_score=0.9), baseline=_report(quality_score=0.7))
    assert "No regressions vs. baseline" in out
    assert 'class="improved"' in out
    assert "+0.2" in out


# --- write_report ---


def test_write_report_creates_both_files(tmp_path):
    paths = write_report(_report(), tmp_path / "out", baseline=_report())
    assert paths["json"].exists()
    assert paths["html"].exists()
    assert paths["json"].name == "report.json"
    data = json.loads(paths["json"].read_text())
    assert "deltas" in data


def test_write_report_custom_stem(tmp_path):
    paths = write_report(_report(), tmp_path, stem="happy_path")
    assert paths["html"].name == "happy_path.html"


# --- formatting helpers ---


def test_as_number_bool_and_string():
    assert _as_number(True) == 1.0
    assert _as_number(False) == 0.0
    assert _as_number("completed") == 0.0
    assert _as_number(3) == 3.0


@pytest.mark.parametrize(
    "metric, expected",
    [
        (Metric("k", "l", True), "Yes"),
        (Metric("k", "l", False), "No"),
        (Metric("k", "l", 0.12, "usd"), "$0.1200"),
        (Metric("k", "l", 150.0, "wpm"), "150.0 wpm"),
        (Metric("k", "l", 1500, "ms"), "1500 ms"),
        (Metric("k", "l", 0.876, "score"), "0.88"),
        (Metric("k", "l", "completed"), "completed"),
    ],
)
def test_format_value(metric, expected):
    assert _format_value(metric) == expected


def test_trim_drops_whole_number_decimal():
    assert _trim(5.0) == "5"
    assert _trim(-0.2) == "-0.2"


def test_deltas_section_empty_for_no_deltas():
    assert _deltas_section([]) == ""


def test_banner_no_baseline_is_empty():
    assert _banner(False, 0) == ""
