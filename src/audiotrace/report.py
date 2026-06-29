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

from audiotrace.models import CallReport, Latency, Sentiment, Transcript, Turn


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
    """Render a standalone, self-contained HTML report page (dashboard style)."""
    metrics = {m.key: m for m in summarize(report)}
    deltas = {d.key: d for d in diff(baseline, report)} if baseline is not None else {}
    regressions = sum(1 for d in deltas.values() if d.regressed)
    banner = _banner(baseline is not None, regressions)

    tile_keys = ("outcome", "quality_score", "sentiment", "response_p95_ms", "cost_usd")
    tiles = "\n".join(_tile(metrics[k], deltas.get(k)) for k in tile_keys)

    transcript = _transcript_html(report.transcript)
    waterfall = _waterfall_html(report.latency)
    sentiment_svg = _sentiment_svg(report.sentiment)
    sentiment_block = f'<h3 class="card-sub">Sentiment</h3>{sentiment_svg}' if sentiment_svg else ""
    flags_list = _flags_list(report.events.compliance_flags)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AudioTrace call report</title>
<style>
  :root {{ --bg: #f3f4ee; --card: #fff; --line: #e7e7df; --muted: #6b6b6b; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.5 -apple-system, system-ui, "Segoe UI", sans-serif;
         background: var(--bg); color: #1a1a1a; margin: 0; padding: 2rem 1rem; }}
  .page {{ max-width: 920px; margin: 0 auto; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-start;
           gap: 1rem; }}
  h1 {{ font-size: 1.5rem; margin: 0; }}
  .sub {{ color: var(--muted); margin: .15rem 0 0; }}
  .banner {{ padding: .7rem 1rem; border-radius: 10px; font-weight: 600; margin: 1rem 0; }}
  .flags-badge {{ background: #fdecea; color: #a31515; font-weight: 600;
                 padding: .4rem .7rem; border-radius: 999px; white-space: nowrap; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: .75rem; margin: 1.25rem 0; }}
  .tile {{ background: #f8f9f3; border: 1px solid var(--line); border-radius: 12px;
          padding: .85rem 1rem; }}
  .tile-label {{ color: var(--muted); font-size: .85rem; }}
  .tile-value {{ font-size: 1.7rem; font-weight: 700; margin-top: .15rem;
                font-variant-numeric: tabular-nums; }}
  .tile-sub {{ font-size: .85rem; margin-top: .2rem; font-weight: 600; }}
  .tile-sub.down {{ color: #b3261e; }}
  .tile-sub.up {{ color: #176c33; }}
  .tile-sub.flat {{ color: #8a8a8a; }}
  .pill {{ display: inline-block; font-size: 1rem; font-weight: 700;
          padding: .15rem .7rem; border-radius: 999px; }}
  .pill.ok {{ background: #e7f6ec; color: #176c33; }}
  .pill.warn {{ background: #fbeccd; color: #8a5a12; }}
  .pill.bad {{ background: #fdecea; color: #a31515; }}
  .pill.neutral {{ background: #ececec; color: #555; }}
  .ok {{ background: #e7f6ec; color: #176c33; }}
  .bad {{ background: #fdecea; color: #a31515; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px;
          padding: 1.1rem 1.25rem; }}
  .card h2 {{ font-size: .8rem; letter-spacing: .05em; text-transform: uppercase;
             color: var(--muted); margin: 0 0 .75rem; }}
  .card-sub {{ font-size: .8rem; letter-spacing: .05em; text-transform: uppercase;
              color: var(--muted); margin: 1.25rem 0 .5rem; }}
  .bubble {{ display: flex; gap: .6rem; margin-bottom: .75rem; }}
  .avatar {{ flex: none; width: 32px; height: 32px; border-radius: 50%;
            display: grid; place-items: center; font-size: .7rem; font-weight: 700; }}
  .bubble.agent .avatar {{ background: #dbe7fb; color: #2f6fdb; }}
  .bubble.caller .avatar {{ background: #d9f0e2; color: #1f9d57; }}
  .bubble-body {{ background: #f4f5ef; border-radius: 12px; padding: .5rem .75rem; }}
  .bubble-head {{ font-weight: 600; font-size: .85rem; }}
  .bubble-head .ts {{ color: var(--muted); font-weight: 400; }}
  .empty {{ color: var(--muted); }}
  .wf-row {{ display: flex; align-items: center; gap: .6rem; margin-bottom: .55rem; }}
  .wf-name {{ width: 44px; color: #333; font-weight: 600; }}
  .wf-track {{ flex: 1; height: 12px; background: #ecebe2; border-radius: 999px; }}
  .wf-bar {{ display: block; height: 12px; border-radius: 999px; }}
  .wf-val {{ width: 64px; text-align: right; font-variant-numeric: tabular-nums; }}
  .spark {{ width: 100%; height: 90px; }}
  ul.flags {{ list-style: none; padding: 0; margin: 0; }}
  ul.flags li {{ color: #a31515; padding: .15rem 0; }}
  footer {{ color: #999; font-size: .8rem; margin-top: 1.5rem; }}
  @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="page">
<header>
  <div>
    <h1>Call report</h1>
    <p class="sub">{_header_sub(report)}</p>
  </div>
  {_flags_badge(report.events.compliance_flags)}
</header>
{banner}
<section class="tiles">
{tiles}
</section>
<section class="grid">
  <div class="card">
    <h2>Transcript</h2>
    {transcript}
  </div>
  <div class="card">
    <h2>Latency waterfall</h2>
    {waterfall}
    {sentiment_block}
    {flags_list}
  </div>
</section>
<footer>Generated by AudioTrace.</footer>
</div>
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


def _format_ts(ms: int) -> str:
    """Format milliseconds from the call start as ``M:SS``."""
    total = int(ms / 1000)
    return f"{total // 60}:{total % 60:02d}"


def _status_class(outcome: str) -> str:
    """Map an event outcome to a status-pill CSS class."""
    return {"completed": "ok", "dropped": "warn", "failed": "bad"}.get(outcome, "neutral")


def _header_sub(report: CallReport) -> str:
    """Build the header subtitle from the signals available on a CallReport."""
    parts: list[str] = []
    if report.events.intent_detected:
        parts.append(html.escape(report.events.intent_detected))
    if report.media:
        parts.append(_format_ts(report.media.duration_ms))
        parts.append(html.escape(report.media.file_format))
    return " · ".join(parts)


def _flags_badge(flags: list[str]) -> str:
    """Top-right compliance-flag count badge, empty when there are no flags."""
    if not flags:
        return ""
    noun = "flag" if len(flags) == 1 else "flags"
    return f'<span class="flags-badge">⚠ {len(flags)} {noun}</span>'


def _flags_list(flags: list[str]) -> str:
    """A labelled list of compliance flags, empty when there are none."""
    if not flags:
        return ""
    items = "\n".join(f"<li>⚠ {html.escape(flag)}</li>" for flag in flags)
    return f'<h3 class="card-sub">Flags</h3><ul class="flags">\n{items}\n</ul>'


def _tile_value(metric: Metric) -> str:
    """Render a tile's headline value — a status pill for outcome, else formatted."""
    if metric.key == "outcome":
        outcome = str(metric.value)
        return f'<span class="pill {_status_class(outcome)}">{html.escape(outcome)}</span>'
    return _format_value(metric)


def _tile_delta(delta: Delta) -> str:
    """Render a tile's run-over-run sub-line, coloured by regression direction."""
    if delta.change == 0:
        return f'<div class="tile-sub flat">· vs {_trim(delta.before)}</div>'
    arrow = "↑" if delta.change > 0 else "↓"
    cls = "down" if delta.regressed else "up"
    return f'<div class="tile-sub {cls}">{arrow} vs {_trim(delta.before)}</div>'


def _tile(metric: Metric, delta: Delta | None) -> str:
    sub = _tile_delta(delta) if delta is not None else ""
    return (
        f'<div class="tile"><div class="tile-label">{html.escape(metric.label)}</div>'
        f'<div class="tile-value">{_tile_value(metric)}</div>{sub}</div>'
    )


def _initials(speaker: str) -> str:
    """Up-to-two-letter avatar initials for a speaker label."""
    letters = "".join(part[0] for part in speaker.split()[:2]).upper()
    return html.escape(letters or "?")


def _bubble(turn: Turn) -> str:
    side = "agent" if "agent" in turn.speaker.lower() else "caller"
    return (
        f'<div class="bubble {side}"><div class="avatar">{_initials(turn.speaker)}</div>'
        f'<div class="bubble-body"><div class="bubble-head">{html.escape(turn.speaker)} '
        f'<span class="ts">{_format_ts(turn.start_ms)}</span></div>'
        f'<div class="bubble-text">{html.escape(turn.text)}</div></div></div>'
    )


def _transcript_html(transcript: Transcript) -> str:
    """Render the transcript as speaker chat bubbles, or a plain fallback line."""
    turns = transcript.turns
    if not turns:
        return f'<p class="empty">{html.escape(transcript.full_text or "(no transcript)")}</p>'
    return "\n".join(_bubble(turn) for turn in turns)


_LATENCY_STAGES = (
    ("STT", "stt_ms", "#2f6fdb"),
    ("LLM", "llm_first_token_ms", "#1f9d57"),
    ("TTS", "tts_ms", "#e8943a"),
    ("Total", "total_ms", "#444"),
)


def _waterfall_html(latency: Latency) -> str:
    """Render STT/LLM/TTS/Total as horizontal bars scaled to the largest stage."""
    stages = [(name, getattr(latency, attr), color) for name, attr, color in _LATENCY_STAGES]
    peak = max((ms for _, ms, _ in stages), default=0)
    return "\n".join(_waterfall_row(name, ms, color, peak) for name, ms, color in stages)


def _waterfall_row(name: str, ms: int, color: str, peak: int) -> str:
    pct = (ms / peak * 100) if peak else 0
    return (
        f'<div class="wf-row"><span class="wf-name">{name}</span>'
        f'<span class="wf-track"><span class="wf-bar" '
        f'style="width:{pct:.0f}%;background:{color}"></span></span>'
        f'<span class="wf-val">{ms} ms</span></div>'
    )


def _sentiment_svg(sentiment: Sentiment) -> str:
    """Inline SVG sparkline of per-turn sentiment, empty when there are no points."""
    points = sentiment.by_turn
    if not points:
        return ""
    width, height = 320.0, 90.0
    count = len(points)
    coords = []
    for index, value in enumerate(points):
        x = index / (count - 1) * width if count > 1 else width / 2
        clamped = max(-1.0, min(1.0, value))
        y = (1 - (clamped + 1) / 2) * height
        coords.append(f"{x:.1f},{y:.1f}")
    pts = " ".join(coords)
    return (
        f'<svg class="spark" viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="none">'
        f'<polyline points="{pts}" fill="none" stroke="#d23b3b" stroke-width="2"/></svg>'
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
