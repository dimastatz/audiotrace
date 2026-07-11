# I Spent a Month Making AI Voice Agents Observable. Here's Everything I Wrote (and Built).

Dear signal-chasers,

When an AI agent *types*, you can see everything — LangChain traces each step,
LangSmith replays every run, OpenTelemetry hangs a span off every call. The moment
that same agent picks up a **phone**, the lights go out. Its entire interaction is
sealed inside an `.mp3`: the transcript, the caller's mood, the four-second
silence, the moment it talked over someone, the point the call went sideways. To
your observability stack, that file is opaque.

So I built **[AudioTrace](https://github.com/dimastatz/audiotrace)** — an
open-source Python library that turns a raw call recording into one structured,
typed `CallReport`: transcript, quality, sentiment, latency, cost, and events. And
I wrote a short series about the ideas behind it. This post is the map — read it,
then follow whichever thread pulls at you.

## The series

**1. [Your AI Voice Agent Is a Black Box. Here's How to Open It.](#)**
The mental model. What's actually recoverable from a single recording, and why
"listen to a few calls by hand" doesn't scale when an agent's behavior *drifts*
with every prompt tweak and model swap. The framing the rest of the series builds
on: there are two ways to pull meaning out of audio — **measure** it with signal
processing, or **estimate** it with a model — and a complete system needs both.

**2. [Measure, Don't Estimate: Labeling Speakers Without a Gated Model](#)**
A story about choosing the simpler tool. Diarization — figuring out who spoke —
usually means reaching for a gated, token-walled model. For the common
two-speaker call, a few dozen lines of pitch clustering give a zero-setup default
that Just Works, with the big model as an opt-in upgrade. Why the obvious
heuristic ("just alternate speakers") fails, and what to do instead.

**3. [Fail the Build When Your Voice Agent Gets Worse](#)**
The payoff. Treat a handful of golden recordings as test fixtures, analyze them on
every change, and assert on the report — so a prompt change that makes the agent
slower, colder, or less compliant turns the build red like any failing test. Plus
how to emit the same signals as OpenTelemetry spans, right next to your existing
traces.

**4. [A GitHub Action That Fails the Build When Your Voice Agent Gets Worse](#)**
The 15-minute version. Commit a baseline of golden calls, drop one Action into
your workflow, and you have a CI gate on call quality — no boilerplate, no
secrets, no API calls.

## The tools

**[AudioTrace regression gate — on the GitHub Marketplace](https://github.com/marketplace/actions/audiotrace-regression-gate).**
Point it at a folder of recordings and a committed baseline; it fails the build
when quality regresses — latency, sentiment, drop-off, cost, or compliance — and
uploads a per-call HTML report as an artifact.

```yaml
- uses: dimastatz/audiotrace@v1
  with:
    calls: tests/calls
    baseline: baseline.json
```

**[The library](https://github.com/dimastatz/audiotrace).** One call, one report:

```python
import audiotrace

report = audiotrace.analyze("call_recording.wav", num_speakers=2)
print(report.quality.overall_score)         # 0.87
print(report.sentiment.caller_frustration)  # False
print(report.latency.llm_first_token_ms)    # 420
print(report.cost.total_usd)                # 0.063
```

It runs locally on open models (Whisper, pyannote, Librosa) — no hosted API, no
key, no per-call bill — which is exactly what lets it live inside CI.

## Why this matters

An agent's behavior isn't fixed; it drifts. Monitoring here isn't just oversight —
the same signals that catch a regression (where it stalled, where the caller
soured, where it missed the intent) are the examples you feed back in to fine-tune
the next, better agent.

If any of that resonates, the fastest way in is `pip install audiotrace`, point it
at three recordings, open a PR, and watch a bad prompt change go red.

⭐ **[Star the repo](https://github.com/dimastatz/audiotrace)** if you want to
follow along — it's early, and feedback is shaping what gets built next.

*— and happy signal-chasing.*
