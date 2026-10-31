# Regression gate in CI

Commit a folder of golden calls and a baseline; every pull request
re-analyzes the calls and fails when the agent got worse.

```bash
audiotrace baseline tests/calls -o baseline.json        # once, and after intended changes
audiotrace check tests/calls -b baseline.json --report out/
```

`check` exits non-zero on a regression and writes a JSON + HTML report per
call (with deltas against the baseline) when `--report` is given.

## Per-call tolerances

A metric fails a call only when it moves in the worse direction by more than
its tolerance (`audiotrace.check.DEFAULT_THRESHOLDS`):

| Metric | Allowed worsening |
|---|---|
| Quality score | −0.05 |
| Sentiment | −0.10 |
| Response latency p95 | +15% |
| Cost | +20% |
| Interruptions | +1 |
| Caller frustration, dropped call, compliance flags | none |

Tune them in code:

```python
from audiotrace import Threshold, check, load_baseline

result = check(current, load_baseline("baseline.json"),
               thresholds={"quality_score": Threshold(abs=0.1)})
```

Calls with no baseline entry are skipped (reported, not failed).

## Run-level drift

Noisy audio metrics wobble per call; a whole run drifting a little in one
direction doesn't trip any per-call tolerance. So `check` also compares each
continuous metric's distribution across the run (quality, sentiment, pace,
response latency, cost) with the baseline's, using the Population Stability
Index, and fails when PSI exceeds 0.25:

```
FAIL — 0 regression(s) and 1 drifted metric(s) across 20 call(s) checked
  drift: quality_score distribution moved (PSI 0.50 > 0.25; mean 0.69 → 0.61)
```

It needs at least 10 calls present in both runs. Override with
`check(..., drift_thresholds={"quality_score": 0.1})`, or turn it off with `{}`.

## Measurement drift vs. agent drift

The extractors are models too. Every report records the stack that produced it
(`provenance`). When it differs from the baseline's, `check` prints a note
listing what changed, so a move after a Whisper or AudioTrace upgrade reads as
*measurement* drift. Re-baseline after an intended stack upgrade.

Re-analyzing **fixed** recordings only catches measurement drift; the audio
doesn't change when the agent does. To gate the agent itself, feed fresh
calls each run: [simulated callers](simulated-callers.md) or recent production
calls via [providers](providers.md).

## GitHub Action

```yaml
# .github/workflows/voice-quality.yml
name: Voice quality
on: [pull_request]
jobs:
  audiotrace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dimastatz/audiotrace@v1
        with:
          calls: tests/calls
          baseline: baseline.json
```

The Action installs FFmpeg and AudioTrace, runs the gate, and uploads the
reports as an artifact even when the build fails. Inputs: `calls`, `baseline`,
`scenarios`, `target`, `scenarios-baseline`, `report-dir`, `version`,
`python-version` (see `action.yml`).

## Worked example

[`tests/fixtures/golden`](https://github.com/dimastatz/audiotrace/tree/main/tests/fixtures/golden)
holds 20 synthetic calls with planted defects, the scripts that generated
them, a committed baseline, and how accurately AudioTrace detects each defect.
