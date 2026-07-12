# Making AI Voice Agents Observable: Notes for the Teams Shipping Them

When an AI agent *types*, its whole life is visible. LangChain traces each step,
LangSmith replays every run, OpenTelemetry hangs a span off every call. The moment
that same agent picks up a **phone**, most of that visibility disappears. The
interaction is sealed inside an `.mp3`: the transcript, the caller's mood, the
four-second silence, the moment it talked over someone, the point the call went
sideways. To the tools your team already relies on, that file is opaque.

That opacity lands on two people. The **developer** instrumenting the agent can't
put a phone call in a test the way they'd test any other output. The **product
manager** accountable for call quality is left listening to a handful of calls by
hand and hoping the sample is representative — with no reliable way to tell whether
last week's prompt change made things quietly worse.

Over the past few weeks I wrote a short series working through that gap, and built
an open-source library —
[AudioTrace](https://github.com/dimastatz/audiotrace) — that turns a raw call
recording into one structured, typed report: transcript, quality, sentiment,
latency, cost, and events. This post is a map of the series, so you can follow the
threads that matter to your role.

## The series

**1. [Your AI Voice Agent Is a Black Box. Here's How to Open It.](#)**
The mental model, and the most PM-friendly place to start. What's actually
recoverable from a single recording, and why "listen to a few calls by hand"
breaks down once an agent's behavior *drifts* with every prompt tweak and model
swap. Underneath it all: two ways to pull meaning out of audio — **measure** it
with signal processing, or **estimate** it with a model — and why a complete
picture needs both.

**2. [Measure, Don't Estimate: Labeling Speakers Without a Gated Model](#)**
A more hands-on, engineering-flavored post about a single decision: how to tell
who's speaking. The usual approach reaches for a heavyweight, token-gated model;
for the common two-speaker call, a much simpler measured approach turns out to be
the better default. A useful case study in resisting the obvious tool.

**3. [Fail the Build When Your Voice Agent Gets Worse](#)**
Where the two audiences meet. Treat a handful of representative recordings as
fixtures, and a change that makes the agent slower, colder, or less compliant can
fail a build the same way a broken feature does — a quality bar the whole team can
point to, expressed as something engineering can enforce.

**4. [A GitHub Action That Fails the Build When Your Voice Agent Gets Worse](#)**
The practical version of post 3: commit a baseline of known-good calls, add one
step to a workflow, and quality regressions show up in a pull request instead of a
customer complaint.

## What it looks like in practice

For a developer, the whole library is one call and one report:

```python
import audiotrace

report = audiotrace.analyze("call_recording.wav", num_speakers=2)
print(report.quality.overall_score)         # 0.87
print(report.sentiment.caller_frustration)  # False
print(report.latency.llm_first_token_ms)    # 420
print(report.cost.total_usd)                # 0.063
```

For a team that wants a quality gate without writing much, there's a
[GitHub Action](https://github.com/marketplace/actions/audiotrace-regression-gate)
that compares each release against a committed baseline and surfaces what moved:

```yaml
- uses: dimastatz/audiotrace@v1
  with:
    calls: tests/calls
    baseline: baseline.json
```

It runs locally on open models (Whisper, pyannote, Librosa) — no hosted API and no
per-call cost — which is what makes it reasonable to run on every change rather
than in an occasional manual review.

## Why it's worth the attention

An agent's behavior isn't fixed; it drifts. Making that drift visible is partly
about catching regressions before customers feel them — and partly about the
feedback loop. The same signals that flag a bad release (where it stalled, where
the caller soured, where it missed the intent) are the examples a team feeds back
in to improve the next version.

If any of this is a problem you recognize, the series linked above is the fuller
argument, and the [repository](https://github.com/dimastatz/audiotrace) is the
place to see how it fits your stack. It's early and actively evolving, so notes
from teams actually running voice agents are especially welcome.
