# Vision Architecture


## AudioTrace · LangTrace · LangGate

> A three-layer platform for building, monitoring, and certifying production voice AI agents.

---

## Executive Summary

Voice AI is being shipped to production with almost zero visibility into what happens on calls. Teams using Vapi, Retell, ElevenLabs, Twilio, or custom LLM-powered telephony stacks face three compounding problems: they cannot observe what is happening in live calls, they cannot test agents before deploying them, and they have no shared infrastructure to build either capability on.

This platform solves all three — as a unified, layered system:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LangGate                                    │
│            Pre-deploy simulation & CI/CD quality gate               │
│      stress-test · regression blocking · compliance checks          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  consumes
┌───────────────────────────────▼─────────────────────────────────────┐
│                         LangTrace                                   │
│              Live call observability & analytics                    │
│        dashboards · alerting · funnels · cost attribution           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  consumes
┌───────────────────────────────▼─────────────────────────────────────┐
│                        AudioTrace                                   │
│              Open-source voice analysis framework                   │
│   transcription · quality scoring · latency · sentiment · cost      │
└─────────────────────────────────────────────────────────────────────┘
                                │  built on
        ┌───────────────────────┼───────────────────┐
        ▼                       ▼                   ▼
     FFmpeg                  Librosa           pyannote.audio
  (audio plumbing)     (feature extraction)   (diarization)
        +                       +                   +
     Whisper               Transformers           Pydantic
  (transcription)          (sentiment)           (schema)
```

---

## Layer 1 — AudioTrace

### What it is

AudioTrace is the **open-source voice analysis framework** that powers everything else. It takes a raw audio file as input and returns a fully structured, semantically rich `CallReport` — every quality signal, sentiment shift, latency breakdown, cost figure, and compliance flag extracted and normalized into a single object.

It does not build dashboards. It does not make deploy decisions. It is pure infrastructure — the shared primitive layer that both LangTrace and LangGate are built on top of.

### Why open-source

```
  Open-source AudioTrace
          │
          ├──► Community builds provider adapters
          │
          ├──► Developers instrument agents against AudioTrace schema
          │         └──► Creates adoption before anyone pays
          │
          ├──► AudioTrace becomes the standard call schema
          │         └──► Competitors must be compatible with it
          │
          └──► LangTrace + LangGate are the commercial layer on top
                        same model as Grafana · Elastic · Airbyte
```

### Input

```python
audiotrace.analyze(
    audio    = "call_recording.wav",    # .wav .mp3 .ogg .flac .m4a or PCM stream
    metadata = {
        "call_id":       "abc123",
        "agent_version": "v2.1",
        "provider":      "vapi",
        "campaign":      "healthcare_intake"
    }
)
```

### Output — CallReport

```
CallReport
│
├── 1. TRANSCRIPT
│   ├── full_text: str
│   ├── turns: List[Turn]
│   │     ├── speaker: "agent" | "caller"
│   │     ├── text: str
│   │     ├── start_ms: int
│   │     ├── end_ms: int
│   │     └── duration_ms: int
│   └── language: str
│
├── 2. QUALITY SCORES
│   ├── overall_score: float          # 0.0 – 1.0
│   ├── interruptions: int            # agent cut caller off N times
│   ├── silence_gaps: List[Gap]       # gaps above threshold ms
│   ├── speaking_pace_wpm: float      # agent words per minute
│   ├── pitch_variance: float         # monotone vs animated
│   ├── agent_energy: float           # loudness / presence
│   └── turn_length_avg_ms: float
│
├── 3. SENTIMENT
│   ├── by_turn: List[float]          # per-turn sentiment score
│   ├── overall: float                # -1.0 to 1.0
│   ├── shift_points: List[int]       # turns where sentiment dropped
│   ├── caller_frustration: bool
│   └── final: "positive" | "neutral" | "negative"
│
├── 4. LATENCY
│   ├── stt_ms: int
│   ├── llm_first_token_ms: int
│   ├── llm_full_response_ms: int
│   ├── tts_ms: int
│   ├── telephony_ms: int
│   ├── total_ms: int
│   └── waterfall: List[LatencySpan]
│
├── 5. COST
│   ├── stt_usd: float
│   ├── llm_usd: float
│   ├── tts_usd: float
│   ├── telephony_usd: float
│   └── total_usd: float
│
├── 6. EVENTS
│   ├── drop_off: bool
│   ├── drop_off_turn: int | None
│   ├── intent_detected: str
│   ├── outcome: "completed" | "dropped" | "failed"
│   ├── compliance_flags: List[str]
│   └── failure_type: "loop" | "misunderstanding" | "silence" | None
│
└── 7. METADATA
    ├── call_id: str
    ├── agent_version: str
    ├── provider: str
    ├── duration_ms: int
    ├── audio_quality: float
    └── processed_at: datetime
```

### Processing Pipeline

```
  Raw audio file
       │
       ▼
  ┌─────────────────────────────────────────────────────┐
  │  FFmpeg — Audio normalization                       │
  │  Convert to 16kHz mono WAV · split turns            │
  └───────────────────┬─────────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  ┌─────────┐   ┌──────────┐   ┌──────────────┐
  │ Whisper │   │ Librosa  │   │   pyannote   │
  │  (STT)  │   │(features)│   │ (diarization)│
  └────┬────┘   └────┬─────┘   └──────┬───────┘
       │              │                │
       ▼              ▼                ▼
  transcript    silence gaps      speaker labels
  full text     pace / pitch      who said what
  timestamps    energy / RMS      turn boundaries
       │              │                │
       └──────────────┼────────────────┘
                      ▼
             ┌─────────────────┐
             │  Transformers   │
             │  (sentiment)    │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │   CallReport    │
             │  (Pydantic)     │
             └─────────────────┘
```

### Dependency Stack

```bash
# Core
pip install audiotrace

# Under the hood
ffmpeg-python        # audio plumbing
librosa              # feature extraction
pyannote.audio       # speaker diarization
openai-whisper       # offline transcription
transformers         # sentiment + intent
pydantic             # call schema
numpy / soundfile    # signal math
```

### Module API

```python
from audiotrace.adapters   import VapiAdapter, RetellAdapter, TwilioAdapter
from audiotrace.call       import Call, CallBuilder
from audiotrace.transcript import Transcript, Diarizer
from audiotrace.score      import QualityScorer, SentimentTracker
from audiotrace.latency    import LatencyTracker, LatencyWaterfall
from audiotrace.cost       import CostCalculator, CostReport
from audiotrace.sim        import SimCaller, CallerPersona
from audiotrace.eval       import EvalSuite, QualityGate
```

---

## Layer 2 — LangTrace

### What it is

LangTrace is the **live call observability and analytics platform**. It ingests `CallReport` objects from AudioTrace in real time, stores them in a structured data store, and surfaces the results through role-appropriate dashboards and alerting.

It answers the question: **what is happening across all live and historical calls right now?**

### Architecture

```
  Voice providers
  Vapi · Retell · ElevenLabs · Twilio · Custom
       │
       │  webhook / SDK / REST / stream
       ▼
  ┌─────────────────────────────────────────┐
  │           Ingestion Layer               │
  └───────────────────┬─────────────────────┘
                      │  raw audio + metadata
                      ▼
  ┌─────────────────────────────────────────┐
  │        AudioTrace Processing            │
  │   → CallReport (transcript, scores,     │
  │     sentiment, latency, cost, events)   │
  └───────────────────┬─────────────────────┘
                      │  structured CallReport
                      ▼
  ┌─────────────────────────────────────────┐
  │        Structured Data Store           │
  │  calls · metrics · events · costs      │
  └──────┬──────────────┬──────────────┬───┘
         │              │              │
         ▼              ▼              ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │  Engineer  │ │  PM / QA   │ │    Exec    │
  │ Dashboard  │ │ Dashboard  │ │ Dashboard  │
  └────────────┘ └────────────┘ └────────────┘
         │              │              │
         └──────────────┼──────────────┘
                        ▼
            ┌───────────────────────┐
            │   Alerts             │
            │  Slack · PagerDuty   │
            │  Email · Webhook     │
            └───────────────────────┘
```

### Core Modules

#### Live Transcript Viewer
- Searchable, speaker-diarized transcripts for every call
- Full-text search across the entire call library
- Filter by date, agent version, campaign, phone number
- Tag calls by outcome, intent, or failure type

#### Conversation Quality Analytics
- Automated detection of interruptions, silence gaps, pace, and turn length
- Caller sentiment shift tracking per call and in aggregate
- Quality score comparison across agent versions (v1 vs v2)
- Top failure type breakdown by campaign and agent

#### Latency Waterfall

```
  Call start
      │
      ├──► STT               [avg 120ms] ░░░
      ├──► LLM first token   [avg 400ms] ░░░░░░░░░░░
      ├──► LLM full response [avg 650ms] ░░░░░░░░░░░░░░░░░
      ├──► TTS render        [avg 200ms] ░░░░░
      └──► Telephony         [avg  80ms] ░░
                                         P50  P95  P99
```

Per-call and aggregate latency breakdown by pipeline stage with configurable threshold alerting.

#### Drop-off Funnel

```
  Call start         100%
       │
  Turn 1 (greeting)   97%  ─── 3% drop
       │
  Turn 3 (intent)     84%  ─── 13% drop  ◄ highest drop point
       │
  Turn 6 (verify)     79%  ─── 5% drop
       │
  Turn 9 (confirm)    71%  ─── 8% drop
       │
  Completion          71%
```

Visual map of drop-off rates at each conversation node. Compare funnels across script versions.

#### Cost Attribution Dashboard
- Unified cost-per-call breakdown across all providers
- Itemized by STT, LLM, TTS, and telephony
- Cost-per-successful-outcome
- Budget alerting before thresholds are exceeded
- Historical trend and anomaly detection

### Role-Based Dashboards

| Role | View | Key signals |
|---|---|---|
| **Engineer** | Pipeline health | Latency waterfall · P95/P99 · error rate · stage breakdown |
| **PM / QA** | Conversation quality | Quality scores · drop-off funnels · A/B comparison · failure types |
| **Exec** | Business overview | Call volume · cost trends · CSAT proxy · completion rates |

### Alerting

```python
# Example alert configuration
langtrace.alerts.configure([
    Alert(metric="latency_p95",    threshold=1200,  channel="pagerduty"),
    Alert(metric="quality_score",  threshold=0.75,  channel="slack"),
    Alert(metric="drop_rate",      threshold=0.10,  channel="slack"),
    Alert(metric="cost_per_call",  threshold=0.12,  channel="email"),
    Alert(metric="error_rate",     threshold=0.05,  channel="pagerduty"),
])
```

### Integrations

| Category | Supported |
|---|---|
| Voice providers | Vapi · Retell · Twilio · ElevenLabs · Deepgram |
| Alerting | Slack · PagerDuty · Email · Custom webhook |
| Auth | SSO (Scale tier and above) |
| Deployment | Cloud SaaS · On-prem / VPC (Enterprise) |

### How LangTrace consumes AudioTrace

```python
from audiotrace import analyze
from langtrace  import ingest

# Every incoming call
raw_call   = adapter.receive(webhook_payload)
report     = analyze(raw_call.audio, raw_call.metadata)
ingest(report)   # → stored, indexed, surfaced in dashboard
```

---

## Layer 3 — LangGate

### What it is

LangGate is the **pre-deploy simulation and CI/CD quality gate** for voice agents. It stress-tests an agent against thousands of synthetic callers before every release and blocks the deploy if quality or compliance regresses.

It answers the question: **is this agent safe to ship?**

### The core problem it solves

```
  Without LangGate:              With LangGate:

  Write prompt                   Write prompt
       │                              │
  Deploy to prod        ──►      Run 1,000 synthetic callers
       │                              │
  Real callers hit bugs          AudioTrace analyzes all calls
       │                              │
  Debug from complaints          Quality gate evaluates results
                                       │
                              PASS ────┼──── FAIL
                                       │         │
                                  Deploy       Block deploy
                                               + diff report
```

### Architecture

```
  CI/CD trigger (GitHub Actions · GitLab CI · Jenkins)
       │
       ▼
  ┌───────────────────────────────────────────────────┐
  │              LangGate Runner                      │
  │                                                   │
  │  1. Pull agent endpoint (staging)                 │
  │  2. Load caller personas + scenarios              │
  │  3. Spin up N synthetic callers (concurrency 50+) │
  │  4. Run all calls against agent                   │
  │  5. Pass audio to AudioTrace for analysis         │
  │  6. Evaluate CallReports against QualityGate      │
  │  7. Compare to baseline (previous release)        │
  │  8. Return PASS or FAIL + full diff report        │
  └───────────────────────────────────────────────────┘
       │
       ├── PASS → deploy proceeds
       └── FAIL → deploy blocked + report posted to PR
```

### Synthetic Caller Simulation

```python
from audiotrace.sim import CallerPersona, ScenarioRunner

# Define caller personas
personas = [
    CallerPersona(
        name   = "confused_elderly",
        traits = ["speaks slowly", "asks for repetition", "easily frustrated"],
        intent = "book a medical appointment"
    ),
    CallerPersona(
        name   = "rushed_professional",
        traits = ["impatient", "interrupts often", "wants quick answers"],
        intent = "reschedule existing appointment"
    ),
    CallerPersona(
        name   = "non_native_speaker",
        traits = ["heavy accent", "searches for words", "polite"],
        intent = "check appointment status"
    ),
    CallerPersona(
        name   = "adversarial",
        traits = ["tries to go off-script", "asks unusual questions"],
        intent = "unknown"
    ),
]

runner = ScenarioRunner(agent_endpoint="wss://staging.myagent.com")
results = runner.run(personas=personas, n=1000, concurrency=50)
```

### Quality Gate

```python
from audiotrace.eval import QualityGate

gate = QualityGate(
    min_quality_score   = 0.80,   # overall quality floor
    max_latency_p95_ms  = 1200,   # 95th percentile latency ceiling
    max_drop_rate       = 0.05,   # max 5% callers hang up early
    max_cost_per_call   = 0.08,   # budget ceiling per call
    min_completion_rate = 0.90,   # 90% of calls must complete intent
    compliance_standard = "HIPAA" # flag any PII leakage
)

verdict = langgate.evaluate(
    reports  = sim_results,
    baseline = previous_release,
    gate     = gate
)

verdict.passed           # bool — blocks CI if False
verdict.failures         # List[str] — which gates failed
verdict.regressions      # metrics that got worse vs baseline
verdict.report()         # full diff breakdown
```

### Regression Report

```
LangGate Evaluation Report
===========================
Agent version:   v2.3  vs  baseline v2.2
Synthetic calls: 1,000
Concurrency:     50

RESULT: ✗ FAILED — 2 gates failed

Gate Results:
  ✓ quality_score      0.84   (min 0.80)   +0.02 vs baseline
  ✗ latency_p95_ms     1,340  (max 1,200)  +180ms vs baseline  ← REGRESSION
  ✓ drop_rate          0.038  (max 0.05)   -0.8% vs baseline
  ✓ cost_per_call      $0.067 (max $0.08)  +$0.003 vs baseline
  ✗ completion_rate    0.87   (min 0.90)   -3% vs baseline     ← REGRESSION

Top failure types in v2.3:
  1. silence_gap      (312 calls)   +28% vs baseline
  2. misunderstanding (187 calls)   +5%  vs baseline
  3. loop             (43 calls)    -12% vs baseline

Worst performing persona:
  confused_elderly:   completion rate 0.71  (-11% vs baseline)

Deploy blocked. Full diff at: https://langgate.io/reports/abc123
```

### CI/CD Integration

```yaml
# GitHub Actions example
- name: LangGate voice agent evaluation
  uses: langgate/action@v1
  with:
    agent_endpoint: ${{ secrets.STAGING_AGENT_URL }}
    personas:       ./langgate/personas.yaml
    gate_config:    ./langgate/gate.yaml
    baseline:       ${{ env.BASELINE_VERSION }}
    n_callers:      1000
```

### How LangGate consumes AudioTrace

```python
from audiotrace import analyze
from langgate   import evaluate

# Run sim → analyze → gate in one pipeline
sim_calls  = runner.run(personas, n=1000)
reports    = [analyze(c.audio, c.metadata) for c in sim_calls]
verdict    = evaluate(reports, gate, baseline)
```

---

## Shared Module Coverage

Both paid products are built entirely on AudioTrace. Here is the coverage map:

| AudioTrace module | LangTrace | LangGate |
|---|---|---|
| `adapters` | ✓ live call ingestion | ✓ sim call ingestion |
| `call` (schema) | ✓ storage + search | ✓ test fixtures |
| `transcript` | ✓ transcript viewer | ✓ failure analysis |
| `score` | ✓ live quality scoring | ✓ regression detection |
| `latency` | ✓ waterfall dashboards | ✓ perf benchmarks |
| `cost` | ✓ cost attribution | ✓ cost-per-test-run |
| `sim` | — | ✓ synthetic callers |
| `eval` | — | ✓ pass/fail gate |

Approximately **65% of the processing layer is shared.** Without AudioTrace, both products would duplicate this work independently.

---

## Product Positioning

```
  Problem                          Solution
  ───────                          ────────
  Calls are black boxes        ──► LangTrace transcript viewer
  No quality visibility        ──► LangTrace quality analytics
  Latency unmeasured           ──► LangTrace latency waterfall
  Drop-off invisible           ──► LangTrace drop-off funnel
  Cost unattributed            ──► LangTrace cost dashboard
  Non-engineers locked out     ──► LangTrace role-based dashboards
  Bad deploys hit prod users   ──► LangGate simulation + gate
  No regression detection      ──► LangGate diff report
  No compliance testing        ──► LangGate HIPAA / SOC2 checks
  No shared voice primitives   ──► AudioTrace open-source framework
```

---

## Go-To-Market Sequence

```
Month 1–3    Ship AudioTrace as open-source
             └──► Provider adapters · call schema · scoring primitives
             └──► 500+ developer installs before charging anything

Month 3–6    Launch LangTrace (paid SaaS)
             └──► Built entirely on AudioTrace
             └──► Starter tier $299/mo — target teams with 5K+ min/mo

Month 6–9    Launch LangGate (paid SaaS)
             └──► Synthetic caller engine + eval harness on AudioTrace
             └──► Upsell to existing LangTrace accounts first

Month 9–12   Enterprise tier
             └──► Single contract bundles LangTrace + LangGate
             └──► HIPAA compliance · on-prem / VPC · dedicated CSM
             └──► 3–5x ACV vs single-product contracts

Month 12+    AudioTrace ecosystem
             └──► Community builds vertical persona packs
             └──► Third-party integrations built on AudioTrace schema
             └──► Platform becomes the standard for voice AI evaluation
```

---

## Pricing

| Product | Tier | Price | Included |
|---|---|---|---|
| **LangTrace** | Starter | $299/mo | 10K min · 5 seats · transcripts + basic analytics |
| **LangTrace** | Growth | $999/mo | 60K min · 20 seats · full analytics + cost dashboard |
| **LangTrace** | Scale | $2,500/mo | 200K min · 50 seats · A/B funnels + SSO |
| **LangTrace** | Enterprise | Custom | Unlimited · HIPAA · on-prem · SLA |
| **LangGate** | Growth | $499/mo | 10K sim calls/mo · standard personas |
| **LangGate** | Scale | $1,500/mo | 100K sim calls/mo · custom personas + compliance |
| **LangGate** | Enterprise | Custom | Unlimited · HIPAA gate · CI/CD SLA |
| **AudioTrace** | — | Free | Open-source · self-hosted |

Overage on LangTrace: $0.004 per additional minute.
Overage on LangGate: $0.01 per additional simulation call.

---

## Defensibility

Three compounding moats:

**1. Data moat (LangTrace)** — 6 months of call history, trained quality scorers, and established alert thresholds create switching costs that compound month over month.

**2. Pipeline moat (LangGate)** — a tool that literally blocks deploys becomes load-bearing CI/CD infrastructure. Teams do not rip that out.

**3. Schema moat (AudioTrace)** — if AudioTrace becomes the standard normalized call schema in the open-source ecosystem, every tool built on it creates a distribution channel back to the commercial products.

---

## Summary

| | AudioTrace | LangTrace | LangGate |
|---|---|---|---|
| **Type** | Open-source framework | Paid SaaS | Paid SaaS |
| **Layer** | Foundation | Observability | CI/CD gate |
| **Input** | Raw audio file | Live call stream | Staging agent endpoint |
| **Output** | CallReport object | Dashboards + alerts | PASS / FAIL + diff report |
| **Primary user** | Developer | Eng · PM · QA · Exec | Eng · DevOps · Compliance |
| **Core question** | What happened in this call? | What is happening across all calls? | Is this agent safe to ship? |
| **Monetization** | Community · distribution | Usage-based SaaS | Per-simulation + enterprise |
