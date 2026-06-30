# PRD 0008 — Baseline + regression gate (CI)

**Status:** In progress
**Owner:** Dima Statz
**Related:** [roadmap Phase M, Workstream A](../roadmap.md),
[PRD 0007 (report)](./0007-report.md),
[devto-3 (CI / drift)](../articles/devto-3-voice-agents-in-ci.md)

## Summary

Turn the per-call `diff()` from [PRD 0007](./0007-report.md) into a **build
gate**: analyze a set of golden call recordings, compare each against a
committed **baseline**, and **exit non-zero** when a metric drifts past its
tolerance. This is the willingness-to-pay moment of the Phase M wedge — a bad
prompt/model/voice change turns the build red, the same as any failing test.

Ships as:
- `src/audiotrace/check.py` — the pure gating logic + baseline persistence
  (fully covered).
- `audiotrace` console script (`src/audiotrace/cli.py`) — `baseline` and
  `check` subcommands over a directory of recordings.
- `action.yml` — a composite GitHub Action so a customer drops it into CI in
  <15 minutes.

## Goals

- **Commit a baseline** — `audiotrace baseline <dir> -o baseline.json` analyzes
  every recording in `<dir>` and writes a baseline keyed by file stem.
- **Gate against it** — `audiotrace check <dir> -b baseline.json` re-analyzes,
  compares with `diff()`, prints a pass/fail summary, writes the HTML+JSON
  report per call, and exits non-zero on any out-of-tolerance regression.
- **Tolerances** — per-metric allowed drift so conversational noise doesn't
  flake the build. Absolute or relative band, whichever is larger; metrics with
  no entry use zero tolerance (any regression fails).
- **New fixtures don't break the build** — a call absent from the baseline is
  *skipped* (reported), not failed.
- **GitHub Action** — composite action wrapping install + `audiotrace check`,
  uploading the report directory as an artifact even on failure.

## Non-goals

- **Run-level aggregate dashboard** (p50/p95 across the whole run, trends over
  time). The gate is per-call pass/fail plus a per-call report; the multi-call
  "session review" view is a separate, later item.
- **Threshold auto-tuning / statistical baselines.** Tolerances are static
  config; learning them from history is out of scope.
- **Fetching recordings from a provider.** `<dir>` is local files; provider
  adapters are [Phase 2](../roadmap.md).

## Default tolerances

| Metric            | Tolerance            | Rationale                              |
|-------------------|----------------------|----------------------------------------|
| quality_score     | ±0.05 absolute       | absorb scoring noise, catch real drops |
| sentiment         | ±0.10 absolute       | tone varies call to call               |
| response_p95_ms   | +15% relative        | matches the article's latency budget   |
| cost_usd          | +20% relative        | provider price / verbosity drift       |
| interruptions     | +1 absolute          | one extra barge-in is noise            |
| everything else   | 0 (any regression)   | frustration / drop-off / compliance    |

## Acceptance criteria

- `check(current, baseline)` returns a `CheckResult` whose `passed` is False iff
  at least one call has a regression exceeding its tolerance.
- A regression within tolerance does **not** fail the gate.
- Calls missing from the baseline appear in `skipped`, not `regressions`.
- `write_baseline` / `load_baseline` round-trip a run of `CallReport`s.
- `audiotrace check` exits 1 on failure, 0 on pass, and always writes reports.
- `action.yml` installs AudioTrace, runs the gate, and uploads the report
  artifact with `if: always()`.
- `./scripts/test_local.sh test` passes with full coverage for `check.py`.
