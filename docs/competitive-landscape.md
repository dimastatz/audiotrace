# Competitive landscape

*Snapshot from knowledge to early 2026 — the voice-AI tooling space churns fast,
so treat named vendors as **representative**, not exhaustive, and re-check before
citing. Update this doc with real objections after discovery calls.*

## The reframe

Most of what competitors do that AudioTrace doesn't is either **(a) the upper two
layers of our own vision that aren't built yet** (LangTrace observability,
LangGate simulation) or **(b) depth in signals we already emit but keep shallow.**
Very little is a surprise — it's mostly roadmap.

## Where we are *not* behind (the moat)

- **Open-source + self-hostable.** Nearly every competitor is closed SaaS. Teams
  that won't ship call recordings to a third party have nowhere else to go.
- **CI/CD gating led from day one** (GitHub Action + CLI) — many LLM-eval tools
  bolt CI on as an afterthought.
- **One normalized `CallReport` across providers** — the "stop rebuilding this"
  pitch, mostly unserved in OSS.

The competitive answer to "you're missing X" is not "go build X" — it's
**"we're open-source and we'll run it for you today,"** which no SaaS player can say.

## Gaps, by category

| Capability | Representative vendors | AudioTrace today |
|---|---|---|
| Pre-deploy simulation / synthetic testing | Coval, Hamming, Cekura, Bespoken | ❌ None — we analyze real recordings only. Unbuilt **LangGate**. |
| Live/hosted observability (dashboards, alerting, funnels, rollups) | Langfuse, LangSmith, Arize, Observe.AI, native Vapi/Retell | ❌ Static HTML per call; no ingestion/live view. Unbuilt **LangTrace**. |
| Datasets + eval harness + LLM-as-judge + human labeling | Braintrust, LangSmith, Langfuse, Phoenix | ⚠️ Per-call regression gate only; no datasets/judge/annotation. |
| Provider auto-ingestion (webhooks/APIs) | ~All of them | ❌ Adapters TBD; local files only. |
| Task-success / semantic eval (goal completion, tool-call correctness, grounding) | Coval, Hamming, contact-center CI vendors | ⚠️ Shallow `events` (outcome, intent); no real task scoring. |
| Battle-tested audio intelligence (calibrated sentiment, robust diarization, barge-in, PII redaction) | Deepgram, AssemblyAI, Observe.AI | ⚠️ Early/heuristic — interruptions currently inert, diarization fallback fragile. |
| Enterprise posture (multi-tenant SaaS, RBAC, SOC2/HIPAA, retention) | Gong, Observe.AI, Cresta | ❌ We're a library. |

## Prioritized — by distance to the first paid pilot

Priority here is **not** "how big the gap is." It's "does closing this move us toward
the first dollar." Everything below P1 is demand-gated: **build only when discovery
calls or a live pilot produce the trigger evidence.**

### P0 — Build nothing; sell the wedge by hand
The Phase M wedge (regression gating + quality dashboard, run for you) needs the
core layer (have it) + concierge delivery (have us). Simulation, live dashboards,
and enterprise posture are **irrelevant** to closing pilot #1. Do not pre-build.

### P1 — Provider ingestion: one Vapi webhook adapter
The single most likely objection in a discovery call: *"do I have to export WAVs by
hand?"* Highest-ROI feature gap.
- **Trigger to build:** 2+ prospects raise ingestion friction unprompted.
- **Scope:** one adapter (Vapi first), not the whole matrix.

### P2 — Core signal credibility
If a paying pilot disputes a number, the sale is at risk. Covers real interruptions
(off the pyannote diarization timeline, see [PRD 0003](./prd/0003-quality.md)),
diarization robustness, and sentiment calibration.
- **Trigger:** a pilot customer challenges a metric's believability.

### P2 — Run-level aggregation (LangTrace seed)
Trends across calls instead of per-call HTML. The first honest step toward the
observability layer.
- **Trigger:** a pilot asks for "how is my agent trending" rather than single-call reports.

### P3 — Pre-deploy simulation (LangGate)
A separate product, not a feature. Only after the first dollar **and** evidence that
customers want *testing* over *observability*. The Phase M definition-of-done
explicitly defers this choice to what the pilot reveals.

### P3 — Datasets / LLM-judge / semantic eval
Depth for the eval story; meaningful only once the core layer is trusted and a
golden corpus exists (also gates [PRD 0009](./prd/0009-drift-gating.md) Part B).

### P4 — Enterprise posture (SOC2, RBAC, multi-tenant)
Concierge pilots don't need it. Build only when moving upmarket to buyers who
require it — a post-Phase-M concern.

## How to use this doc

After each discovery call, log which gap (if any) the prospect raised. When a P1/P2
trigger fires with real evidence (not a hunch), promote it into a PRD and the
roadmap. Let demand — not this table — decide what gets built.
