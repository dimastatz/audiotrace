# CallReport reference

`audiotrace.analyze()` returns a `CallReport` (Pydantic). It is the library's
stable contract: fields are only added, never renamed, without a major
version. Times are milliseconds from the start of the recording.

## CallReport

| Field | Type | Meaning |
|---|---|---|
| `media` | `MediaInfo \| None` | File facts from ffprobe |
| `transcript` | `Transcript` | Words and turns with speakers |
| `quality` | `Quality` | Audio and conversation quality signals |
| `sentiment` | `Sentiment` | Per-turn sentiment and frustration |
| `latency` | `Latency` | Response latency waterfall and processing times |
| `cost` | `Cost` | Estimated cost from list prices |
| `events` | `Events` | Outcome, drop-off, intent, compliance |
| `provenance` | `Provenance \| None` | The extraction stack that produced the report (`None` in old reports) |
| `simulation` | `SimulationResult \| None` | Set only for calls placed by `audiotrace simulate` |

## MediaInfo

| Field | Type | Meaning |
|---|---|---|
| `duration_ms` | `int` | Recording length |
| `sample_rate_hz` | `int` | Sample rate |
| `channels` | `int` | Channel count |
| `codec` | `str` | Audio codec, e.g. `opus`, `mp3` |
| `file_size_bytes` | `int` | File size |
| `file_format` | `str` | Container format |
| `bitrate_kbps` | `float` | Bit rate |

## Transcript

| Field | Type | Meaning |
|---|---|---|
| `full_text` | `str` | Whole transcript |
| `turns` | `list[Turn]` | Speaker turns in order |
| `language` | `str` | Detected language code |
| `diarization_confidence` | `float \| None` | Pitch fallback only: how separable the voices were (0–1); `None` otherwise |

### Turn

| Field | Type | Meaning |
|---|---|---|
| `speaker` | `str` | Label, e.g. `AI Agent`, `Customer`, or your `speaker_labels` |
| `text` | `str` | What was said |
| `start_ms` / `end_ms` | `int` | Time range |
| `confidence` | `float` | Recognition confidence (0–1) |
| `words` | `list[Word]` | Word timings (`text`, `start_ms`, `end_ms`) |

### Word

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | The word |
| `start_ms` / `end_ms` | `int` | Time range |

## Quality

| Field | Type | Meaning |
|---|---|---|
| `overall_score` | `float` | Heuristic 0–1: starts at 1, minus silence share (≤0.4), interruptions (0.05 each, ≤0.3), pace outside the ideal range (≤0.2), flat pitch (0.1) |
| `interruptions` | `int` | Turns starting before the other speaker finished (rare on mono audio: recognition segments seldom overlap) |
| `silence_gaps` | `list[Gap]` | Long stretches of silence (`start_ms`, `end_ms`) |
| `speaking_pace_wpm` | `float` | Words per minute over the call |
| `pitch_variance` | `float` | Standard deviation of voiced pitch (Hz) |
| `turn_length_avg_ms` | `float` | Average turn length |

### Gap

| Field | Type | Meaning |
|---|---|---|
| `start_ms` / `end_ms` | `int` | Time range of the silence |

## Sentiment

| Field | Type | Meaning |
|---|---|---|
| `by_turn` | `list[float]` | Per-turn score, −1 (negative) to +1 (positive) |
| `overall` | `float` | Mean of `by_turn` |
| `shift_points` | `list[int]` | Turn indices where the score jumps by more than 0.4 |
| `caller_frustration` | `bool` | Two consecutive caller turns below −0.3 |

## Latency

| Field | Type | Meaning |
|---|---|---|
| `waterfall` | `list[LatencySpan]` | One `agent_response` span per caller→agent hand-off longer than 250 ms: the silence before the agent replied |
| `stt_ms` | `int` | Time AudioTrace spent transcribing (processing time, not call latency) |
| `total_ms` | `int` | Time AudioTrace spent on the whole analysis |
| `llm_first_token_ms` / `llm_full_response_ms` / `tts_ms` | `int` | Reserved for provider-reported stage timings; `0` today (not measurable from a recording) |

### LatencySpan

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Span kind, e.g. `agent_response` |
| `start_ms` | `int` | When the span starts |
| `duration_ms` | `int` | How long it lasted |

## Cost

All in USD, estimated from list prices (see [Pricing](../guides/pricing-and-speakers.md)).

| Field | Type | Meaning |
|---|---|---|
| `stt_usd` | `float` | From call duration |
| `llm_usd` | `float` | From caller (input) and agent (output) characters |
| `tts_usd` | `float` | From agent characters |
| `telephony_usd` | `float` | From call duration |
| `total_usd` | `float` | Sum |

## Events

| Field | Type | Meaning |
|---|---|---|
| `outcome` | `str` | `completed`, `dropped`, or `failed` (no speech) |
| `drop_off` | `bool` | Long trailing silence, or the caller spoke last |
| `drop_off_turn` | `int \| None` | Turn index where it dropped |
| `intent_detected` | `str` | Zero-shot label from the caller's words (billing, technical support, sales, cancellation, general inquiry) |
| `failure_type` | `str \| None` | e.g. `no_speech` |
| `compliance_flags` | `list[str]` | Summary: `missing_consent`, `pii_exposed` |
| `compliance_findings` | `list[ComplianceFinding]` | The located findings behind the flags |

### ComplianceFinding

| Field | Type | Meaning |
|---|---|---|
| `type` | `str` | `missing_consent` or `pii` |
| `pii_type` | `str \| None` | `ssn`, `card`, `email`, `phone`, `dob`, `address`, `account`, `ni_number`, `postcode`, `iban` |
| `detail` | `str` | Masked value (last two characters), or the rule that failed |
| `speaker` | `str` | Who said it |
| `role` | `str` | `agent`, `caller`, or `""` if the label has no known role |
| `turn_index` | `int \| None` | Turn it was found in |
| `start_ms` / `end_ms` | `int` | Time range |

## Provenance

The extraction stack, so metric moves can be told apart from measurement
changes. Empty strings mean a version couldn't be determined.

| Field | Type | Meaning |
|---|---|---|
| `audiotrace_version` | `str` | AudioTrace version |
| `whisper_model` | `str` | Whisper model size, e.g. `base` |
| `diarization` | `str` | pyannote pipeline id, `pitch` (fallback), or `none` |
| `sentiment_model` | `str` | Sentiment model id |
| `intent_model` | `str` | Intent model id |
| `python_version` | `str` | Python version |
| `whisper_version` | `str` | openai-whisper package version |
| `pyannote_version` | `str` | pyannote.audio version |
| `librosa_version` | `str` | Librosa version |
| `transformers_version` | `str` | Transformers version |
| `torch_version` | `str` | PyTorch version |

## SimulationResult

| Field | Type | Meaning |
|---|---|---|
| `scenario` | `str` | Scenario name |
| `persona` | `str` | Persona used |
| `noise` | `str` | Noise profile used |
| `task_completed` | `bool` | The verdict |
| `reason` | `str` | Failed criteria, or that all held |
| `turns` | `int` | Caller turns spoken |
