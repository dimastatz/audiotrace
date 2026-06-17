# PRD 0003 — Quality extraction pipeline

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 1](../roadmap.md)

## Summary

Implement the quality extraction layer of the `analyze()` pipeline. This stage extracts physical characteristics of the audio and conversational flow signals, including silence gaps, interruptions, speaking pace (WPM), and pitch variance.

## Goals

- **Integrate Librosa**: Use `librosa` for low-level audio analysis (silence detection, RMS energy, pitch).
- **Detect Silence Gaps**: Identify stretches of silence longer than a threshold (e.g., 2000ms).
- **Detect Interruptions**: Identify overlapping speech segments using diarization data.
- **Calculate Speaking Pace**: Calculate words-per-minute (WPM) using transcript and audio duration.
- **Calculate Pitch Variance**: Measure the modulation of the agent/caller voice.
- **Calculate Turn Length**: Provide average turn duration.
- **Score Overall Quality**: Implement a heuristic score (0.0–1.0) based on the above signals.

## Non-goals

- Transcription/Diarization — covered by [PRD 0002](./0002-transcript.md).
- Sentiment analysis — covered by a future PRD.

## Proposed pipeline

```
audio file + transcript → Librosa (RMS energy) → Silence detection
                         → Diarization turns → Interruption detection
                         → Full text + duration → Speaking pace (WPM)
                         → Librosa (YIN/PYIN) → Pitch variance
                         → Quality (CallReport)
```

## Data contract

`src/audiotrace/models.py::Quality` and `Gap`

```python
class Gap(BaseModel):
    start_ms: int
    end_ms: int

class Quality(BaseModel):
    overall_score: float = 0.0
    interruptions: int = 0
    silence_gaps: list[Gap] = Field(default_factory=list)
    speaking_pace_wpm: float = 0.0
    pitch_variance: float = 0.0
    turn_length_avg_ms: float = 0.0
```

### Field definitions and business impact

**`overall_score: float`** — Heuristic quality score from 0.0 (poor) to 1.0 (excellent),
aggregating all signals below into a single number.

> *Why it matters:* The field that appears on dashboards and in SLA reports. Ops teams
> set alert thresholds ("flag calls below 0.6 for review") and track trends over time
> without needing to understand the underlying signals. It also enables ranking: "show me
> the 10 worst calls this week" is a single sort on this field.

**`interruptions: int`** — Count of times one speaker began talking while the other was
still speaking.

> *Why it matters:* High interruption counts are a leading indicator of a poor caller
> experience. Agents interrupting callers signals impatience or poor listening; callers
> interrupting agents may indicate frustration or that the agent is speaking too slowly.
> Coaching teams use this metric to identify agents who need active-listening training.
> It also correlates with call outcomes — high-interruption calls have lower resolution
> rates in most contact centers.

**`silence_gaps: list[Gap]`** — List of silence stretches exceeding the threshold
(default 2000 ms), each with `start_ms` and `end_ms`.

> *Why it matters:* Long silences are a direct proxy for on-hold time, agent confusion,
> or system lag. A 10-second gap after the agent asks a question may mean they are
> searching a knowledge base — a training or tooling gap. Surfacing exact timestamps
> lets ops teams audit specific moments rather than guessing where delays occurred.
> Silence gaps also feed the latency waterfall when provider metadata is unavailable.

**`silence_gaps[].start_ms`** and **`silence_gaps[].end_ms`** — Millisecond offsets
marking the boundaries of each silence stretch.

> *Why it matters:* Timestamps make gaps actionable — a reviewer can seek directly to
> the silence in the audio player and hear the context around it. Without boundaries,
> knowing "there were 3 silences" gives no way to investigate or coach on them.

**`speaking_pace_wpm: float`** — Average words per minute across the full call.

> *Why it matters:* Pace is one of the most trainable call-quality levers. Agents
> speaking above ~180 WPM are often perceived as rushed or hard to understand, especially
> by older callers or non-native speakers. Agents below ~120 WPM may frustrate callers
> and inflate handle time. WPM benchmarks also vary by use case — sales calls tolerate
> faster pace than healthcare or financial services calls.

**`pitch_variance: float`** — Standard deviation of the fundamental frequency (F0)
across the agent's speech, in Hz.

> *Why it matters:* Pitch variance is a proxy for vocal engagement. A flat, monotone
> delivery (low variance) is associated with disengagement and lower caller satisfaction
> scores. High variance indicates an expressive, natural-sounding agent. This signal is
> particularly useful for evaluating AI voice agents, where monotone synthesis is a common
> quality problem that is otherwise invisible in text-based metrics.

**`turn_length_avg_ms: float`** — Mean duration of all speaker turns in milliseconds.

> *Why it matters:* Diagnostic for conversational balance. Very long average agent turns
> indicate monologue-style delivery where the agent is not pausing to check understanding.
> Very short turns may indicate rapid back-and-forth or a confused, fragmented conversation.
> Comparing agent vs. caller average turn lengths separately (a future field split) reveals
> who is dominating the conversation.

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.quality` is populated.
- `report.quality.silence_gaps` correctly identifies pauses > 2s.
- `report.quality.interruptions` accurately counts speech overlaps.
- `report.quality.speaking_pace_wpm` is accurate within 10%.
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
