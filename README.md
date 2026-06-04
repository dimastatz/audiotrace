<div align="center">
<h1 align="center"> LangVox </h1> 
<h3>Voice Agents Observability Framework</br></h3>
<img src="https://img.shields.io/badge/Progress-10%25-red"> <img src="https://img.shields.io/badge/Feedback-Welcome-green">
</br>
</br>
<kbd>
<img src="./docs/Langvox.png?raw=true" width="256px"> 
</kbd>
</div>

---

## System Architecture

A purpose-built observability platform that sits on top of any voice agent stack and turns raw call data into structured, actionable intelligence.

``` Bash
┌─────────────────────────────────────────────────────────────────┐
│                     Voice Agent Providers                       │
│         Vapi · Retell · ElevenLabs · Twilio · Custom            │
└────────┬───────────┬──────────────┬──────────────┬─────────────-┘
         │           │              │              │
         ▼           ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Ingestion Layer                            │
│           Webhooks · SDK · REST API · Streaming                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Processing Pipeline                          │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────-┐  │
│  │Transcription│ │Latency Audit │ │  Quality   │ │  Cost     │  │
│  │+ Diarization│ │STT/LLM/TTS   │ │  Scoring   │ │Attribution│  │
│  └─────────────┘ └──────────────┘ └────────────┘ └──────────-┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Structured Data Store                         │
│       Transcripts · Metrics · Events · Cost Records             │
└──────────┬──────────────┬──────────────┬────────────────────────┘
           │              │              │
           ▼              ▼              ▼
    ┌────────────┐ ┌────────────┐ ┌────────────────┐
    │  Engineer  │ │  PM / QA   │ │      Exec      │
    │ Dashboard  │ │ Dashboard  │ │   Dashboard    │
    └────────────┘ └────────────┘ └────────────────┘
                              │
                              ▼
               ┌──────────────────────────┐
               │    Alerts & Integrations │
               │  Slack · PagerDuty · API │
               └──────────────────────────┘
```

---

## How It Works

### 1. Ingestion Layer

LangVox connects to any voice agent provider via webhooks, SDK, REST API, or streaming connectors. Supported out of the box: **Vapi, Retell, ElevenLabs, Twilio, Deepgram**, and custom LLM-powered telephony stacks.

The platform is fully stack-agnostic — it does not care which LLM, STT, or TTS provider runs underneath.

```
  Vapi ──┐
Retell ──┤
         ├──► Webhook / SDK / REST ──► LangVox Ingestion
 Twilio ─┤
Custom ──┘
```

---

### 2. Processing Pipeline

Once call data is ingested, four processing modules run in parallel:

```
                    ┌─────────────────────┐
                    │   Raw Call Data     │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐───────────────────┐
           │                   │                   │                   │
           ▼                   ▼                   ▼                   ▼
  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
  │  Transcription  │ │  Latency Audit  │ │ Quality Scoring │ │Cost Attribution │
  │                 │ │                 │ │                 │ │                 │
  │ · Diarization   │ │ · STT timing    │ │ · Interruptions │ │ · Per-provider  │
  │ · Intent tags   │ │ · LLM latency   │ │ · Silence gaps  │ │ · Per-call      │
  │ · Outcome tags  │ │ · TTS render    │ │ · Sentiment     │ │ · Per-outcome   │
  │ · Full-text idx │ │ · P50/P95/P99   │ │ · Speaking pace │ │ · Budget alerts │
  └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
```

#### Transcription

- Speaker-diarized transcripts for every call
- Full-text search across the call library
- Tagging by outcome, intent, or failure type

#### Latency Audit

``` Bash
  Call start
      │
      ├──► STT          [~120ms] ──────────────────────────┐
      │                                                    │
      ├──► LLM first token  [~400ms] ─────────────────-─┐  │
      │                                                 │  │  Waterfall
      ├──► LLM full response [~650ms] ─────────────-─┐  │  │  view per
      │                                              │  │  │  call
      ├──► TTS render    [~200ms] ────────────────┐  │  │  │
      │                                           │  │  │  │
      └──► Telephony handoff [~80ms] ──────────┐  │  │  │  │
                                               ▼  ▼  ▼  ▼  ▼
                                            Total end-to-end latency
```

- Per-call breakdown of time spent in each pipeline stage
- P50 / P95 / P99 views
- Configurable threshold alerting per stage

#### Quality Scoring

- Automated detection of interruptions, silence gaps, speaking pace, and turn length
- Caller sentiment shift tracking across the conversation
- Aggregate scores per agent version for prompt/persona comparison

#### Cost Attribution

``` Bash
  One call =
    STT cost   ($/min)
  + LLM cost   ($/1k tokens)
  + TTS cost   ($/character)
  + Telephony  ($/min)
  ─────────────────────────
  = Cost per call
  = Cost per successful outcome
```

- Unified cost-per-call breakdown across all providers
- Itemized by STT, LLM, TTS, and telephony
- Cost-per-successful-outcome and budget alerting

---

### 3. Structured Data Store

All processed outputs are normalized into a consistent schema and indexed for:

- Full-text transcript search
- Filtering by date, agent version, campaign, or phone number
- Historical trend analysis and anomaly detection
- Cross-version funnel comparison

``` Bash
  ┌──────────────────────────────────────────────────┐
  │              Structured Data Store               │
  │                                                  │
  │  calls          metrics         events           │
  │  ├─ call_id     ├─ latency_ms   ├─ drop_off      │
  │  ├─ transcript  ├─ quality_score├─ interruption  │
  │  ├─ duration    ├─ cost_usd     ├─ silence_gap   │
  │  ├─ agent_ver   ├─ sentiment    └─ intent_tag    │
  │  └─ outcome     └─ p95_latency                   │
  └──────────────────────────────────────────────────┘
```

---

### 4. Dashboards & Alerts

The same data surfaces through role-appropriate views — no log reading required.

```
  ┌─────────────────────────────────────────────────────────┐
  │                  Structured Data Store                  │
  └───────────┬──────────────────┬──────────────────────────┘
              │                  │                  │
              ▼                  ▼                  ▼
  ┌───────────────────┐ ┌────────────────┐ ┌────────────────┐
  │    Engineer       │ │    PM / QA     │ │      Exec      │
  │                   │ │                │ │                │
  │ Latency waterfall │ │ Drop-off funnel│ │ Call volume    │
  │ Pipeline errors   │ │ Quality scores │ │ Cost trends    │
  │ P50/P95/P99       │ │ A/B comparison │ │ CSAT proxy     │
  └───────────────────┘ └────────────────┘ └────────────────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
              ┌──────────────────────────────────────┐
              │         Alerts & Integrations        │
              │   Slack · PagerDuty · Email · API    │
              └──────────────────────────────────────┘
```

| Role | Key metrics |
|---|---|
| Engineer | Latency waterfall, pipeline errors, P95/P99 breakdowns |
| PM / QA | Drop-off funnels, quality scores, A/B script comparison |
| Exec | Call volume, cost trends, CSAT proxy scores |

Alerts fire to **Slack, PagerDuty, or email** when latency, error rate, cost, or quality thresholds are breached. Webhook support is available for custom workflows.

---

## Architecture Principle

The key architectural bet is the normalization layer: by converting data from any provider into a consistent internal schema, LangVox becomes the **persistent observability layer** even as teams swap out LLMs, TTS engines, or telephony stacks.

``` Bash
  Without LangVox:          With LangVox:

  Vapi ──► your app         Vapi ──┐
  Retell ──► ??? logs               ├──► LangVox ──► consistent schema
  Twilio ──► silence        Twilio ─┘              ──► your dashboards
```

This means:

- No re-instrumentation when switching providers
- Call history, quality benchmarks, and alert thresholds survive stack migrations
- Switching costs compound over time as data accumulates

---

## Integrations

| Category | Providers |
|---|---|
| Telephony / voice agents | Vapi, Retell, Twilio, ElevenLabs |
| STT | Deepgram, and any webhook-compatible provider |
| Alerting | Slack, PagerDuty, email, custom webhooks |
| Deployment | Cloud SaaS, on-prem / VPC (Enterprise) |

---

## Compliance & Security

- SOC 2 Type II certification (roadmap: Phase 3)
- HIPAA-compliant tier for healthcare and financial services (roadmap: Phase 4)
- On-premises / VPC deployment available on Enterprise plan
- Role-based access control with SSO support (Scale tier and above)
