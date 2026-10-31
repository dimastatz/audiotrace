<div align="center">
<h1 align="center"> AudioTrace </h1> 
<h3>CI/CD for voice AI</br></h3>
<img src="https://img.shields.io/badge/Progress-10%25-red"> <img src="https://img.shields.io/badge/Feedback-Welcome-green">
</br>
</br>
<img src="https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/imgs/auditrace.png" width="256px" alt="AudioTrace logo"> 
</div>

📖 **Docs:** https://dimastatz.github.io/audiotrace/ — getting started, guides, the full `CallReport` reference, and [what's shipped](https://dimastatz.github.io/audiotrace/status/).

## What is AudioTrace?

Voice Agents AI plumbing tool every team rebuilds from scratch — until now.
Drop in a call recording. Get back everything: transcript, quality scores, sentiment shifts, agent response latency, estimated cost, compliance findings. Normalized. Structured. Queryable. Works with any provider, any stack.
One integration. Zero plumbing. Ship faster.

```python
import audiotrace

report = audiotrace.analyze("call_recording.wav", num_speakers=2)

print(report.quality.overall_score)                          # 0.87
print(report.sentiment.caller_frustration)                   # False
print([s.duration_ms for s in report.latency.waterfall])     # agent response gaps: [640, 1210, ...]
print(report.events.drop_off)                                # False
print(report.cost.total_usd)                                 # 0.063 (estimated from list prices)
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
- Agent response latency for every caller → agent hand-off
- Cost estimates from your own provider rates
- Compliance findings (PII said on the call, missing recording disclosure), located and masked
- A regression gate for CI, simulated callers, and production replay

<img src="https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/imgs/dashboard.png" alt="AudioTrace dashboard"> 

---

## Installation

```bash
pip install audiotrace

# Simulated callers (Claude + local Kokoro TTS; Python 3.10–3.12)
pip install audiotrace[simulate]

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

report = audiotrace.analyze("call.wav", num_speakers=2)   # labels speakers "AI Agent" / "Customer"

for turn in report.transcript.turns:
    print(f"{turn.speaker}: {turn.text}")

print(report.quality.overall_score, report.sentiment.overall, report.events.outcome)
audiotrace.write_report(report, "out/")   # out/report.json + a self-contained out/report.html
```

Every field, with units and how it's computed, is in the [CallReport reference](https://dimastatz.github.io/audiotrace/reference/callreport/). Runnable scripts live in [`examples/`](examples/).

### Use provider adapters

```python
from audiotrace.adapters import VapiAdapter  # also RetellAdapter, TwilioAdapter

adapter = VapiAdapter()  # api_key=..., or VAPI_API_KEY from the environment
call = adapter.fetch_call("abc123")  # downloads the recording once, then reuses it
report = audiotrace.analyze(call.audio, call.metadata)

call.metadata  # call_id, provider, agent_id, agent_version, started_at, ended_reason, provider_cost_usd
for call_id in adapter.list_calls(limit=20):  # newest calls
    ...
```

Recordings are cached under `~/.cache/audiotrace/recordings/<provider>/` (or `$AUDIOTRACE_CACHE`) until you delete them. The CLI can gate provider calls directly: `audiotrace check --provider retell --since 2026-10-01 -b baseline.json`.

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
│   ├── language: str
│   └── diarization_confidence: float | None   # pitch-fallback speaker separability (0-1); None if not measured
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
│   ├── stt_ms: int                  # AudioTrace's own transcription time
│   ├── llm_first_token_ms: int      # reserved: 0 (not measurable from audio)
│   ├── llm_full_response_ms: int    # reserved: 0
│   ├── tts_ms: int                  # reserved: 0
│   ├── total_ms: int                # AudioTrace's own analysis time
│   └── waterfall: List[LatencySpan] # agent_response gaps, one per caller → agent hand-off
├── cost
│   ├── stt_usd: float
│   ├── llm_usd: float
│   ├── tts_usd: float
│   ├── telephony_usd: float
│   └── total_usd: float
├── events
│   ├── outcome: str
│   ├── drop_off: bool
│   ├── drop_off_turn: int | None
│   ├── intent_detected: str
│   ├── failure_type: str | None
│   ├── compliance_flags: List[str]      # "missing_consent", "pii_exposed"
│   └── compliance_findings: List[ComplianceFinding]
│       ├── type: str                    # "missing_consent" | "pii"
│       ├── pii_type: str | None         # ssn, card, email, phone, dob, address, account, ...
│       ├── detail: str                  # masked value (last 2 chars) or the rule that failed
│       ├── speaker: str / role: str     # who said it; role "agent" | "caller" | ""
│       ├── turn_index: int | None
│       └── start_ms / end_ms: int
├── provenance: Provenance | None   # extraction stack that produced this report; None if unrecorded
│   ├── audiotrace_version: str
│   ├── whisper_model: str
│   ├── diarization: str             # pyannote pipeline id, "pitch" fallback, or "none"
│   ├── sentiment_model: str
│   ├── intent_model: str
│   ├── python_version: str
│   ├── whisper_version: str
│   ├── pyannote_version: str
│   ├── librosa_version: str
│   ├── transformers_version: str
│   └── torch_version: str
└── simulation: SimulationResult | None  # set only for calls placed by `audiotrace simulate`
    ├── scenario: str
    ├── persona: str
    ├── noise: str
    ├── task_completed: bool
    ├── reason: str                  # the failed success criteria, or that all held
    └── turns: int                   # caller turns spoken
```

---

## Provider support

Adapters use plain HTTPS from the standard library, so no extra install is needed (the extras below are kept as no-op aliases).

| Provider | Adapter | Credentials | Status |
|---|---|---|---|
| Vapi | `VapiAdapter` | `VAPI_API_KEY` | ✅ calls + recordings, cost, end reason |
| Retell | `RetellAdapter` | `RETELL_API_KEY` | ✅ calls + recordings, cost (converted from cents), agent version |
| Twilio | `TwilioAdapter` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | ✅ recordings (ids are `RE...` Recording SIDs) |
| ElevenLabs | — | — | Not planned as an adapter (usage/pricing import at most) |
| Deepgram | — | — | Not planned as an adapter (usage/pricing import at most) |
| Custom webhook | `CustomAdapter` | your own (static header) | ✅ any payload shape via a field mapping; optional `audiotrace serve` receiver |

**Custom stacks** (self-hosted LiveKit or Pipecat, your own SIP, …): map your end-of-call event with `CustomAdapter`.

```yaml
# mapping.yaml
provider: livekit
recording_headers:
  Authorization: Bearer ${RECORDINGS_TOKEN}   # read from the environment
fields:
  recording_url: $.data.recording.files[0].location   # required
  call_id: $.data.id                                  # required
  agent_version: $.data.metadata.agent_version        # optional: skipped when missing
  started_at: $.data.started_at
```

```python
from audiotrace.adapters import CustomAdapter

call = CustomAdapter.from_yaml("mapping.yaml").parse(event_json)  # from your own handler
report = audiotrace.analyze(call.audio, call.metadata)
```

Or run the bundled receiver: `AUDIOTRACE_WEBHOOK_SECRET=... audiotrace serve --mapping mapping.yaml --out reports/`. It accepts POSTs signed with `X-AudioTrace-Signature: sha256=<HMAC-SHA256 of the body>`, answers `202` immediately, and writes `<call_id>.json`/`.html` reports from a background worker. It binds to `127.0.0.1` by default; put it behind your own HTTPS proxy. It's meant for modest volume (one worker, no retries).

The adapters are tested against the providers' documented response shapes, not live accounts yet; please open an issue if a field comes back different.

---|---|---|
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

Want it run *for* you today? We're taking a few paid design-partner pilots —
"early access + we run it for you." See [COMMERCIAL.md](COMMERCIAL.md).

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

For a worked example, [`tests/fixtures/golden`](tests/fixtures/golden/README.md) has 20 synthetic calls with planted defects (missing disclosure, PII, frustrated callers, barge-ins, slow replies, dropped calls), the scenario scripts that generated them, and a committed baseline.

On top of the per-call tolerances, `audiotrace check` compares each continuous metric's *distribution* across the run (quality, sentiment, pace, response latency, cost) with the baseline using the Population Stability Index, and fails when PSI exceeds 0.25. That catches a whole run drifting a little in the same direction, which no single call would trip. It needs at least 10 calls present in both runs; smaller runs are gated per call only.

Every report records the extraction stack that produced it (`provenance`: AudioTrace, Whisper, pyannote, sentiment model, Librosa, Transformers and Torch versions). When it differs from the baseline's, `audiotrace check` prints a note listing what changed, so a metric move after an extractor upgrade reads as *measurement drift* rather than an agent regression. The note doesn't fail the build; re-baseline after an intentional stack upgrade.

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
      - uses: dimastatz/audiotrace@v1.3.0
        with:
          calls: tests/calls
          baseline: baseline.json
```

## Compliance checks

Every report checks two things, locally and with rules only:

- **Recording disclosure:** the *agent* must mention recording, monitoring or consent within the first 30 seconds. A caller asking "is this recorded?" doesn't count.
- **Exposed PII:** card numbers (Luhn-checked), SSNs, phone numbers, emails, dates of birth, street addresses and account numbers, including spoken forms such as "four one one one…" or "jo dot lee at example dot com". UK (`ni_number`, `postcode`) and EU (`iban`) presets are available.

Each finding records the speaker, their role, the turn and the time range. The matched value is masked (last two characters kept), so the report never repeats the PII it found. `compliance_flags` still carries the summary (`missing_consent`, `pii_exposed`), and the HTML report links each finding to its turn.

Rules are configurable from code (`CompliancePolicy`) or YAML (`audiotrace baseline|check --policy policy.yaml`):

```yaml
consent_window_ms: 15000        # null = anywhere in the call
consent_keywords: [record, recorded, recording, monitored, consent]
regions: [us, uk]               # us | uk | eu
disabled_pii: [address]
flag_caller_pii: false          # only flag PII the agent says
```

AudioTrace flags signals; it doesn't certify HIPAA, PCI-DSS or GDPR compliance.

---

## Production replay

Turn failing production calls into regression tests. Write rules over `CallReport` fields:

```yaml
# rules.yaml
rules:
  - name: low-quality
    when: quality.overall_score < 0.6
  - name: frustrated-caller
    when: sentiment.caller_frustration
  - name: compliance
    when: events.compliance_flags
```

```bash
pip install "audiotrace[replay]"          # only needed for S3 / GCS sources
audiotrace replay ingest --source s3://my-bucket/calls --rules rules.yaml   # or a dir, gs://, vapi, retell, twilio
audiotrace replay review                   # pending cases with occurrence counts
audiotrace replay approve <case> --reviewer dana
audiotrace check replay/suite -b replay/suite/baseline.json   # gate on the approved cases
```

Each run analyzes only calls it hasn't seen before. Calls that fail the same way (rule + failure type + intent) collapse into one case with a count. Before anything is written, every turn containing PII (card, SSN, phone, email, date of birth, address, account number) a self-introduced name ("my name is …"), or a short number given right after a request for a security code, CVV or PIN has its text replaced and its audio silenced, and the result is scanned again; a case that still shows PII isn't stored. Cases wait in `replay/pending/` until someone approves or discards them, and only approved cases reach `replay/suite/`, which you can point the GitHub Action's `calls` input at.

Name detection is a heuristic: it catches people introducing themselves, not every name mentioned in passing.

---

## Simulated callers

Test an agent *before* release by having AudioTrace call it. Each scenario file names the caller's goal, a persona (`neutral`, `frustrated`, `heavy_accent`, `interrupter`, `silent`, or your own), a line condition (`clean`, `cafe`, `street`, `car`, `bad_line`, or your own noise file), and the success criteria:

```yaml
name: reschedule-appointment
goal: Move my Tuesday 3pm appointment to Thursday morning.
persona: interrupter
noise: cafe
max_turns: 12
success:
  outcome: completed
  must_mention: ["Thursday"]
  judge: The agent confirmed a specific new time on Thursday morning.   # optional, graded by Claude
```

```bash
pip install "audiotrace[simulate]"
audiotrace simulate --init scenarios                 # example scenarios + a custom persona
audiotrace simulate scenarios --target mock          # play each scenario's scripted mock agent
audiotrace simulate scenarios --target my_agent:make_target -b sim-baseline.json
```

Claude plays the caller (set `ANTHROPIC_API_KEY`), Kokoro voices it locally, and the agent's replies are transcribed with Whisper when the target doesn't return text. Each call is recorded as stereo (caller left, agent right), analyzed like any other recording, and given a `simulation` verdict. The command exits non-zero when a scenario's task isn't completed or, with `-b`, when a metric regresses against the baseline (keyed by scenario name; write one with `--write-baseline`).

Targets:

- `--target mock` replays the `mock:` script in each scenario (no agent needed).
- `--target vapi:<assistant_id>` calls a Vapi assistant over Vapi's WebSocket transport (`VAPI_API_KEY`), streaming the caller's audio in real time.
- `--target my_module:make_target` plugs in any other agent: a function that takes a scenario and returns an object with `start(scenario)`, `respond(caller_audio, caller_text)` and `close()` (see `audiotrace.simulate.Target`).

Retell and SIP targets aren't available yet: Retell web calls only connect through Retell's WebRTC client, and SIP needs a full SIP/RTP stack ([PRD 0010](docs/prd/0010-simulated-callers.md)).

In CI, the GitHub Action runs scenarios too:

```yaml
      - uses: dimastatz/audiotrace@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          VAPI_API_KEY: ${{ secrets.VAPI_API_KEY }}
        with:
          scenarios: tests/scenarios
          target: vapi:${{ vars.STAGING_ASSISTANT_ID }}
          calls: tests/calls            # optional: also gate recorded calls
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