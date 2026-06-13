# PRD 0001 — Core `analyze()` pipeline

**Status:** In Progress
**Owner:** Dima Statz
**Related:** [roadmap Phase 0/1](../roadmap.md)

## Summary

Implement `audiotrace.analyze(audio, metadata)` so it turns a single audio file
into a fully populated `CallReport`. This is the foundation every other feature
(batch, adapters, dashboards) builds on.

## Goals

- Accept an audio file path (any format FFmpeg can read) plus optional metadata.
- Normalize audio with FFmpeg, then extract every section of `CallReport`:
  transcript, quality, sentiment, latency, cost, events.
- Return a validated `CallReport` (the contract already defined in
  `src/audiotrace/models.py`).

## Non-goals

- Concurrency / batching — covered by `batch()` (later PRD).
- Provider-specific fetching — covered by adapter PRDs.
- Live/streaming analysis — file-based only for now.

## Proposed pipeline

```
audio file → FFmpeg normalize → Whisper (transcript)
                              → pyannote (diarization → turns)
                              → Librosa (gaps, pace, pitch → quality)
                              → Transformers (sentiment, intent)
                              → cost model (from metadata + durations)
                              → CallReport
```

## Open questions

- Which Whisper implementation (faster-whisper vs openai-whisper)?
answer: openai-whisper
- Are latency fields derivable from audio alone, or do they require
  provider-supplied timing metadata?
answer: for audio file alone
- How is cost computed when provider/pricing metadata is absent?
answer: show N/A in a meantime

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` with a non-empty transcript.
- All `CallReport` sections populate for a representative sample call.
- Unit tests cover each extractor with fixture audio.
- `pytest`, `ruff check .`, and `mypy src/audiotrace` all pass.
