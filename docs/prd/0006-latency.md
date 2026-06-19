# PRD 0006 — Latency waterfall extraction

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 1](../roadmap.md), [PRD 0001](./0001-mediainfo.md) (open question: latency
derivable from audio alone — answered "yes")

## Summary

Implement the `waterfall` portion of `Latency` extraction in the `analyze()`
pipeline. This stage measures how long the agent took to respond after the
caller stopped speaking, turn by turn, and surfaces each response gap as a
`LatencySpan` in `report.latency.waterfall`. It runs entirely on the
diarized transcript already produced by [PRD 0002](./0002-transcript.md) —
no provider/webhook metadata is required.

## Goals

- **Run entirely locally, no external API calls and no provider metadata
  required**: derive response latency purely from `Transcript.turns`
  timestamps, the same data already available after diarization.
- **Detect agent response gaps**: for every caller turn immediately followed
  by an agent turn, compute the gap between the caller's `end_ms` and the
  agent's `start_ms`.
- **Populate `report.latency.waterfall`**: emit one `LatencySpan` per
  detected agent response gap, named `"agent_response"`, in chronological
  order.
- **Filter noise**: skip transitions with a negative or near-zero gap
  (overlapping speech / barge-in — already captured by
  `Quality.interruptions`) and gaps below a small noise floor.

## Non-goals

- **Decomposing a response gap into STT / LLM-first-token / LLM-full-response
  / TTS sub-spans.** Audio alone cannot distinguish where time was spent
  inside a single silence — that requires provider-supplied timing metadata
  (e.g., a Vapi/Retell webhook payload). The existing `Latency.stt_ms`,
  `llm_first_token_ms`, `llm_full_response_ms`, and `tts_ms` fields are left
  untouched by this PRD and stay at their defaults until a provider adapter
  ([roadmap Phase 2](../roadmap.md)) can populate them.
- **`Latency.total_ms`.** This field currently tracks the wall-clock time of
  the `analyze()` call itself (a pipeline-performance metric set in
  `core.py`), which is a different concept from in-call response latency.
  Not in scope here.
- **Caller-side response gaps** (agent finishes → caller takes a long time to
  reply). Useful for caller-engagement analysis but not a voice-agent
  responsiveness signal; can be added as a second span `name` later if
  needed.
- Silence detection from raw audio (RMS-based) — already covered by
  `Quality.silence_gaps` ([PRD 0003](./0003-quality.md)); this PRD reuses
  turn timestamps instead of re-running Librosa.

## Proposed pipeline

```
Transcript.turns (speaker-labeled, timestamped)
        → pairwise scan for caller → agent transitions
        → gap_ms = agent.start_ms - caller.end_ms
        → drop gap_ms <= noise floor (overlap / negligible gap)
        → LatencySpan(name="agent_response", start_ms=caller.end_ms, duration_ms=gap_ms)
        → Latency.waterfall (CallReport)
```

Speaker labels follow the same `"agent"` / `"caller"` convention already used
in `cost.py::_speaker_char_counts`. When labels are unavailable (e.g.
diarization fell back to `"unknown"`), no waterfall spans are produced —
matching the silent degrade already used elsewhere in the pipeline rather
than guessing at attribution.

## Data contract (existing — do not change)

`src/audiotrace/models.py::Latency` and `LatencySpan`

```python
class LatencySpan(BaseModel):
    name: str
    start_ms: int
    duration_ms: int

class Latency(BaseModel):
    stt_ms: int = 0
    llm_first_token_ms: int = 0
    llm_full_response_ms: int = 0
    tts_ms: int = 0
    total_ms: int = 0
    waterfall: list[LatencySpan] = Field(default_factory=list)
```

Only `waterfall` is populated by this PRD; the other `Latency` fields are
out of scope (see Non-goals).

### Field definitions and business impact

**`waterfall: list[LatencySpan]`** — Ordered list of response-latency spans
detected across the call.

> *Why it matters:* Response latency is the single biggest driver of how
> "alive" a voice agent feels — callers tolerate a 1-second pause but
> perceive 3+ seconds as broken or hung. Unlike `overall_score` or a single
> aggregate number, a per-turn waterfall lets teams see exactly which turns
> were slow, correlate slowness with specific intents or script branches
> (e.g., "every lookup after 'what's my balance' adds 4s"), and trend p50/p95
> response time across calls without re-parsing transcripts.

**`LatencySpan.name: str`** — The kind of span; this PRD only emits
`"agent_response"`. Kept as a free string (rather than an enum) so future
spans (`"caller_response"`, or provider-supplied `"stt"` / `"llm"` / `"tts"`
sub-spans) can be added without a schema change.

> *Why it matters:* A typed, extensible label is what lets the same list
> hold both audio-derived spans (this PRD) and, later, provider-derived
> sub-spans, without breaking existing consumers that filter by name.

**`LatencySpan.start_ms: int`** — Offset into the call, in milliseconds,
where the caller's turn ended and the agent's silence began.

> *Why it matters:* Lets a reviewer seek directly to the moment in the
> recording where the agent went quiet, rather than scrubbing the whole
> call to find slow turns.

**`LatencySpan.duration_ms: int`** — Length of the gap before the agent's
next turn began.

> *Why it matters:* The actual responsiveness number. Aggregating this
> across calls (mean, p95) is the metric ops teams alert on when a model or
> infra change regresses latency; aggregating within a call highlights
> whether slowness is consistent or a single outlier turn.

## Open questions

- What noise floor should suppress negligible gaps (e.g., normal
  conversational micro-pauses)? Proposed default: 250ms, configurable via a
  module-level constant, matching the precedent set by
  `quality.py::SILENCE_THRESHOLD_MS`.
- Should a second span name (e.g. `"caller_response"`) ship in this PRD or
  be deferred until there's a concrete consumer need? Proposed: defer —
  keep the first cut to agent-responsiveness only.

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.latency.waterfall`
  is populated whenever the transcript contains `"agent"`/`"caller"`-labeled
  turns.
- Each emitted `LatencySpan` has `name == "agent_response"`,
  `start_ms == caller_turn.end_ms`, and
  `duration_ms == agent_turn.start_ms - caller_turn.end_ms`.
- Transitions with `duration_ms` at or below the noise floor are omitted.
- Overlapping turns (`agent_turn.start_ms < caller_turn.end_ms`, i.e.
  barge-in) are omitted — these are already counted in
  `Quality.interruptions`.
- `report.latency.waterfall` is sorted in chronological order by `start_ms`.
- `Latency.stt_ms`, `llm_first_token_ms`, `llm_full_response_ms`, `tts_ms`,
  and `total_ms` are unchanged by this work.
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
