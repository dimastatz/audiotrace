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

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.transcript` is
  fully populated.
- `report.transcript.turns` correctly identifies "agent" vs "caller" (or
  "SPEAKER_00" etc if roles are unknown).
- `start_ms` and `end_ms` for each turn are accurate within 200ms compared to
  manual ground truth.
- `language` correctly identifies the primary spoken language (e.g., "en", "es").
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
