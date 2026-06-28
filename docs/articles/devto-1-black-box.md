---
title: "Your AI Voice Agent Is a Black Box. Here's How to Open It."
published: true
description: "LangChain and LangSmith trace your agent when it types. The moment it speaks on a phone call, they see tokens, not audio. Here's how to get structured signals out of a raw recording."
tags: ai, python, opensource, machinelearning
series: Observability for AI Voice Agents
cover_image: https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/articles/audiotrace-flow.png
---

When your AI agent types, you can see everything it does. LangChain traces every
step, LangSmith replays every run, OpenTelemetry hangs spans off each call. You
know what the model saw, what it said, how long it took, and what it cost.

The moment that same agent picks up a phone, the lights go out.

A voice agent's entire interaction lives inside an `.mp3`. The transcript, the
customer's mood, the awkward four-second silence, the moment it talked over the
caller, the point where the conversation went sideways — all of it is in there.
But to your existing observability stack, that file is opaque. LangSmith sees the
tokens you fed the LLM; it does not see the audio that reached a human ear.

So most teams do the only thing they can: they listen to a handful of calls by
hand and hope the sample is representative. That doesn't scale, and it misses the
thing that makes voice agents hard — **their behavior drifts.** You tweak a
prompt, swap a model, change a TTS voice, and the agent gets subtly slower,
colder, or starts missing intents. No unit test catches it, because the
regression lives in the audio.

This series is about closing that gap. In this first post I'll lay out the mental
model; the next two get hands-on with a tricky signal-extraction problem and with
wiring voice signals into CI.

## The artifact is richer than you think

Here's what's actually recoverable from a single call recording:

- **Transcript** — what was said, by whom, with timestamps.
- **Quality** — silence gaps, interruptions, speaking pace, pitch variance.
- **Sentiment** — the caller's mood, and where it shifted.
- **Latency** — how long each stage (STT, LLM, TTS) took to respond.
- **Cost** — what the call cost, attributed per stage.
- **Events** — the detected intent, whether the caller dropped off, compliance flags.

That's a lot of signal locked inside one file. The reason teams rebuild this from
scratch at every company is that prying it loose means bolting together speech
recognition, speaker separation, audio analysis, a sentiment model, and a pricing
sheet — and then maintaining all of it.

## Two ways to pull meaning out of audio

The key insight that makes this tractable: there are really **two different
kinds of question** you can ask of audio, and they want two different tools.

**1. Measure it — classical signal processing.** Deterministic math run straight
on the waveform: energy, pitch, the length of a silence. Cheap, exact, no
training data. It shines for physical questions:

- How long was the pause?
- How fast did someone speak?
- Is this voice high-pitched or low?

You *measure* the answer instead of guessing at it.

**2. Estimate it — learned models.** Statistical systems like Whisper or a
sentiment classifier that have ingested enormous amounts of data and *estimate*
an answer. They own everything that turns on meaning rather than physics:

- What words were said?
- Who is speaking?
- Is the caller upset?

No hand-written rule survives real speech here — you need a model.

Most of the craft is knowing which question belongs to which bucket: reach for a
model to **estimate meaning**, for signal processing to **measure physics**. (In
the next post you'll see that when a model isn't available, a measurement can
sometimes stand in for it — that turns out to be a surprisingly useful trick.)

## One report, split along that line

I packaged this into a small open-source library called
[AudioTrace](https://github.com/dimastatz/audiotrace). You hand it a recording;
it hands back one structured, typed report — split along exactly that
measure-vs-estimate line. The acoustic layer (silence, pace, pitch) is signal
processing; the semantic layer (transcript, sentiment, intent) is models.

```bash
pip install audiotrace
```

```python
import audiotrace

report = audiotrace.analyze(
    audio="call_recording.wav",
    metadata={"agent_version": "v2.1", "provider": "vapi"},
)

print(report.quality.overall_score)        # 0.87
print(report.quality.speaking_pace_wpm)     # 168.0
print(report.sentiment.caller_frustration)  # False
print(report.latency.total_ms)              # 4200
print(report.events.drop_off)               # False
print(report.cost.total_usd)                # 0.063
```

The return value is a Pydantic `CallReport`, so it's typed, validated, and trivial
to serialize. You can emit it as OpenTelemetry spans, hang it off your LangChain
and LangSmith traces, or assert on it in a CI check — which is exactly where this
series is headed.

## One decision shaped everything: it runs locally

Call recordings are about as sensitive as data gets. So AudioTrace runs entirely
on your machine — no audio leaves the box, and the open models download once.
Privacy here shouldn't be an upgrade you pay for; it should be the default.

## What's next

The two-layer model sounds tidy, but the interesting part is what happens when
the "right" tool isn't available. In the next post I'll walk through a concrete
example: labeling **who is speaking** without the gated model everyone reaches
for — and why a few dozen lines of pitch measurement beat it for the common case.

If you want to poke at it now:

```bash
pip install audiotrace
```

⭐ The repo is at [github.com/dimastatz/audiotrace](https://github.com/dimastatz/audiotrace).
Issues and PRs welcome — it's early, and provider integrations are exactly the
kind of contribution that helps most.

Keep building!
