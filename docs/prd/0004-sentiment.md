# PRD 0004 — Sentiment extraction pipeline

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 2](../roadmap.md)

## Summary

Implement the sentiment extraction layer of the `analyze()` pipeline. This stage uses the
transcript produced by PRD 0002 to score emotional tone per speaker turn, detect sentiment
shift points, and flag caller frustration.

## Goals

- **Run entirely locally — no external API calls**: Download model weights on first use and
  cache them locally (same pattern as Whisper in `src/audiotrace/transcripts.py`). The library
  must work fully offline after the initial download.
- **Integrate a pre-trained sentiment model**: Use `transformers` pipeline with
  `distilbert-base-uncased-finetuned-sst-2-english` (or equivalent small HuggingFace model)
  running local inference via PyTorch/ONNX.
- **Model caching**: Cache the loaded pipeline in a module-level variable so repeated calls
  within the same process do not reload weights from disk.
- **Populate `by_turn`**: Produce a list of sentiment scores (−1.0 = very negative,
  +1.0 = very positive) aligned to `Transcript.turns`.
- **Populate `overall`**: Compute the mean sentiment across all turns.
- **Detect shift points**: Record turn indices where sentiment crosses a threshold in either
  direction (e.g., delta > 0.4 between consecutive turns).
- **Flag caller frustration**: Set `caller_frustration = True` when the caller's turns
  contain ≥ 2 consecutive negative scores (< −0.3).

## Non-goals

- Any cloud/API-based sentiment service (OpenAI, AWS Comprehend, Google NLP, etc.).
- Intent detection — separate PRD.
- Real-time/streaming sentiment.
- Fine-tuning the model on domain-specific voice-agent data.

## Proposed pipeline

```
Transcript.turns → sentiment model (per turn text) → by_turn scores
                 → mean → overall
                 → delta scan → shift_points
                 → caller turn filter + threshold → caller_frustration
                 → Sentiment (CallReport)
```

## Data contract (existing — do not change)

`src/audiotrace/models.py::Sentiment`

```python
class Sentiment(BaseModel):
    by_turn: list[float] = Field(default_factory=list)   # one score per turn
    overall: float = 0.0                                  # mean of by_turn
    shift_points: list[int] = Field(default_factory=list) # turn indices
    caller_frustration: bool = False
```

### Field definitions and business impact

**`by_turn: list[float]`** — Sentiment score for each speaker turn, from −1.0 (very
negative) to +1.0 (very positive), in the same order as `Transcript.turns`.

> *Why it matters:* Enables per-turn granularity that aggregate scores hide. A QA team can
> pinpoint the exact moment a conversation went wrong — e.g., the agent's third turn dropped
> to −0.7 — and use that to coach on specific phrasing. It is also the raw input for every
> other sentiment signal below.

**`overall: float`** — Mean of `by_turn` across the entire call, representing the
call's net emotional tone.

> *Why it matters:* The single number that goes on a dashboard or SLA report. Operations
> can track average call sentiment by agent, by campaign, or by product line and set alert
> thresholds ("flag any call below −0.2 for manual review"). Without it, sentiment is not
> comparable across calls.

**`shift_points: list[int]`** — Indices into `Transcript.turns` where consecutive
sentiment scores differ by more than 0.4 in either direction.

> *Why it matters:* Identifies inflection moments — where the conversation took a sharp
> turn for better or worse. A sudden negative shift after the agent reads a script section
> is a signal to revise that script. A positive shift after a specific offer or apology
> confirms what de-escalation technique actually works. This is the field that drives
> conversation-level root-cause analysis.

**`caller_frustration: bool`** — `True` when the caller's turns contain at least two
consecutive sentiment scores below −0.3.

> *Why it matters:* A binary flag cheap enough to evaluate in real time or in bulk. It
> feeds escalation routing ("callers flagged frustrated should be offered a supervisor"),
> churn-risk models ("frustrated callers correlate with cancellations 3× more often"),
> and agent performance metrics ("agent A triggers frustration on 12% of calls vs. 4%
> team average"). The boolean form keeps it actionable without requiring the consumer to
> implement their own threshold logic.

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.sentiment` is populated.
- `report.sentiment.by_turn` has the same length as `report.transcript.turns`.
- `report.sentiment.overall` equals the mean of `by_turn` (within floating-point tolerance).
- `report.sentiment.shift_points` contains indices where |score[i] − score[i−1]| > 0.4.
- `report.sentiment.caller_frustration` is `True` when caller turns have ≥ 2 consecutive
  scores below −0.3.
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
