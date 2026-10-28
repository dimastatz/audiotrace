# PRD 0011 — Production replay (regression capture)

**Status:** Draft
**Owner:** Dima Statz
**Source:** [Issue #48](https://github.com/dimastatz/audiotrace/issues/48)
**Related:** [PRD 0008 (regression gate)](./0008-regression-gate.md),
[PRD 0009 (drift gating)](./0009-drift-gating.md),
[PRD 0010 (simulated callers)](./0010-simulated-callers.md),
[roadmap Phase 5](../roadmap.md)

## Summary

When a real call goes badly, the lesson gets lost: nobody turns that failure
into a test, so the same bug can ship again next release.

Production replay **watches production recordings, flags calls that match
failure rules, and turns them into regression test cases** that the
[regression gate](./0008-regression-gate.md) re-checks on every release. The
golden set grows automatically from real failures — which also feeds the
larger golden set that [PRD 0009 Part B](./0009-drift-gating.md) is blocked on.

**Users:** the same engineering teams, plus support and CX leads who flag bad
calls.

## Goals

- **Ingest** recordings from S3, GCS, or provider call-log APIs (Vapi,
  Retell first), incrementally — only calls not seen before.
- **Rule-based capture** with configurable thresholds over `CallReport`
  fields, e.g.:

  ```yaml
  rules:
    - name: low-quality
      when: quality.overall_score < 0.6
    - name: frustrated-caller
      when: sentiment.caller_frustration
    - name: drop-off
      when: events.drop_off
    - name: compliance
      when: events.compliance_flags
  ```

- **Deduplication** — calls with the same failure signature (rule +
  `events.failure_type` + intent + nearest-transcript similarity) collapse into
  one candidate case with an occurrence count; a hundred identical failures
  become one test.
- **PII redaction before storage** — transcript text and audio segments are
  redacted (names, phone numbers, emails, card/account numbers, addresses)
  before anything is written as a test case. Unredacted audio never lands in
  the test-case store.
- **Human review** — captured cases land in a `pending` queue; a reviewer
  approves (joins the suite) or discards. `audiotrace replay review` CLI first;
  a UI is out of scope here.
- **Re-check on release** — approved cases become fixtures the existing
  GitHub Action gates on, either as recordings + baseline expectations or (once
  [PRD 0010](./0010-simulated-callers.md) lands) as replayable scenarios.

## Non-goals

- **Real-time / streaming monitoring and alerting.** Batch ingestion on a
  schedule is enough.
- **A hosted review UI or dashboard.** CLI + files in the repo first; a hosted
  tier is a later commercial decision.
- **ML-learned failure detection.** Rules are explicit and configurable.
- **Storing unredacted production audio** anywhere AudioTrace controls.

## Design notes

- **Pipeline:** `ingest → analyze() → match rules → dedupe → redact → pending
  → review → approved suite`.
- **Case format:** a directory per case — redacted audio, redacted
  `CallReport` JSON, `case.yaml` (rule hit, signature, occurrence count, source
  call IDs, reviewer, status). Lives in the customer's repo next to golden
  calls.
- **Replay semantics:** a recorded call can't be re-run against a new agent
  version directly. Two modes: (1) *re-analysis* — re-check the recording with
  the current extractor stack (catches measurement drift); (2) *scenario
  replay* — derive a [PRD 0010](./0010-simulated-callers.md) scenario from the
  case (caller goal + persona from the transcript) and run it against the new
  agent. Mode (2) is what actually catches agent regressions, so this PRD
  depends on 0010 for full value.
- **Redaction** reuses the compliance/PII detection planned in
  [Phase 3](../roadmap.md); audio redaction = bleep/silence the matched word
  spans using existing word timestamps.
- **Contract impact:** none required on `CallReport`; case metadata lives in
  `case.yaml`.
- Cloud SDKs behind `pip install audiotrace[replay]`.

## Open questions

- Dedup signature: is rule + failure_type + intent enough, or do we need
  transcript embeddings from day one?
- Where does the pending queue live for teams that don't want cases in git
  (bucket prefix vs. repo directory)?
- Redaction recall target — what miss rate is acceptable before a case may be
  stored?

## Success metrics

- The test suite **grows automatically** from real failures.
- Previously seen failure types **don't recur** in later releases.

## Acceptance criteria

- Ingest from a local directory, S3, and GCS (cloud SDKs mocked in tests);
  re-running ingestion skips already-seen calls.
- Rules parse from YAML and match against `CallReport` fields with clear
  errors on bad expressions.
- N calls with the same signature produce one case with `count == N`.
- No stored case contains detectable PII in transcript text; matched audio
  spans are silenced.
- Cases stay `pending` until approved; only approved cases are picked up by
  the gate / Action.
- `./scripts/test_local.sh test` passes with coverage ≥ 95%.
