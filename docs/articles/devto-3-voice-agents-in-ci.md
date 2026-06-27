---
title: "Fail the Build When Your Voice Agent Gets Worse"
published: false
description: "Voice agents regress in ways no unit test catches — slower, colder, less compliant. Here's how to assert on call quality in CI and emit the signals as OpenTelemetry spans next to your LangChain/LangSmith traces."
tags: ai, python, testing, opensource
series: Observability for AI Voice Agents
cover_image: https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/articles/audiotrace-flow.png
---

In this series we've turned a raw call recording into a structured `CallReport`
([post 1](#)) and looked at how to extract signals cheaply enough to run on every
call ([post 2](#)). Now the payoff: **using those signals to stop regressions
before they ship.**

A voice agent's behavior drifts. You change a prompt, swap a model, pick a new TTS
voice — and the agent gets subtly slower to respond, colder in tone, or starts
skipping a required disclosure. None of that shows up in a normal test suite,
because the regression lives in the audio. So let's put the audio in the test
suite.

## The idea: golden recordings as test fixtures

Treat a small set of representative call recordings as fixtures. On every change,
analyze them and assert on the report. If a prompt change pushes a number past a
threshold, the build goes red — same as any other failing test.

```python
import audiotrace
import pytest

# A few representative calls checked into the repo (or pulled from storage).
GOLDEN_CALLS = [
    "tests/calls/happy_path.wav",
    "tests/calls/frustrated_customer.wav",
    "tests/calls/compliance_heavy.wav",
]


@pytest.mark.parametrize("path", GOLDEN_CALLS)
def test_call_quality_does_not_regress(path):
    report = audiotrace.analyze(path, num_speakers=2)

    # Latency: the agent must stay responsive.
    assert report.latency.total_ms < 6000, "agent got too slow"

    # Quality: overall score must stay healthy.
    assert report.quality.overall_score >= 0.80

    # The agent shouldn't be talking over the caller.
    assert report.quality.interruptions <= 2


def test_required_disclosure_present():
    report = audiotrace.analyze("tests/calls/compliance_heavy.wav")
    # Compliance flags surface missing/again-required disclosures.
    assert "missing_disclosure" not in report.events.compliance_flags


def test_agent_does_not_frustrate_callers():
    report = audiotrace.analyze("tests/calls/happy_path.wav")
    assert report.sentiment.caller_frustration is False
    assert report.sentiment.overall >= 0.0  # net-neutral-or-better tone
```

Because `analyze()` runs locally with no API calls, this works in CI with no
secrets and no network — the recordings and the open models are all you need.

## Catching drift, not just hard failures

Absolute thresholds catch cliffs. To catch *drift*, compare against a baseline you
commit alongside the code:

```python
import json
import audiotrace

def snapshot(path):
    r = audiotrace.analyze(path, num_speakers=2)
    return {
        "pace_wpm": r.quality.speaking_pace_wpm,
        "overall": r.quality.overall_score,
        "latency_ms": r.latency.total_ms,
        "sentiment": r.sentiment.overall,
    }

def test_no_drift_from_baseline():
    baseline = json.load(open("tests/baseline.json"))
    current = snapshot("tests/calls/happy_path.wav")

    # Latency may not grow more than 15% vs. the committed baseline.
    assert current["latency_ms"] <= baseline["latency_ms"] * 1.15
    # Tone may not drop more than 0.1 absolute.
    assert current["sentiment"] >= baseline["sentiment"] - 0.1
```

When you intentionally improve the agent, you regenerate `baseline.json` and
commit it — the same workflow as snapshot testing.

## Emit it as OpenTelemetry spans

CI catches regressions before they ship; observability catches what happens in
production. The `CallReport` maps cleanly onto OpenTelemetry, so voice-call
signals sit right next to the rest of your traces:

```python
from opentelemetry import trace
import audiotrace

tracer = trace.get_tracer("audiotrace")

def trace_call(path: str):
    report = audiotrace.analyze(path)
    with tracer.start_as_current_span("voice_call") as span:
        span.set_attribute("call.duration_ms", report.media.duration_ms)
        span.set_attribute("call.quality_score", report.quality.overall_score)
        span.set_attribute("call.caller_frustrated", report.sentiment.caller_frustration)
        span.set_attribute("call.cost_usd", report.cost.total_usd)
        span.set_attribute("call.outcome", report.events.outcome)

        # The latency waterfall becomes child spans (STT, LLM, TTS, ...).
        for stage in report.latency.waterfall:
            child = tracer.start_span(stage.name, start_time=stage.start_ms)
            child.end()
    return report
```

## Hang it off your LangChain / LangSmith traces

If you already trace your agent's reasoning in LangSmith, AudioTrace fills in the
half it can't see — what actually reached the caller's ear. Attach the report to
the run as metadata so the audio signals live next to the token-level trace:

```python
from langsmith import Client
import audiotrace

client = Client()

def attach_audio_signals(run_id: str, recording: str):
    report = audiotrace.analyze(recording)
    client.update_run(
        run_id,
        extra={
            "audio": {
                "quality_score": report.quality.overall_score,
                "caller_frustration": report.sentiment.caller_frustration,
                "speaking_pace_wpm": report.quality.speaking_pace_wpm,
                "drop_off": report.events.drop_off,
                "total_cost_usd": report.cost.total_usd,
            }
        },
    )
```

Now a single LangSmith run shows both what the model *thought* and how the call
*sounded* — and the same signals that flag a bad call in production are the
examples you feed back in to fine-tune the next, better agent.

## Wrapping the series

Three ideas, one thread:

1. A voice call is a rich artifact your token-level tooling can't read — so turn
   it into a typed `CallReport`.
2. Split the work by **measure vs. estimate**, and don't reach for a big model
   when a cheap measurement will do.
3. Put those signals where they pay off: **red builds** on regressions and
   **spans/traces** in production.

A lot of progress in AI isn't a new model — it's packaging hard-won engineering
into something others can `pip install`. That's what AudioTrace is trying to be
for voice agents.

```bash
pip install audiotrace
```

⭐ Repo: [github.com/dimastatz/audiotrace](https://github.com/dimastatz/audiotrace) —
it's early, and provider integrations + richer compliance checks are exactly where
contributions help most.

Keep building!
