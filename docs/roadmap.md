# AudioTrace Roadmap

High-level milestones and ordering. Each item links to its spec in
[`docs/prd/`](./prd/README.md). Granular tasks live in GitHub Issues, not here —
this file answers *what's next and in what order*.

---

## Phase M — First Monetization (active priority)

**Goal: a first paid invoice within ~6 weeks (target by 2026-08-09).** Not first
revenue at scale — the *first dollar from a real customer*, to validate
willingness to pay before we build anything heavy.

**Strategy: a paid design-partner pilot, delivered concierge-style.** We do *not*
build a SaaS first. We sell a managed outcome to 1–3 voice-AI teams using the OSS
library plus minimal glue, and we deliver it by hand if we have to. The product
catches up to the revenue, not the other way around.

**The wedge: "regression gating + a quality dashboard for your voice agent."**
Chosen because it (a) is deliverable today on top of the existing pipeline,
(b) carries no compliance/liability burden, and (c) maps exactly to the published
[article series](./articles/) — so the pitch is already written. (Compliance
packs are higher-value but slower to sell and riskier; they come *after* the first
dollar, not before.)

**Pricing:** flat pilot fee of **$500–$1,000 / month**, month-to-month, "early
access + we run it for you." Cheap enough to clear procurement on a credit card,
real enough to prove willingness to pay.

### Prerequisites (must ship first — blocks the pilot)

- [x] Events extraction (outcome, drop-off, intent, compliance) — [PRD 0005](./prd/0005-events.md)
- [x] Latency waterfall extraction — [PRD 0006](./prd/0006-latency.md)
  - *These complete the `CallReport`. The pilot's value (latency + drop-off +
    quality trends) depends on them, so they jumped the queue.*

### Workstream A — Minimum sellable increment (weeks 1–3)

- [x] Quality/regression **report output**: a single `analyze()`-fed HTML + JSON
      summary a customer can actually read (per-call + run-over-run deltas) — [PRD 0007](./prd/0007-report.md)
- [x] **Baseline + drift check**: commit a baseline, flag regressions vs. it
      (the pytest/CI pattern from [devto-3](./articles/devto-3-voice-agents-in-ci.md)) — [PRD 0008](./prd/0008-regression-gate.md)
- [x] **GitHub Action** wrapper so a customer can drop it into CI in <15 min — [`action.yml`](../action.yml)

### Workstream B — Payment rails (week 1, ~half a day)

- [ ] Stripe payment link / invoicing set up
- [ ] `COMMERCIAL-LICENSE.md` + a one-page pilot agreement (scope, price, term)
- [ ] GitHub Sponsors enabled as a low-friction backstop

### Workstream C — Design-partner motion (weeks 1–6, in parallel)

- [ ] Build a list of 20 target teams (Vapi/Retell/LiveKit/Pipecat builders from
      Discords, the HN/Reddit launch, inbound from the article series)
- [ ] 10+ discovery calls → qualify on *acute pain + budget*
- [ ] Convert 1–3 to a paid pilot; **first invoice paid = Phase M done**

### Definition of done

A customer's payment has cleared. Capture what they paid *for* (the wedge that
closed) — that decides whether Phase 4 is the managed cloud or a compliance pack.

---

## Phase 0 — Foundation

- [x] Repo scaffolding: packaging, `src/` layout, tests, CI, Docker
- [x] Public data contract: `CallReport` Pydantic models
- [x] Core `analyze()` pipeline (MediaInfo) — [PRD 0001](./prd/0001-mediainfo.md)

## Phase 1 — Single-call analysis (current)

- [x] Transcription + speaker diarization (Whisper + pyannote) — [PRD 0002](./prd/0002-transcript.md)
- [x] Quality signals (silence gaps, interruptions, pace, pitch — Librosa) — [PRD 0003](./prd/0003-quality.md)
- [x] Sentiment extraction (local Transformers) — [PRD 0004](./prd/0004-sentiment.md)
- [x] Cost attribution model
- [x] Events extraction (outcome, drop-off, intent, compliance) — [PRD 0005](./prd/0005-events.md)
- [x] Latency waterfall extraction — [PRD 0006](./prd/0006-latency.md)

## Phase 2 — Providers & Intelligence

- [ ] Provider adapters: Vapi, Retell, Twilio, Deepgram, ElevenLabs

## Phase 3 — Compliance & polish

- [ ] Compliance flag detection (PII, consent gaps)
- [ ] Custom webhook adapter
- [ ] Docs site + examples
