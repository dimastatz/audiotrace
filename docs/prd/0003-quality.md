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

## Acceptance criteria

- `analyze("call.wav")` returns a `CallReport` where `report.quality` is populated.
- `report.quality.silence_gaps` correctly identifies pauses > 2s.
- `report.quality.interruptions` accurately counts speech overlaps.
- `report.quality.speaking_pace_wpm` is accurate within 10%.
- `./scripts/test_local.sh test` passes with full coverage for the new logic.
