# PRD 0002 — Transcript and Diarization pipeline

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 1](../roadmap.md)

## Summary

Implement the transcription and speaker diarization layer of the `analyze()`
pipeline. This stage turns raw audio into a structured `Transcript` object
containing the full text, individual speaker turns with timestamps, and detected
language.

## Goals

- **Integrate OpenAI Whisper**: Use `openai-whisper` to perform speech-to-text
  extraction.
- **Integrate pyannote.audio**: Use `pyannote.audio` to identify different
  speakers and their turn boundaries.
- **Populate `Transcript` model**: Fill in `full_text`, `language`, and the list
  of `turns` (speaker, text, start_ms, end_ms).
- **Temporal Alignment**: Ensure transcription segments are accurately mapped to
  diarization turns.

## Non-goals

- Quality signals (silence, pace, pitch) — covered by a separate PRD.
- Sentiment analysis or intent detection — covered by a separate PRD.
- Real-time/streaming transcription.

## Proposed pipeline

```
audio file → FFmpeg normalize (16kHz) → Whisper (STT + timestamps)
                                      → pyannote.audio (diarization)
                                      → Segment Alignment Logic
                                      → Transcript (CallReport)
```

## Open questions

- **Model size selection**: Should the Whisper model size be configurable by the
  user (e.g., `base` vs `large-v3`)?
- **Diarization accuracy**: How do we handle calls where speakers have similar
  voice profiles?
- **Resource usage**: Whisper and pyannote are heavy; how do we handle
  concurrency limits in the library?

## Data contract

`src/audiotrace/models.py::Transcript` and `Turn`

```python
class Turn(BaseModel):
    speaker: str
    text: str
    start_ms: int
    end_ms: int

class Transcript(BaseModel):
    full_text: str = ""
    turns: list[Turn] = Field(default_factory=list)
    language: str = "en"
```

### Field definitions and business impact

**`full_text: str`** — The complete call transcript as a single concatenated string.

> *Why it matters:* The starting point for any text-based analysis — keyword search,
> topic classification, compliance scanning, and LLM summarization all consume this field.
> It is also the most human-readable artifact of a call: QA reviewers and managers open
> it first. Without it, every downstream consumer must reconstruct the text from turns,
> introducing inconsistency.

**`turns: list[Turn]`** — Ordered list of speaker turns, each with speaker identity,
spoken text, and millisecond timestamps.

> *Why it matters:* Turns are the unit of conversational analysis. Every higher-level
> signal — sentiment per turn, interruption count, speaking pace, turn-length average —
> is computed over this list. Without turns, the pipeline degrades to document-level
> analysis and loses the ability to attribute behavior to a specific speaker or moment
> in the call.

**`turns[].speaker: str`** — Speaker label for the turn (e.g., `"agent"`, `"caller"`,
or `"SPEAKER_00"` when roles are unknown).

> *Why it matters:* Makes metrics attributable. "The caller was frustrated" is actionable;
> "someone was frustrated" is not. Agent-vs-caller split enables separate coaching signals
> (agent pace, agent interruptions) from customer experience signals (caller sentiment,
> caller frustration). Role labels also feed compliance checks — only the agent should
> read the disclosure script.

**`turns[].text: str`** — Transcribed text spoken during this turn.

> *Why it matters:* The raw material for sentiment scoring, keyword flagging, intent
> detection, and compliance review. Accurate per-turn text (rather than full-call text)
> lets models focus on a short, coherent utterance rather than a multi-minute monologue,
> improving accuracy and reducing token cost when using LLMs downstream.

**`turns[].start_ms: int`** and **`turns[].end_ms: int`** — Turn boundaries in
milliseconds from the start of the recording.

> *Why it matters:* Timestamps make the transcript seekable. A QA reviewer can click a
> flagged turn and jump directly to that moment in the audio player. They also enable
> latency measurement (gap between agent turn end and caller turn start = response lag),
> interruption detection (overlapping start/end ranges), and silence gap identification.
> Without timestamps, the transcript is a static document with no link to the audio.

**`language: str`** — BCP-47 language code detected from the audio (e.g., `"en"`, `"es"`).

> *Why it matters:* Routes calls to the correct downstream models and human reviewers.
> A Spanish call sent to an English-only QA team wastes review capacity. Language also
> unlocks compliance requirements — disclosures must be delivered in the caller's language
> in many jurisdictions. Detecting it automatically removes a manual tagging step and
> enables language-breakdown reporting across a call center.

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.transcript` is
  fully populated.
- `report.transcript.turns` correctly identifies "agent" vs "caller" (or
  "SPEAKER_00" etc if roles are unknown).
- `start_ms` and `end_ms` for each turn are accurate within 200ms compared to
  manual ground truth.
- `language` correctly identifies the primary spoken language (e.g., "en", "es").
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
