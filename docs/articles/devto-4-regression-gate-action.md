---
title: "A GitHub Action That Fails the Build When Your Voice Agent Gets Worse"
published: false
description: "Drop a CI gate on your voice agent's call quality in under 15 minutes. Commit a baseline of golden calls, add one Action to your workflow, and let a bad prompt/model/voice change turn the build red — no secrets, no API calls."
tags: ai, python, testing, opensource
series: Observability for AI Voice Agents
cover_image: https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/articles/audiotrace-flow.png
---

In the [last post](#) we put call audio in the test suite: treat a few golden
recordings as fixtures, analyze them on every change, and assert on the report so
a regression turns the build red. That works — but it's a pile of `pytest` you
have to write and maintain.

This post skips the boilerplate. There's now a GitHub Action that does the whole
thing: **[AudioTrace regression gate](https://github.com/marketplace/actions/audiotrace-regression-gate)**.
Point it at a folder of recordings and a committed baseline, and it fails the
build when call quality regresses — latency, sentiment, drop-off, cost, or
compliance. It runs entirely on open models, so there are no secrets and no
network calls in CI.

Here's the whole thing, start to finish.

## The idea in one sentence

Voice agents drift in ways no unit test catches — a prompt tweak makes the agent
slower, a new TTS voice makes it colder, a refactor drops a required disclosure.
So we **commit a baseline** of what "good" sounds like, and **gate every PR**
against it.

## Step 1 — Commit a baseline

Grab a handful of representative call recordings — a happy path, a frustrated
caller, a compliance-heavy call — and drop them in your repo (say `tests/calls/`).
Then generate a baseline locally:

```bash
pip install audiotrace          # FFmpeg must be on your system
audiotrace baseline tests/calls -o baseline.json
```

This analyzes every recording and writes `baseline.json` — the committed snapshot
of "good." Commit it alongside your code:

```bash
git add tests/calls baseline.json
git commit -m "Add voice-quality baseline"
```

That's your golden master. When you *intentionally* improve the agent, you
regenerate and re-commit it — same workflow as snapshot testing.

## Step 2 — Add the Action

Drop this into `.github/workflows/voice-quality.yml`:

```yaml
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

Two required inputs — where the recordings live and where the baseline lives.
That's it. The Action installs AudioTrace + FFmpeg, re-analyzes the calls,
compares each against the baseline, and **exits non-zero on any out-of-tolerance
regression**.

## Step 3 — Watch it catch a regression

Open a PR that changes a prompt or swaps the model. On the next run the gate
re-scores your golden calls and, if the agent got measurably worse, the check
fails with a summary like:

```
FAIL  frustrated_customer.wav
  Response latency (p95)  1,820ms → 2,540ms   (+39%, allowed +15%)
  Sentiment               0.12 → -0.20        (Δ0.32, allowed 0.10)

1 of 3 calls regressed.
```

A green build means the change was safe to ship. A red build means you made the
agent slower or colder *before* a customer felt it.

Every run also uploads a per-call **HTML + JSON report** as a build artifact —
even on failure — so you can open the report and see exactly what moved.

## Inputs

| Input | Required | Default | What it does |
|---|---|---|---|
| `calls` | yes | — | Directory of golden call recordings to gate. |
| `baseline` | yes | `baseline.json` | The committed baseline to compare against. |
| `report-dir` | no | `audiotrace-report` | Where per-call HTML + JSON reports are written. |
| `version` | no | `audiotrace` | pip spec to pin AudioTrace (e.g. `audiotrace==1.2.2`). |
| `python-version` | no | `3.12` | Python version the gate runs on. |

## Tuning the tolerances

Conversational signals wiggle run to run, so the gate ships with sane per-metric
tolerances — a band the number can move within before it counts as a regression:

| Metric | Tolerance |
|---|---|
| Quality score | ±0.05 |
| Sentiment | ±0.10 |
| Response p95 | +15% |
| Cost | +20% |
| Interruptions | +1 |
| Frustration / drop-off / compliance | zero — any regression fails |

New recordings that aren't in the baseline yet are *skipped*, not failed, so
adding fixtures never breaks the build.

## Why this runs in CI at all

The trick that makes this practical: `audiotrace analyze()` runs locally on open
models (Whisper, pyannote, Librosa) — no hosted API, no key, no per-call bill. So
the gate needs nothing but your recordings and a runner. That's what lets it live
in `pull_request` CI instead of a nightly job behind a secret.

## Try it

- **Action:** [AudioTrace regression gate on the Marketplace](https://github.com/marketplace/actions/audiotrace-regression-gate)
- **Library:** `pip install audiotrace` · [github.com/dimastatz/audiotrace](https://github.com/dimastatz/audiotrace)

Point it at three recordings and a baseline, open a PR, and watch a bad prompt
change go red. That's regression testing for the part of your product that used
to be a black box.
