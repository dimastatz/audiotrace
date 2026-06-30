<div align="center">
<h1 align="center"> AudioTrace </h1> 
<h3>CI/CD for voice AI</br></h3>
<img src="https://img.shields.io/badge/Progress-10%25-red"> <img src="https://img.shields.io/badge/Feedback-Welcome-green">
</br>
</br>
<img src="https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/imgs/auditrace.png" width="256px" alt="AudioTrace logo"> 
</div>

## What is AudioTrace?

Voice Agents AI plumbing tool every team rebuilds from scratch — until now.
Drop in a call recording. Get back everything: transcript, quality scores, sentiment shifts, latency breakdown, cost attribution, compliance flags. Normalized. Structured. Queryable. Works with any provider, any stack.
One integration. Zero plumbing. Ship faster.

```python
import audiotrace

report = audiotrace.analyze(
    audio    = "call_recording.wav",
    metadata = {"agent_version": "v2.1", "provider": "vapi"}
)

print(report.quality.overall_score)        # 0.87
print(report.sentiment.caller_frustration) # False
print(report.latency.llm_first_token_ms)   # 420
print(report.events.drop_off)              # False
print(report.cost.total_usd)               # 0.063
```

📺 **Watch the demo:**

[![AudioTrace demo video](https://img.youtube.com/vi/sBWPomlYpv4/maxresdefault.jpg)](https://youtu.be/sBWPomlYpv4)

---

## Why AudioTrace?

Every team building voice agents faces the same problem: raw audio is a black box. You can listen to recordings manually, or you can build your own signal extraction pipeline from scratch — but no open-source framework normalizes the full call into a structured, queryable object.

AudioTrace exists to be that shared layer. It handles the hard parts so you can focus on what you're building:

- Transcription with speaker diarization
- Silence gaps, interruptions, speaking pace, and pitch analysis
- Per-turn sentiment tracking and frustration detection
- Per-stage latency breakdown (STT → LLM → TTS → telephony)
- Unified cost calculation across any provider mix
- Compliance flag detection (PII leakage, consent gaps)

<img src="https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/imgs/dashboard.png" alt="AudioTrace dashboard"> 

---

## Installation

```bash
pip install audiotrace

# With specific provider adapter
pip install audiotrace[vapi]
pip install audiotrace[retell]
pip install audiotrace[twilio]

# Full install
pip install audiotrace[all]
```

### Docker
```bash
docker build -f docker/Dockerfile -t audiotrace .
docker run -it audiotrace
```

**Requirements:** Python 3.9+, FFmpeg installed on system

---

# Quick start

### Analyze a single call

```python
import audiotrace

report = audiotrace.analyze(
    audio    = "call.wav",
    metadata = {
        "call_id":       "abc123",
        "agent_version": "v2.1",
        "provider":      "vapi",
        "campaign":      "healthcare_intake"
    }
)

# Media
print(report.media.duration_ms)          # int
print(report.media.codec)                # str

# Transcript
print(report.transcript.full_text)
for turn in report.transcript.turns:
    print(f"{turn.speaker}: {turn.text}")

# Quality
print(report.quality.overall_score)       # float 0.0–1.0
print(report.quality.interruptions)       # int
print(report.quality.silence_gaps)        # List[Gap]
print(report.quality.speaking_pace_wpm)   # float

# Sentiment
print(report.sentiment.overall)           # float -1.0 to 1.0
print(report.sentiment.shift_points)      # List[int] — turn indices
print(report.sentiment.caller_frustration)# bool

# Latency
print(report.latency.stt_ms)             # int
print(report.latency.llm_first_token_ms) # int
print(report.latency.tts_ms)             # int
print(report.latency.total_ms)           # int

# Cost
print(report.cost.stt_usd)               # float
print(report.cost.llm_usd)               # float
print(report.cost.total_usd)             # float

# Events
print(report.events.outcome)             # "completed" | "dropped" | "failed"
print(report.events.drop_off_turn)       # int | None
print(report.events.compliance_flags)    # List[str]
```

### Use provider adapters

```python
from audiotrace.adapters import VapiAdapter

adapter = VapiAdapter(api_key="...")
call    = adapter.fetch_call(call_id="abc123")
report  = audiotrace.analyze(call.audio, call.metadata)
```

---

## Output — CallReport

```
CallReport
├── media
│   ├── duration_ms: int
│   ├── sample_rate_hz: int
│   ├── channels: int
│   ├── codec: str
│   ├── file_size_bytes: int
│   ├── file_format: str
│   └── bitrate_kbps: float
├── transcript
│   ├── full_text: str
│   ├── turns: List[Turn]   # speaker · text · start_ms · end_ms · confidence · words[]
│   └── language: str
├── quality
│   ├── overall_score: float
│   ├── interruptions: int
│   ├── silence_gaps: List[Gap]
│   ├── speaking_pace_wpm: float
│   ├── pitch_variance: float
│   └── turn_length_avg_ms: float
├── sentiment
│   ├── by_turn: List[float]
│   ├── overall: float
│   ├── shift_points: List[int]
│   └── caller_frustration: bool
├── latency
│   ├── stt_ms: int
│   ├── llm_first_token_ms: int
│   ├── llm_full_response_ms: int
│   ├── tts_ms: int
│   ├── total_ms: int
│   └── waterfall: List[LatencySpan]
├── cost
│   ├── stt_usd: float
│   ├── llm_usd: float
│   ├── tts_usd: float
│   ├── telephony_usd: float
│   └── total_usd: float
└── events
    ├── outcome: str
    ├── drop_off: bool
    ├── drop_off_turn: int | None
    ├── intent_detected: str
    ├── failure_type: str | None
    └── compliance_flags: List[str]
```

---

## Provider support

> **Provider adapters are TBD** — not yet implemented. The integrations below are
> planned; today you pass a local audio file path to `analyze()` directly. The
> adapter example above is illustrative of the intended API.

| Provider | Adapter | Status |
|---|---|---|
| Vapi | `audiotrace[vapi]` | TBD |
| Retell | `audiotrace[retell]` | TBD |
| Twilio | `audiotrace[twilio]` | TBD |
| ElevenLabs | `audiotrace[elevenlabs]` | TBD |
| Deepgram | `audiotrace[deepgram]` | TBD |
| Custom webhook | `CustomAdapter` | TBD |

---

## How it works

AudioTrace builds on top of best-in-class audio libraries so you don't have to:

```
Raw audio file
      │
      ▼
  FFmpeg              — format normalization, turn splitting
      │
      ├── Whisper     — transcription
      ├── pyannote    — speaker diarization
      ├── Librosa     — silence gaps, pace, pitch, energy
      └── Transformers — sentiment, intent detection
      │
      ▼
  CallReport (Pydantic)
```

---

## Part of the Lang ecosystem [TBD]()

AudioTrace is the open-source foundation that powers two commercial products:

| Product | What it does | Built on |
|---|---|---|
| **[LangTrace](https://langtrace.io)** | Live call observability & analytics dashboards | AudioTrace |
| **[LangGate](https://langgate.io)** | Pre-deploy simulation & CI/CD quality gate | AudioTrace |

AudioTrace is free and MIT-licensed. The commercial products are optional hosted layers on top.

---

## Running locally

For quick testing or interactive analysis, you can use the provided runner script. It automatically handles virtual environment setup and dependency validation.

```bash
# Analyze default golden data fixture
./scripts/run.sh

# Concise per-section summary tables instead of the raw JSON
./scripts/run.sh --summary

# Playback, inferring speakers by pitch (no pyannote token needed)
./scripts/run.sh --playback --skip-pyannote

# Analyze a specific file
./scripts/run.sh path/to/your/audio.wav
```

### Development & Validation
Before submitting changes, ensure everything passes the local validation suite (formatting, linting, type-checking, and tests):

```bash
./scripts/test_local.sh test
```

---

## Regression gating in CI

Treat a handful of representative recordings as golden fixtures, commit a **baseline**, and fail the build when a prompt/model/voice change makes the agent measurably worse — slower, colder, less compliant.

```bash
# 1. Commit a baseline from your golden calls (one time, and after intentional changes)
audiotrace baseline tests/calls -o baseline.json

# 2. Gate every change against it — exits non-zero on regression, writes per-call reports
audiotrace check tests/calls -b baseline.json --report audiotrace-report
```

A metric only fails the build when it drifts past its tolerance (quality −0.05, sentiment −0.10, latency +15%, cost +20%; frustration / drop-off / compliance have zero slack). New recordings not in the baseline are skipped, not failed.

### GitHub Action

Drop the gate into CI in a few lines. It installs AudioTrace, runs the check, and uploads the HTML report as an artifact even when the build fails:

```yaml
# .github/workflows/voice-quality.yml
name: Voice quality
on: [pull_request]
jobs:
  audiotrace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dimastatz/audiotrace@v1
        with:
          calls: tests/calls
          baseline: baseline.json
```

---

## Contributing

Contributions are welcome — especially new provider adapters, persona definitions for simulation, and compliance rule sets.

```bash
git clone https://github.com/audiotrace/audiotrace
cd audiotrace
./scripts/test_local.sh test  # Run all checks (formatting, lint, types, tests)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT — see [LICENSE](LICENSE)