# PRD 0010 — Simulated callers (pre-release testing)

**Status:** Draft
**Owner:** Dima Statz
**Source:** [Issue #48](https://github.com/dimastatz/audiotrace/issues/48)
**Related:** [PRD 0008 (regression gate)](./0008-regression-gate.md),
[PRD 0011 (production replay)](./0011-production-replay.md),
[roadmap Phase 5](../roadmap.md)

## Summary

AudioTrace only analyzes calls that already happened. Teams change prompts,
models, or tools and find out what broke when real customers call; the only
pre-release testing is engineers phoning the bot by hand — slow, inconsistent,
narrow coverage.

Simulated callers close that gap: AudioTrace **places synthetic calls against a
staging agent** using scripted scenarios, caller personas, and background-noise
conditions. Each recorded call runs through the existing `analyze()` pipeline,
plus a new **task-completion verdict** checked against the scenario's success
criteria. Results feed the same gate as [PRD 0008](./0008-regression-gate.md).

**Users:** voice-agent engineers and QA leads shipping on Vapi, Retell,
LiveKit, or custom SIP stacks.

## Goals

- **Scenario files (YAML)** — each describes the caller goal, persona, noise
  profile, script/turn hints, and explicit success criteria:

  ```yaml
  name: reschedule-appointment
  goal: Move my Tuesday 3pm appointment to Thursday morning
  persona: interrupter
  noise: cafe
  max_turns: 12
  success:
    outcome: completed
    intent: reschedule
    must_mention: ["Thursday"]
  ```

- **Personas** — built-in defaults (`neutral`, `frustrated`, `heavy_accent`,
  `interrupter`, `silent`) that set caller LLM style, TTS voice, barge-in
  behavior, and response delay. User-definable in YAML.
- **Noise profiles** — built-in defaults (`clean`, `cafe`, `street`, `car`,
  `bad_line`) mixed into caller audio at a configurable SNR; user-supplied
  noise files allowed.
- **Task-completion verdict** — a pass/fail per call (plus reason), evaluated
  from the transcript and `Events` against the scenario's `success` block,
  reported alongside quality, latency, and sentiment.
- **Runners** — `audiotrace simulate <scenarios-dir> --target <agent>` locally;
  the existing GitHub Action gains a `scenarios` input.
- **Targets at launch** — Vapi and Retell (via their outbound/web-call APIs);
  generic SIP as a fallback for custom stacks.
- **Time to first run under 15 minutes** — ship example scenarios and a
  `audiotrace simulate --init` scaffold.

## Non-goals

- **Load / concurrency testing.** Calls run sequentially or at low, bounded
  concurrency; this is functional QA, not a load generator.
- **LiveKit / Twilio targets at launch.** Follow-on adapters (see
  [Phase 2 provider adapters](../roadmap.md)).
- **Auto-generating scenarios** from production traffic — that's
  [PRD 0011](./0011-production-replay.md).
- **Reimplementing audio decoding.** Recordings go through the existing
  FFmpeg-based pipeline.

## Design notes

- **Caller loop:** caller LLM (persona prompt + goal) → TTS → noise mix →
  target agent; agent audio → STT → caller LLM. The whole call is recorded as
  stereo (caller / agent) and handed to `analyze()`.
- **Public contract impact:** the verdict needs a home on `CallReport`, e.g. a
  new optional `simulation: SimulationResult | None` (`scenario`, `persona`,
  `noise`, `task_completed: bool`, `reason: str`). This is an **additive**
  change to `models.py`, but still a contract change — update the README's
  `CallReport` tree in the same PR.
- **Credentials** for caller LLM/TTS and target providers come from env vars;
  never written into reports.
- **Optional extra:** heavy deps (TTS, telephony SDKs) live behind
  `pip install audiotrace[simulate]` so the core library stays light.
- Python 3.9+ compatible, like the rest of the library.

## Open questions

- Which caller LLM/TTS by default — hosted (cost per run) vs. local (setup
  time vs. the 15-minute target)?
- Is the verdict rule-based only (the `success` block), or optionally
  LLM-judged for fuzzy goals?
- How do simulated calls interact with the baseline — separate baseline
  file, or keyed by scenario name in the existing one?

## Success metrics

- Install → first simulated test run in **under 15 minutes**.
- Design partners replace **at least half** of their manual QA calls.
- Regressions caught **before deploy** rather than reported by customers.

## Acceptance criteria

- Scenario, persona, and noise YAML schemas validate with clear errors.
- `audiotrace simulate` runs a scenario directory against a mocked target and
  emits a `CallReport` per scenario with a populated task-completion verdict.
- A failing verdict makes `audiotrace simulate` / the Action exit non-zero.
- Vapi and Retell adapters covered by tests against recorded/mocked API
  responses; SIP adapter covered at the interface level.
- README `CallReport` tree updated for the new field.
- `./scripts/test_local.sh test` passes with coverage ≥ 95%.
