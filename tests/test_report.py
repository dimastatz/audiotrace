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
    Transcript,
    Turn,
)
from audiotrace.report import (
    Delta,
    Metric,
    _as_number,
    _banner,
    _bubble,
    _flags_badge,
    _flags_list,
    _format_ts,
    _format_value,
    _header_sub,
    _initials,
    _response_p95_ms,
    _sentiment_svg,
    _status_class,
    _tile,
    _tile_delta,
    _transcript_html,
    _trim,
    _waterfall_html,
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
    media: bool = True,
) -> CallReport:
    return CallReport(
        media=(
            MediaInfo(
                duration_ms=duration_ms,
                sample_rate_hz=16000,
                channels=1,
                codec="mp3",
                file_size_bytes=1000,
                file_format="mp3",
                bitrate_kbps=128.0,
            )
            if media
            else None
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
    metrics = {m.key: m.value for m in summarize(_report(media=False))}
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
    keys = {d.key for d in diff(_report(), _report())}
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
    from audiotrace import report as report_mod

    original = report_mod.summarize
    calls = {"n": 0}

    def fake_summarize(r):
        calls["n"] += 1
        return base_metrics if calls["n"] == 1 else original(r)

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
    data = json.loads(render_json(_report(cost=0.3456)))
    assert data["summary"]["cost_usd"] == pytest.approx(0.3456)


# --- render_html ---


def test_render_html_is_standalone_document():
    out = render_html(_report())
    assert out.startswith("<!doctype html>")
    assert "<title>AudioTrace call report</title>" in out
    assert 'class="tiles"' in out
    assert "Latency waterfall" in out


def test_render_html_escapes_outcome():
    out = render_html(_report(outcome="<script>"))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_html_no_banner_without_baseline():
    out = render_html(_report())
    assert "vs. baseline" not in out


def test_render_html_ok_banner_when_no_regressions():
    out = render_html(_report(), baseline=_report())
    assert "No regressions vs. baseline" in out
    assert 'class="banner ok"' in out


def test_render_html_bad_banner_counts_regressions():
    out = render_html(
        _report(quality_score=0.7, cost=0.3), baseline=_report(quality_score=0.9, cost=0.1)
    )
    assert "2 regressions vs. baseline" in out


def test_render_html_single_regression_singular_label():
    out = render_html(_report(quality_score=0.7), baseline=_report(quality_score=0.9))
    assert "1 regression vs. baseline" in out


def test_render_html_renders_transcript_bubbles():
    report = _report()
    report.transcript = Transcript(
        full_text="hi there",
        turns=[
            Turn(speaker="AI Agent", text="hi", start_ms=0, end_ms=1000),
            Turn(speaker="Customer", text="there", start_ms=2000, end_ms=3000),
        ],
    )
    out = render_html(report)
    assert 'class="bubble agent"' in out
    assert 'class="bubble caller"' in out
    assert ">AA<" in out  # agent initials


def test_render_html_renders_flags_badge_and_list():
    out = render_html(_report(compliance_flags=("pii_exposed", "missing_consent")))
    assert "flags-badge" in out
    assert "2 flags" in out
    assert "pii_exposed" in out


# --- tiles ---


def test_tile_outcome_renders_status_pill():
    metric = next(m for m in summarize(_report(outcome="dropped")) if m.key == "outcome")
    assert 'class="pill warn"' in _tile(metric, None)


def test_tile_includes_delta_subline():
    deltas = {d.key: d for d in diff(_report(quality_score=0.9), _report(quality_score=0.7))}
    metric = next(m for m in summarize(_report(quality_score=0.7)) if m.key == "quality_score")
    html_out = _tile(metric, deltas["quality_score"])
    assert "tile-sub down" in html_out
    assert "↓ vs 0.9" in html_out


def test_tile_delta_improvement_is_up_arrow():
    delta = Delta("quality_score", "Quality score", 0.7, 0.9, 0.2, regressed=False)
    out = _tile_delta(delta)
    assert "tile-sub up" in out
    assert "↑ vs 0.7" in out


def test_tile_delta_increase_regression_is_up_arrow_and_down_class():
    # cost rose: change > 0 (up arrow) but it's a regression (red "down" class).
    delta = Delta("cost_usd", "Cost", 0.1, 0.3, 0.2, regressed=True)
    out = _tile_delta(delta)
    assert "tile-sub down" in out
    assert "↑ vs 0.1" in out


def test_tile_delta_flat_when_unchanged():
    delta = Delta("quality_score", "Quality score", 0.9, 0.9, 0.0, regressed=False)
    assert "tile-sub flat" in _tile_delta(delta)


# --- header / status / flags helpers ---


@pytest.mark.parametrize(
    "outcome, cls",
    [("completed", "ok"), ("dropped", "warn"), ("failed", "bad"), ("weird", "neutral")],
)
def test_status_class(outcome, cls):
    assert _status_class(outcome) == cls


def test_header_sub_includes_intent_duration_format():
    report = _report()
    report.events.intent_detected = "billing"
    sub = _header_sub(report)
    assert "billing" in sub
    assert "1:00" in sub  # 60_000 ms
    assert "mp3" in sub


def test_header_sub_without_intent_or_media():
    report = _report(media=False)
    assert _header_sub(report) == ""


def test_flags_badge_empty_and_singular_and_plural():
    assert _flags_badge([]) == ""
    assert "1 flag<" in _flags_badge(["pii"]) or "1 flag " in _flags_badge(["pii"])
    assert "2 flags" in _flags_badge(["pii", "consent"])


def test_flags_list_empty_and_populated():
    assert _flags_list([]) == ""
    assert "pii_exposed" in _flags_list(["pii_exposed"])


# --- transcript helpers ---


def test_format_ts():
    assert _format_ts(0) == "0:00"
    assert _format_ts(75_000) == "1:15"


def test_initials_multiword_and_empty():
    assert _initials("AI Agent") == "AA"
    assert _initials("") == "?"


def test_bubble_agent_vs_caller_side():
    agent = Turn(speaker="AI Agent", text="hi", start_ms=0, end_ms=1000)
    caller = Turn(speaker="Customer", text="hello", start_ms=0, end_ms=1000)
    assert 'class="bubble agent"' in _bubble(agent)
    assert 'class="bubble caller"' in _bubble(caller)


def test_transcript_html_empty_with_full_text():
    out = _transcript_html(Transcript(full_text="only text"))
    assert "only text" in out


def test_transcript_html_empty_without_text():
    out = _transcript_html(Transcript())
    assert "(no transcript)" in out


# --- waterfall ---


def test_waterfall_all_zero_has_no_fill():
    out = _waterfall_html(Latency())
    assert "width:0%" in out
    assert "STT" in out


def test_waterfall_scales_to_peak():
    out = _waterfall_html(Latency(stt_ms=100, total_ms=200))
    assert "width:50%" in out  # stt 100 of peak 200
    assert "width:100%" in out  # total


# --- sentiment sparkline ---


def test_sentiment_svg_empty_is_blank():
    assert _sentiment_svg(Sentiment()) == ""


def test_sentiment_svg_single_point_centered():
    out = _sentiment_svg(Sentiment(by_turn=[0.0]))
    assert "<polyline" in out
    assert "160.0,45.0" in out  # centered x, midline y


def test_sentiment_svg_multi_point_and_clamps():
    out = _sentiment_svg(Sentiment(by_turn=[1.5, -2.0]))  # out-of-range, clamped
    assert "0.0,0.0" in out  # clamped to +1 -> top
    assert "320.0,90.0" in out  # clamped to -1 -> bottom


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


def test_banner_no_baseline_is_empty():
    assert _banner(False, 0) == ""
