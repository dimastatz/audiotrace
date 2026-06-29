# PRD 0007 — Report output (JSON + HTML summary)

**Status:** In progress
**Owner:** Dima Statz
**Related:** [roadmap Phase M, Workstream A](../roadmap.md),
[devto-3 (CI / drift)](../articles/devto-3-voice-agents-in-ci.md)

## Summary

Turn a `CallReport` into a customer-readable **summary** and render it as both
**JSON** and a standalone **HTML** page. Comparing a current report against a
committed **baseline** report produces run-over-run **deltas** with regression
flags. This is the first sellable increment of Phase M: the artifact a pilot
customer actually opens, and the machine-readable output a GitHub Action gates
on.

Lives in `src/audiotrace/report.py`, fed by the existing `analyze()` output. No
new dependencies (standard library + the existing models).

## Goals

- **Headline summary** — reduce the full `CallReport` to the metrics a reviewer
  cares about: outcome, quality score, sentiment, caller frustration,
  interruptions, speaking pace, p95 response latency, drop-off, compliance flag
  count, cost, and duration.
- **JSON output** — `render_json(report, baseline=None)` returns the summary,
  the full `report.model_dump()`, and (when a baseline is given) the deltas. This
  is what CI / the GitHub Action consumes.
- **HTML output** — `render_html(report, baseline=None)` returns a single
  self-contained page (inline CSS, no assets) with a metrics table and, with a
  baseline, a "Change vs. baseline" table plus a pass/fail banner.
- **Run-over-run deltas** — `diff(baseline, current)` flags each drift-tracked
  metric as `regressed` when it moved in the worse direction (lower quality,
  higher cost/latency, newly frustrated/dropped).
- **Write helper** — `write_report(report, output_dir, baseline=None, stem)`
  writes `<stem>.json` and `<stem>.html`.
- **Run fully locally**, no network, consistent with the rest of the pipeline.

## Non-goals

- **Multi-call / aggregate reports** (a whole test run, p50/p95 across many
  calls). This PRD is per-call plus a single baseline comparison; run-level
  rollups are the "baseline + drift check" and GitHub Action items that build on
  this output.
- **Configurable thresholds / gating policy.** `diff` reports the *direction* of
  change; deciding what magnitude fails a build belongs to the CI wrapper, not
  here.
- **Charting / JS interactivity.** The HTML is a static, printable summary.
- **Decomposed latency sub-spans** — uses `latency.waterfall` as produced by
  [PRD 0006](./0006-latency.md).

## Metric direction (`higher_is_better`)

| Metric                | Unit   | Direction        |
|-----------------------|--------|------------------|
| outcome               | —      | neutral (string) |
| quality_score         | score  | higher better    |
| sentiment             | score  | higher better    |
| caller_frustration    | bool   | lower better     |
| interruptions         | —      | lower better     |
| speaking_pace_wpm     | wpm    | neutral          |
| response_p95_ms       | ms     | lower better     |
| drop_off              | bool   | lower better     |
| compliance_flags      | —      | lower better     |
| cost_usd              | usd    | lower better     |
| duration_ms           | ms     | neutral          |

Neutral metrics are shown but not delta-tracked.

## Acceptance criteria

- `render_json(report)` returns valid JSON with `summary` and `report` keys and
  no `deltas`; with a baseline it additionally includes `deltas`.
- `render_html(report)` returns a `<!doctype html>` document; string values are
  HTML-escaped.
- With a baseline, the HTML shows a green "No regressions" banner or a red
  "N regression(s)" banner, and a per-metric change table.
- `diff` flags a metric `regressed` iff it moved in the worse direction; neutral
  and string metrics are skipped.
- `write_report` creates `output_dir` and writes both files.
- `./scripts/test_local.sh test` passes with full coverage for the new module.
