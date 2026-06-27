---
title: "Measure, Don't Estimate: Labeling Speakers Without a Gated Model"
published: false
description: "Diarization usually means a gated, token-walled model. For the common two-speaker call, a few dozen lines of pitch clustering beat reaching for the big model. A story about choosing the simpler tool."
tags: ai, python, machinelearning, opensource
series: Observability for AI Voice Agents
cover_image: https://raw.githubusercontent.com/dimastatz/audiotrace/main/docs/articles/audiotrace-flow.png
---

In [the first post](#) I argued there are two ways to pull meaning out of audio:
**measure** it with signal processing, or **estimate** it with a model. This post
is the story of a problem where the obvious move was to estimate — and where
measuring turned out to be better.

The problem: **labeling who is speaking.** A transcript that says "Agent: …" and
"Customer: …" is far more useful than an undifferentiated wall of text. Splitting
a conversation by speaker is called *diarization*.

## The obvious tool, and why it hurt

The strong, well-known tool for diarization is
[pyannote](https://github.com/pyannote/pyannote-audio). It's genuinely good. It
is also **gated**: to run it you need a Hugging Face account, an access token, and
to accept a license agreement before the weights will download.

That's fine for a production deployment. It's a terrible first impression for
someone who just `pip install`-ed your library and wants to see it work. Without a
token, every single turn comes back labeled `"unknown"`. The newcomer's first run
is a wall of `unknown: …` and they bounce.

So I wanted a *default* path that works with zero setup, and lets you opt into
pyannote when you have a token and want the best quality.

## Shortcut #1: just alternate speakers (this fails)

My first instinct was the dumbest possible heuristic: in a two-party call, the
speakers take turns, so just alternate `Agent`, `Customer`, `Agent`, `Customer`…

It fell apart immediately. Speech recognizers like Whisper segment on
**sentences**, not **speakers**. So the agent's multi-sentence greeting —

> "Hi there! Thanks for calling. How can I help you today?"

— gets split into three segments, and the naive alternator flip-flops the label
mid-utterance:

```
Agent:    Hi there!
Customer: Thanks for calling.
Agent:    How can I help you today?
```

Garbage. The structure I assumed (one segment per speaker turn) simply isn't there.

## Shortcut #2: ask what signal is actually present

Instead of forcing a model-shaped solution, I asked: *what's physically in the
audio that distinguishes these two speakers?*

In a typical support call, the agent and the customer have **noticeably
different voice pitch**. That's a physical property of the waveform — exactly the
kind of thing signal processing measures cheaply and exactly.

So the approach becomes:

1. For each transcribed segment, **measure its average pitch** (fundamental
   frequency) using an audio library I already had as a dependency.
2. **Cluster** the segments into two groups by pitch.
3. The low-pitch cluster is one speaker, the high-pitch cluster is the other.

The core of it is just a measurement plus a 2-way split:

```python
import librosa
import numpy as np

def segment_pitch(y: np.ndarray, sr: int) -> float:
    """Mean fundamental frequency (Hz) of one transcript segment."""
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=float(librosa.note_to_hz("C2")),
        fmax=float(librosa.note_to_hz("C7")),
        sr=sr,
    )
    voiced = f0[voiced_flag]
    return float(np.nanmean(voiced)) if voiced.size else 0.0


def assign_speakers(pitches: list[float], labels=("AI Agent", "Customer")):
    """Split segments into two speakers by a pitch threshold."""
    valid = [p for p in pitches if p > 0]
    if not valid:
        return ["unknown"] * len(pitches)
    threshold = float(np.median(valid))
    # Lower-pitched cluster -> first label, higher -> second.
    return [
        labels[0] if (p > 0 and p <= threshold) else
        labels[1] if p > 0 else "unknown"
        for p in pitches
    ]
```

A few dozen lines. No new dependency. No token. And the labels come out right for
the common case — a plain *measurement* standing in for a *model* I couldn't
assume the user had.

## It isn't magic — and that's the point

Two similar voices (two men, two women, a deep-voiced customer) can fool the pitch
split. With a token, pyannote still does better, and it handles three-plus
speakers, overlapping speech, and edge cases this never will. So AudioTrace keeps
both paths:

```python
import audiotrace

# Default: zero-setup, infer speakers by pitch.
report = audiotrace.analyze("call.wav", diarize=False, num_speakers=2)

# Best quality: opt into pyannote with a token.
report = audiotrace.analyze("call.wav", hf_token="hf_...")
```

The lesson I keep relearning: **we grab the biggest model out of habit.** A
careful look at the data often points to something lighter, cheaper, and easier
to reason about. "What signal is actually there?" is a more useful question than
"which model should I download?"

That's also a practical observability principle. The cheap, deterministic
measurement runs in milliseconds with no GPU, which means you can run it on
*every* call — and the things you can afford to run on every call are the things
that actually catch regressions.

## What's next

We now have a structured `CallReport` with speakers, quality, sentiment, latency,
and cost. In the final post I'll wire it into CI: **fail the build when a prompt
change makes the agent slower, colder, or less compliant**, and emit the signals
as OpenTelemetry spans alongside your LangChain / LangSmith traces.

```bash
pip install audiotrace
```

⭐ Repo: [github.com/dimastatz/audiotrace](https://github.com/dimastatz/audiotrace)

Keep building!
