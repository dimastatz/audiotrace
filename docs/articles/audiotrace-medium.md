# Your Voice Agent Is a Black Box. I Built the Layer That Opens It.

### How I turned a raw call recording into a structured, queryable report — transcript, quality, sentiment, cost, and compliance — with everything running locally.

---

Every team building voice agents hits the same wall. You ship an AI that talks
to customers, and then someone asks the obvious questions:

- Was that call any good?
- Did the caller get frustrated?
- Where did the agent go quiet for four seconds?
- What did this conversation actually *cost* us?
- Did we read the consent disclosure?

The recording holds every answer. But a `.mp3` is opaque. To get anything out
of it you stitch together Whisper for transcription, pyannote for "who spoke
when," some DSP for silence and pace, a sentiment model, a pricing spreadsheet,
and a pile of glue code. Every team rebuilds this from scratch, slightly
differently, and none of it is reusable.

So I built **[AudioTrace](https://pypi.org/project/audiotrace/)** — an
open-source Python library that turns one call recording into one structured,
typed object. One function call in, a full `CallReport` out.

```python
import audiotrace

report = audiotrace.analyze("call.mp3")

report.transcript.turns        # who said what, with word-level timestamps
report.quality.overall_score   # 0.0–1.0
report.sentiment.caller_frustration
report.cost.total_usd
report.events.compliance_flags
```

```bash
pip install audiotrace
```

This post is about how it works, and the more interesting problems I ran into
building it.

---

## The contract comes first

The most important file in the project isn't an extractor — it's the data
model. `CallReport` is a Pydantic tree that every part of the pipeline fills in,
and that every consumer reads from. It is the *stable contract*: as long as the
shape holds, the internals can change freely.

```
CallReport
├── media       # duration, codec, sample rate, channels, bitrate
├── transcript  # full_text, turns[] (speaker · text · timing · words[]), language
├── quality     # score, interruptions, silence_gaps[], pace_wpm, pitch_variance
├── sentiment   # by_turn[], overall, shift_points[], caller_frustration
├── latency     # stt_ms, total_ms, waterfall[]
├── cost        # stt / llm / tts / telephony / total (USD)
└── events      # outcome, drop_off, intent_detected, compliance_flags[]
```

Designing the output before the implementation kept the project honest. Each
feature became "populate this section," not "invent a new shape."

---

## Principle: everything runs locally

The single biggest design decision was **no external API calls**. Transcription,
diarization, sentiment, intent — all of it runs on your machine with
open-weight models (Whisper, pyannote, Hugging Face Transformers) and classic
DSP (Librosa). Models download once and are cached; after that the library works
fully offline.

Why bother, when a cloud API would be less code?

- **Privacy.** Call recordings are some of the most sensitive data a company
  holds. Shipping them to a third party is a non-starter in healthcare,
  finance, and collections.
- **Cost.** Running 100k calls a day through paid speech APIs is its own budget
  line. Local inference is just compute you already have.
- **Reproducibility.** No silent model swaps behind an endpoint.

This constraint shaped everything that follows.

---

## The fun part: diarization without the gated model

Here's where it got interesting. The standard tool for speaker diarization —
figuring out which turns belong to the agent vs. the customer — is
`pyannote.audio`. It's excellent. It's also **gated**: you need a Hugging Face
token and have to accept a license before the weights will download.

That's fine for a configured production box, but it means the out-of-the-box
experience degrades to a single `"unknown"` speaker. For a two-party support
call, that's useless — and it quietly breaks everything downstream that depends
on knowing who spoke.

My first instinct was a cheap heuristic: assume speakers alternate, turn by
turn. It produced this:

```
AI Agent:  Thank you for calling Paradise Hotel.
Customer:  This is Aria, your virtual assistant.   ← wrong
AI Agent:  Please note this call may be recorded.
Customer:  How can I help you today?               ← wrong
```

Whisper splits on *sentences*, not *speakers*. The agent's greeting is four
segments, all the same person — but alternation flip-flops the label on every
one. And because the segments are back-to-back with no pauses, there's no timing
signal to fix it either. The only thing that can separate those sentences is the
**audio itself**.

So I added a fallback that doesn't need any gated model: **cluster each segment
by its voice pitch.** A female agent and a male customer sit in clearly
different fundamental-frequency bands. Extract each segment's median pitch with
Librosa's PYIN, run a tiny 1-D k-means over those pitches, and assign segments
to speakers by cluster:

```python
def _cluster_pitches(pitches, num_speakers):
    valid = [p for p in pitches if p is not None]
    if num_speakers < 2 or len(set(valid)) < 2:
        return [0] * len(pitches)
    centers = _kmeans_1d(valid, min(num_speakers, len(set(valid))))
    # assign each segment to its nearest pitch center;
    # silent segments inherit the previous speaker
    ...
```

Now the agent's four sentences land in one cluster, the customer's replies in
another, and a first-appearance mapping turns clusters into friendly labels —
`"AI Agent"`, `"Customer"`. It runs with zero new dependencies (Librosa was
already in the stack) and works with no token at all.

Is it perfect? No — it leans on speakers having distinguishable pitch, so
same-gender calls are its weak spot. With a token, pyannote still does the real
acoustic diarization. But as a free, offline default, pitch clustering took the
demo from "obviously broken" to "obviously right."

---

## Signals, end to end

With speakers sorted, the rest of the pipeline is a series of focused extractors,
each populating its slice of the report:

- **Quality** (Librosa): silence gaps over a threshold, interruption counts from
  overlapping turns, speaking pace in WPM, pitch variance as a proxy for vocal
  engagement, and a heuristic 0–1 score over all of it.
- **Sentiment** (Transformers): a local `distilbert` model scores each turn from
  −1 to +1, then derives an overall mean, *shift points* where the tone swings,
  and a `caller_frustration` flag from consecutive negative caller turns.
- **Events**: rule-based outcome classification (`completed` / `dropped` /
  `failed`), drop-off detection from trailing silence, **intent** via a local
  zero-shot classifier, and **compliance** flags — a missing recording-consent
  disclosure, or PII (SSN / card / email) caught by regex.
- **Cost**: a configurable `PricingTable` with sane public defaults (AWS
  Transcribe for STT, Polly Neural for TTS, GPT-4o-mini rates for the LLM). STT
  cost comes from duration, TTS from agent character count, LLM from a
  token estimate — all overridable.
- **Latency**: an agent-response *waterfall* derived purely from turn
  timestamps — for every caller→agent transition, how long before the agent
  replied.

Every module is small, independently testable, and degrades gracefully when an
input is missing.

---

## A demo that actually feels like a call

Numbers in a JSON blob don't sell a voice-AI tool. So the CLI has an
`--animate` mode that *plays the call back*: it starts the audio, and reveals
the transcript word by word, each word timed to when it's actually spoken.

That sync is the payoff of one upgrade: turning on Whisper's
`word_timestamps=True` and carrying per-word timing through the contract as a
`Word` model on each turn. The player schedules every word against a monotonic
clock started at playback, so the captions track the voice instead of crawling
at a fixed delay. Consecutive same-speaker turns collapse under a single label,
so it reads like a chat log, not a stutter.

```bash
./run.sh --animate
```

---

## Holding the bar

Because this is meant to be a dependency other people build on, the quality gate
is strict and non-negotiable:

- **Type-checked** end to end with `mypy --strict`.
- **Formatted and linted** with Ruff.
- **95%+ test coverage**, enforced in CI — most modules sit at 100%.

Heavy models are mocked in tests, so the suite runs in seconds and never touches
the network. One command — `./scripts/test_local.sh` — runs format, lint, types,
and tests, mirroring CI exactly.

Shipping a release is one command too. A `publish.sh` script runs the full
validation gate, builds the sdist and wheel, validates them with `twine check`,
and uploads to PyPI behind a confirmation prompt — because PyPI versions are
immutable and there's no undo.

---

## What's next

The single-call pipeline is the foundation. The roadmap from here:

- **Provider adapters** — pull recordings and metadata directly from Vapi,
  Retell, Twilio, Deepgram, and ElevenLabs.
- **Richer latency** — decompose response gaps into STT / LLM / TTS sub-spans
  when provider timing metadata is available.
- **More compliance rules** — beyond consent and basic PII.

If you're building voice agents and tired of rebuilding the same signal-
extraction glue, give it a try:

```bash
pip install audiotrace
```

It's MIT-licensed and open source. Contributions — especially provider adapters
and compliance rule sets — are very welcome.

*Built with Python, Whisper, pyannote, Librosa, and Transformers. No call audio
ever leaves your machine.*
