# PRD 0005 — Events extraction pipeline

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 1/3](../roadmap.md)

## Summary

Implement the events extraction layer of the `analyze()` pipeline. This stage
derives call-level outcome signals from the transcript and audio: whether the
call completed or was abandoned, where a caller dropped off, the caller's
detected intent, the failure type when a call fails, and any compliance flags
(e.g., missing consent disclosure, PII exposure).

## Goals

- **Run entirely locally — no external API calls**: Intent classification uses a
  local `transformers` zero-shot model (same caching pattern as
  [PRD 0004](./0004-sentiment.md)); all other signals are rule-based over the
  transcript. The library must work fully offline after the initial download.
- **Determine `outcome`**: Classify the call as `completed`, `dropped`, or
  `failed` using heuristics over turn structure, trailing silence, and call
  duration.
- **Detect drop-off**: Set `drop_off` and `drop_off_turn` when the conversation
  ends abruptly — a long trailing silence or a caller turn with no agent reply.
- **Detect intent**: Populate `intent_detected` via local zero-shot
  classification over the caller's turns against a configurable label set
  (e.g., billing, support, sales, cancellation).
- **Classify failure**: Populate `failure_type` (e.g., `no_speech`,
  `silence_timeout`, `agent_error`) when `outcome == "failed"`.
- **Flag compliance issues**: Scan the transcript for missing consent
  disclosure and PII exposure, appending findings to `compliance_flags`.

## Non-goals

- Any cloud/API-based classification or PII service.
- Sentiment analysis — covered by [PRD 0004](./0004-sentiment.md).
- Provider-supplied event metadata (webhook outcomes) — covered by adapter PRDs.
- Real-time/streaming event detection.

## Proposed pipeline

```
Transcript.turns + MediaInfo.duration_ms
        → turn-structure + trailing-silence heuristics → outcome, drop_off, drop_off_turn
        → caller turns → zero-shot classifier → intent_detected
        → outcome == failed → failure-type rules → failure_type
        → regex / keyword + consent rules → compliance_flags
        → Events (CallReport)
```

## Data contract (existing — do not change)

`src/audiotrace/models.py::Events`

```python
class Events(BaseModel):
    outcome: str = "completed"               # "completed" | "dropped" | "failed"
    drop_off: bool = False
    drop_off_turn: int | None = None         # index into Transcript.turns
    intent_detected: str = ""
    failure_type: str | None = None
    compliance_flags: list[str] = Field(default_factory=list)
```

### Field definitions and business impact

**`outcome: str`** — Terminal disposition of the call: `completed`, `dropped`,
or `failed`.

> *Why it matters:* The single most important call-level KPI. Completion rate is
> the headline metric every voice-agent team reports to stakeholders. Splitting
> `dropped` (caller left) from `failed` (system broke) separates a UX problem
> from an engineering problem — they route to different teams and different
> fixes. It also gates downstream analytics: success-only cohorts for quality
> benchmarking, failure-only cohorts for incident triage.

**`drop_off: bool`** — Whether the caller abandoned the call before it reached a
natural conclusion.

> *Why it matters:* Drop-off is the clearest signal of caller frustration or a
> broken flow, and it directly hits conversion and resolution rates. A spike in
> drop-off after a release is an instant regression alarm. As a cheap boolean it
> feeds dashboards and alerting without requiring consumers to re-derive it.

**`drop_off_turn: int | None`** — The turn index where the call was abandoned,
or `None` if it completed.

> *Why it matters:* Turns drop-off from a count into a diagnosis. If 60% of
> abandonments happen on the same turn — right after the agent asks for an
> account number — that pinpoints the exact script step to redesign. Without the
> turn index, teams know *that* callers leave but not *where*, and cannot act.

**`intent_detected: str`** — The caller's primary intent (e.g., `billing`,
`cancellation`, `support`).

> *Why it matters:* Intent turns a pile of calls into a segmented funnel. Ops can
> measure resolution rate per intent, staff for the most common ones, and spot
> emerging issues ("cancellation intent up 30% this week"). It also enables
> routing analysis — were callers sent to the right flow for what they actually
> wanted?

**`failure_type: str | None`** — The category of failure when `outcome` is
`failed`, otherwise `None`.

> *Why it matters:* Failures are not all equal — `no_speech` (bad recording),
> `silence_timeout` (agent hung), and `agent_error` (logic bug) demand completely
> different responses. Categorizing them lets engineering prioritize by volume
> and burn down the largest failure class first, rather than treating "failed" as
> one opaque bucket.

**`compliance_flags: list[str]`** — List of compliance issues detected in the
call (e.g., `missing_consent`, `pii_exposed`).

> *Why it matters:* In regulated industries (healthcare, finance, collections), a
> missing consent disclosure or leaked PII is a legal and financial liability, not
> just a quality nit. Automatically flagging these across 100% of calls — versus
> the 1–2% a human QA team can sample — turns compliance from spot-check theater
> into real coverage, and produces an audit trail regulators accept.

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.events` is populated.
- `report.events.outcome` is one of `completed`, `dropped`, `failed`.
- `report.events.drop_off` is `True` with a valid `drop_off_turn` index when the
  call ends abruptly; `False` with `drop_off_turn is None` otherwise.
- `report.events.intent_detected` is a non-empty label for calls with caller
  speech, drawn from the configured label set.
- `report.events.failure_type` is set when and only when `outcome == "failed"`.
- `report.events.compliance_flags` contains `missing_consent` when no consent
  disclosure is present in a call that requires one.
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
