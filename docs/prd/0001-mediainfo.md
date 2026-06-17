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

## Data contract

`src/audiotrace/models.py::MediaInfo`

```python
class MediaInfo(BaseModel):
    duration_ms: int
    sample_rate_hz: int
    channels: int
    codec: str
    file_size_bytes: int
    file_format: str
    bitrate_kbps: float
```

### Field definitions and business impact

**`duration_ms: int`** — Total call length in milliseconds.

> *Why it matters:* The most basic operational metric. Average handle time (AHT) is a core
> contact-center KPI, and duration is its raw input. Long calls may signal agent confusion
> or complex issues; very short calls may indicate abandonment or misrouting. Duration also
> gates cost estimation for per-minute billing (telephony, STT, TTS).

**`sample_rate_hz: int`** — Audio sampling rate (e.g., 8000 Hz for telephone, 16000 Hz
for VoIP, 44100 Hz for wideband).

> *Why it matters:* Determines which downstream models can run. Whisper and most STT
> engines require 16 kHz; telephony recordings are often 8 kHz. Knowing the sample rate
> upfront lets the pipeline resample once rather than silently degrade accuracy. It also
> signals audio quality — 8 kHz recordings have narrowband frequency content that affects
> pitch and sentiment analysis fidelity.

**`channels: int`** — Number of audio channels (1 = mono, 2 = stereo).

> *Why it matters:* Stereo recordings often carry agent and caller on separate channels,
> making diarization trivial and near-perfect. Mono recordings require model-based speaker
> separation. Surfacing this field lets the pipeline choose the right diarization strategy
> and allows operators to audit their recording infrastructure.

**`codec: str`** — Audio codec used to encode the file (e.g., `pcm_s16le`, `opus`, `mp3`).

> *Why it matters:* Lossy codecs (MP3, Opus at low bitrates) introduce artifacts that
> degrade STT accuracy and pitch analysis. Knowing the codec lets the pipeline warn when
> quality is compromised and helps ops teams set minimum recording standards for their
> infrastructure.

**`file_size_bytes: int`** — Raw file size on disk in bytes.

> *Why it matters:* Drives storage cost forecasting and ingestion pipeline capacity
> planning. A team processing 10k calls/day needs to know average file size to size
> object storage and network bandwidth. It also sanity-checks recordings — a 30-minute
> call in 10 KB is a silent or corrupt file.

**`file_format: str`** — Container format (e.g., `wav`, `mp4`, `ogg`).

> *Why it matters:* Different telephony providers and recording systems produce different
> formats. Knowing the format ahead of time lets the pipeline skip unnecessary probing and
> handle format-specific edge cases (e.g., WAV with non-standard headers).

**`bitrate_kbps: float`** — Audio bitrate in kilobits per second.

> *Why it matters:* Together with codec, bitrate is the best single indicator of audio
> quality. Low-bitrate Opus (< 16 kbps) or MP3 (< 64 kbps) will measurably hurt STT
> word-error-rate. Teams can use this field to filter out low-quality recordings before
> running expensive models, or to flag them for re-recording policies.

## Acceptance criteria (Milestone 1)

- `analyze("call.wav")` returns a `CallReport` where `report.media` is fully populated.
- `report.media.duration_ms` is accurate within 100ms.
- FFmpeg/ffprobe dependency is verified and handled gracefully.
- `./scripts/test_local.sh test` passes (covers formatting, linting, and coverage).
