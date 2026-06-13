# PRD 0001 — Core `analyze()` pipeline

**Status:** In Progress
**Owner:** Dima Statz
**Related:** [roadmap Phase 0/1](../roadmap.md)

## Summary

Implement `audiotrace.analyze(audio, metadata)` to extract structured data from
audio recordings. Delivery is phased: **Milestone 1 focuses exclusively on
`MediaInfo` extraction** (duration, codec, bitrate) to establish the base
pipeline before adding heavy extractors (Whisper, Librosa).

## Goals

### Milestone 1 (Current)
- Establish the `analyze()` entry point and FFmpeg-based preprocessing.
- **Extract and return `MediaInfo` only**: duration, sample rate, channels, codec, file size, format, and bitrate.
- Ensure `CallReport` validates with only the `media` field populated (others use defaults).

### Milestone 2
- Integrate heavy extractors for the remaining `CallReport` sections:
  transcript, quality, sentiment, latency, cost, events.
- Full extraction using Whisper, Librosa, and Transformers.

## Non-goals

- Concurrency / batching — covered by `batch()` (later PRD).
- Provider-specific fetching — covered by adapter PRDs.
- Live/streaming analysis — file-based only for now.

## Proposed pipeline (Milestone 1)

```
audio file → FFmpeg (ffprobe) → parse MediaInfo → CallReport
```

## Proposed pipeline (Full)

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

## Acceptance criteria (Milestone 1)

- `analyze("call.wav")` returns a `CallReport` where `report.media` is fully populated.
- `report.media.duration_ms` is accurate within 100ms.
- FFmpeg/ffprobe dependency is verified and handled gracefully.
- `./scripts/test_local.sh test` passes (covers formatting, linting, and coverage).
