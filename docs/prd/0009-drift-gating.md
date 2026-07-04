# PRD 0009 — Trustworthy drift gating: extractor provenance + distributional checks

**Status:** Draft
**Owner:** Dima Statz
**Source:** Design-partner feedback on the CI / signal-extraction article series.
**Related:** [PRD 0007 (report)](./0007-report.md),
[PRD 0008 (regression gate)](./0008-regression-gate.md),
[roadmap Phase M / Phase 4](../roadmap.md)

## Summary

The regression gate ([PRD 0008](./0008-regression-gate.md)) implicitly assumes
that when a metric moves, **the agent changed**. But AudioTrace's extractors —
Whisper (transcript), pyannote (diarization), Librosa (quality), the sentiment
transformer — are *themselves models*. The measurement layer has its own drift
surface, so a moved metric has **two hypotheses: the agent changed, or the
measurement changed.** Two concrete failure modes follow, both live in `1.2.0`:

1. **Attribution ambiguity.** A `CallReport` records *no* provenance — not the
   `audiotrace` version, the Whisper model (`base`), the pyannote pipeline
   (`speaker-diarization-3.1`), the sentiment model
   (`distilbert…sst-2`), or the Librosa version. When a number moves you cannot
   tell an agent regression from an extractor bump. You chase ghosts.

2. **Fragile assertions.** Audio-derived signals wiggle run-to-run. The current
   gate asserts on **per-call exact values** with abs/rel tolerances
   ([`check.py`](../../src/audiotrace/check.py)); tuning tolerances to absorb
   that noise is a losing game. Asserting on **distributions** against a golden
   call set — failing when PSI/KL drift exceeds a threshold — is stable.

The principle: **version and pin the extractors the same way you pin the agent**,
and gate on distributions rather than per-call values for continuous signals.

---

## Part A — Extractor provenance (near-term, actionable now)

**Goal:** every `CallReport` records the versioned identity of the extraction
stack that produced it, so drift is attributable.

- Add a provenance sub-model to [`models.py`](../../src/audiotrace/models.py)
  (e.g. `ExtractionMeta`) capturing: `audiotrace` version, Whisper model name,
  pyannote pipeline name, sentiment model id, Librosa version (optionally
  Python / Torch). Additive and non-breaking — defaults present, same pattern as
  the `diarization_confidence` field.
- Populate it in [`core.analyze()`](../../src/audiotrace/core.py); surface it in
  [`report.py`](../../src/audiotrace/report.py) (JSON + HTML).
- In [`check.py`](../../src/audiotrace/check.py), when the baseline's provenance
  differs from the current run's, **label the run** so a metric move that
  coincides with a stack change reads as *"measurement changed"*, not a silent
  agent regression.
- `models.py` is a public contract → update the README `CallReport` tree.

**Acceptance criteria**

- `CallReport` carries provenance: `audiotrace` + every model/library version.
- `diff`/`check` surface a *provenance-changed* signal when baseline ≠ current
  stack.
- README `CallReport` tree updated; `./scripts/test_local.sh test` green at ≥95%.

---

## Part B — Distributional drift gate (Phase 4; blocked on golden set)

**Goal:** complement per-call tolerance gating with a **run-level distributional
check** for continuous, noisy signals.

- For continuous metrics (`quality_score`, `sentiment`, `speaking_pace_wpm`,
  `response_p95_ms`, `cost_usd`), compare the metric's distribution across the
  golden set (current run) vs the baseline run using **PSI** (primary) and/or
  **KL divergence**; fail the gate when drift exceeds a configured threshold.
- **Keep** the per-call abs/rel gate for hard/binary events (frustration,
  drop-off, compliance flags) where a distribution is meaningless and per-call
  pinpointing matters. (Recommended: augment, not replace.)
- New module (e.g. `drift.py`), wired into `check.py` as a run-level result
  alongside the existing per-call `Regression` list.

**Hard prerequisite — a golden call set of meaningful size.** Today the golden
set is **n = 1** (`tests/fixtures/paradise_hotel_booking_60s`), so PSI/KL are
undefined/unstable. Part B needs ~20+ representative calls, plausibly sourced
from the **first design-partner pilot** — which is why it sequences to Phase 4,
after the first paid dollar, not before.

**Open questions**

- PSI vs KL vs both; binning strategy for small samples; minimum golden-set size
  for a stable metric.
- Threshold config location (mirror `DEFAULT_THRESHOLDS` in `check.py`).
- Confirm augment-vs-replace once real distributions exist.

**Acceptance criteria (when unblocked)**

- Given a golden set, `check()` computes per-metric PSI/KL (current vs baseline)
  and fails when drift exceeds threshold.
- Hard/binary events remain gated per-call.
- Thresholds are configurable and documented.

## Non-goals

- Auto-learning thresholds from history (static config, as in PRD 0008).
- Trend dashboards over time (separate "session review" item).
- Provider-fetched recordings (Phase 2 adapters).
