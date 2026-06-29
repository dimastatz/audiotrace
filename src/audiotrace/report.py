"""Customer-facing report rendering.

Turns a :class:`~audiotrace.models.CallReport` (or a pair of them) into a
compact headline **summary** and renders it as **JSON** and a standalone
**HTML** page a customer can actually read. Comparing a current report against
a committed baseline yields run-over-run *deltas* with regression flags — the
same drift signal the CI article asserts on, made human-readable.

Pure standard library + the existing models; no new dependencies.
"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass
from pathlib import Path

from audiotrace.models import CallReport


@dataclass(frozen=True)
class Metric:
    """A single headline metric in a report summary.

    Attributes:
        key: Stable machine identifier (matches across reports for deltas).
        label: Human-readable name for display.
        value: The metric value (number, bool, or string).
        unit: Formatting hint — one of "score", "wpm", "ms", "usd", or "".
        higher_is_better: Direction for regression detection. True when a larger
            value is better, False when smaller is better, None for neutral
            metrics (e.g. outcome, duration) that are not drift-tracked.
    """

    key: str
    label: str
    value: float | int | str | bool
    unit: str = ""
    higher_is_better: bool | None = None


@dataclass(frozen=True)
class Delta:
    """A run-over-run change in one metric between a baseline and a new report."""

    key: str
    label: str
    before: float
    after: float
    change: float
    regressed: bool


def summarize(report: CallReport) -> list[Metric]:
    """Reduce a full CallReport to the headline metrics a reviewer cares about."""
    quality = report.quality
    sentiment = report.sentiment
    events = report.events
    duration_ms = report.media.duration_ms if report.media else 0

    return [
        Metric("outcome", "Outcome", events.outcome),
        Metric("quality_score", "Quality score", round(quality.overall_score, 2), "score", True),
        Metric("sentiment", "Sentiment", round(sentiment.overall, 2), "score", True),
        Metric("caller_frustration", "Caller frustrated", sentiment.caller_frustration, "", False),
        Metric("interruptions", "Interruptions", quality.interruptions, "", False),
        Metric("speaking_pace_wpm", "Speaking pace", round(quality.speaking_pace_wpm, 1), "wpm"),
        Metric("response_p95_ms", "Response latency (p95)", _response_p95_ms(report), "ms", False),
        Metric("drop_off", "Dropped call", events.drop_off, "", False),
        Metric("compliance_flags", "Compliance flags", len(events.compliance_flags), "", False),
        Metric("cost_usd", "Cost", round(report.cost.total_usd, 4), "usd", False),
        Metric("duration_ms", "Duration", duration_ms, "ms"),
    ]


def diff(baseline: CallReport, current: CallReport) -> list[Delta]:
    """Compute run-over-run deltas for every drift-tracked metric.

    Neutral metrics (``higher_is_better is None``) and non-numeric metrics are
    skipped. A metric is ``regressed`` when it moved in the worse direction.
    """
    before_by_key = {m.key: m for m in summarize(baseline)}
    deltas: list[Delta] = []
    for metric in summarize(current):
        if metric.higher_is_better is None:
            continue
        base = before_by_key.get(metric.key)
        if base is None:
            continue
        before = _as_number(base.value)
        after = _as_number(metric.value)
        change = round(after - before, 6)
        if metric.higher_is_better:
            regressed = change < 0
        else:
            regressed = change > 0
        deltas.append(Delta(metric.key, metric.label, before, after, change, regressed))
    return deltas


def render_json(report: CallReport, baseline: CallReport | None = None) -> str:
    """Render the summary (and deltas, if a baseline is given) plus the full report as JSON."""
    payload: dict[str, object] = {
        "summary": {m.key: m.value for m in summarize(report)},
        "report": report.model_dump(),
    }
    if baseline is not None:
        payload["deltas"] = [
            {
                "key": d.key,
                "before": d.before,
                "after": d.after,
                "change": d.change,
                "regressed": d.regressed,
            }
            for d in diff(baseline, report)
        ]
    return json.dumps(payload, indent=2)


def render_html(report: CallReport, baseline: CallReport | None = None) -> str:
    """Render a standalone, self-contained HTML report page."""
    metrics = summarize(report)
    deltas = diff(baseline, report) if baseline is not None else []
    rows = "\n".join(_metric_row(m) for m in metrics)
    deltas_section = _deltas_section(deltas) if baseline is not None else ""
    regressions = sum(1 for d in deltas if d.regressed)
    banner = _banner(baseline is not None, regressions)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AudioTrace call report</title>
<style>
  body {{ font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem auto;
         max-width: 720px; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #eee; }}
  th {{ color: #666; font-weight: 600; }}
  td.value {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .banner {{ padding: .75rem 1rem; border-radius: 6px; font-weight: 600; }}
  .ok {{ background: #e7f6ec; color: #176c33; }}
  .bad {{ background: #fdecea; color: #a31515; }}
  .regressed {{ color: #a31515; }}
  .improved {{ color: #176c33; }}
  footer {{ color: #999; font-size: .8rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>AudioTrace call report</h1>
{banner}
<table>
<thead><tr><th>Metric</th><th class="value">Value</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
{deltas_section}
<footer>Generated by AudioTrace.</footer>
</body>
</html>
"""


def write_report(
    report: CallReport,
    output_dir: str | Path,
    baseline: CallReport | None = None,
    stem: str = "report",
) -> dict[str, Path]:
    """Write ``<stem>.json`` and ``<stem>.html`` into ``output_dir``.

    Creates ``output_dir`` if needed. Returns the two written paths keyed by
    ``"json"`` and ``"html"``.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    html_path = directory / f"{stem}.html"
    json_path.write_text(render_json(report, baseline), encoding="utf-8")
    html_path.write_text(render_html(report, baseline), encoding="utf-8")
    return {"json": json_path, "html": html_path}


# --- internals ---


def _response_p95_ms(report: CallReport) -> int:
    """p95 (nearest-rank) of agent-response gap durations, 0 when no spans."""
    durations = [span.duration_ms for span in report.latency.waterfall]
    if not durations:
        return 0
    ordered = sorted(durations)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def _as_number(value: float | int | str | bool) -> float:
    """Coerce a metric value to a float for delta math (bools become 0/1)."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def _format_value(metric: Metric) -> str:
    """Render a metric value for display, escaped for HTML."""
    value = metric.value
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if metric.unit == "usd":
        return f"${float(value):.4f}"
    if metric.unit == "wpm":
        return f"{float(value):.1f} wpm"
    if metric.unit == "ms":
        return f"{int(value)} ms"
    if metric.unit == "score":
        return f"{float(value):.2f}"
    return html.escape(str(value))


def _metric_row(metric: Metric) -> str:
    label = html.escape(metric.label)
    return f'<tr><td>{label}</td><td class="value">{_format_value(metric)}</td></tr>'


def _deltas_section(deltas: list[Delta]) -> str:
    if not deltas:
        return ""
    rows = "\n".join(_delta_row(d) for d in deltas)
    return (
        "<h2>Change vs. baseline</h2>\n"
        '<table>\n<thead><tr><th>Metric</th><th class="value">Before</th>'
        '<th class="value">After</th><th class="value">Change</th></tr></thead>\n'
        f"<tbody>\n{rows}\n</tbody>\n</table>"
    )


def _delta_row(delta: Delta) -> str:
    cls = "regressed" if delta.regressed else ("improved" if delta.change != 0 else "")
    sign = "+" if delta.change > 0 else ""
    return (
        f'<tr class="{cls}"><td>{html.escape(delta.label)}</td>'
        f'<td class="value">{_trim(delta.before)}</td>'
        f'<td class="value">{_trim(delta.after)}</td>'
        f'<td class="value">{sign}{_trim(delta.change)}</td></tr>'
    )


def _trim(number: float) -> str:
    """Drop a trailing ``.0`` so whole numbers read cleanly."""
    return str(int(number)) if number == int(number) else f"{number:g}"


def _banner(has_baseline: bool, regressions: int) -> str:
    if not has_baseline:
        return ""
    if regressions:
        label = "regression" if regressions == 1 else "regressions"
        return f'<p class="banner bad">{regressions} {label} vs. baseline</p>'
    return '<p class="banner ok">No regressions vs. baseline</p>'
