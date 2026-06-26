# AudioTrace — Observability for Voice AI

Dear signal-chasers,

A recording of a voice-AI call is one of the richest artifacts in modern
software. Hidden inside a single `.mp3` is the transcript, the customer's mood,
the awkward four-second silence, the moment it all went wrong, and even what the
call cost. Yet most teams treat that file as a black box — they listen to a
handful by hand and move on, because prying those signals loose means bolting
together speech recognition, speaker separation, audio analysis, a sentiment
model, and a pricing sheet, then doing it all again at the next company.

This matters most when the voice on the call is an AI agent rather than a person.
An agent's behavior isn't fixed: it drifts as you tweak a prompt or swap a model,
and surprises you in ways no test suite anticipates. If it were typing instead of
talking, you'd already have the instruments — LangChain, LangSmith, OpenTelemetry
— tracing every run. But the moment it speaks on a phone call, those tools see
tokens, not audio. AudioTrace is built to slot in beside them, not replace them:
every call comes back as one structured, typed report you can emit as
OpenTelemetry spans, hang off your LangChain and LangSmith traces, or assert on
in a CI check that fails the build when a prompt change makes the agent slower,
colder, or less compliant. Those same signals — where it stalled, where the
caller soured, where it missed the intent — are also the examples you feed back
in to fine-tune it. Monitoring here isn't just oversight; it's the raw material
for the next, better agent.

It helps to step back, because there are really two ways to pull meaning out of
audio, and a complete system needs both. One is classical signal processing:
deterministic math run straight on the waveform — energy, pitch, the length of a
silence. It's cheap, exact, needs no training data, and it shines for physical
questions. How long was the pause? How fast did someone speak? Is the voice high
or low? You measure the answer rather than guess at it. The other is learned
models: statistical systems like Whisper or a sentiment classifier that have
swallowed enormous amounts of data and *estimate* an answer. They own everything
that turns on meaning rather than physics — the words, who's speaking, whether
the caller is upset — where no hand-written rule survives real speech. Most of
the craft is knowing which question belongs to which: reach for a model to
*estimate* meaning, for signal processing to *measure* it. And, as you'll see in
a moment, when a model isn't available, a measurement can sometimes stand in.

So I built a small open-source library, AudioTrace. You hand it a recording; it
hands back one report — transcript, quality, sentiment, latency, cost,
compliance — split along exactly that line: the acoustic layer (silence, pace,
pitch) is signal processing, the semantic layer (transcript, sentiment, intent)
is models. One early decision shaped everything else: it all runs locally. No
call audio leaves your machine; the open models download once. For data this
sensitive, privacy shouldn't be an upgrade you pay for — it should be the
default.

The clearest illustration came from a small problem: labeling who is speaking.
The obvious tool is a strong model called pyannote — but it's gated, needing an
account, a token, and a signed license before it runs. Fine for production, less
fine for a newcomer who just wants to try the library and instead gets every
turn labeled "unknown." My first shortcut — assume the two speakers simply take
turns — fell apart instantly: speech recognizers split on sentences, not
speakers, so the agent's multi-sentence greeting flip-flopped between "Agent" and
"Customer" line by line.

Instead, I asked what signal was actually there. In a typical support call, the
agent and the customer have noticeably different voice pitch. So I measured each
segment's pitch with an audio library I already had and clustered the segments
into two groups — the agent's sentences in one, the customer's in the other. A
few dozen lines, no new dependency, no token, and the labels came out right: a
plain measurement standing in for a model I couldn't use.

It isn't magic. Two similar voices can fool it, and with a token, pyannote still
does better. But for the common case, a simple, well-understood technique beat
reaching for something larger — and that's the lesson I keep relearning. We grab
the biggest model out of habit, when a careful look at the data often points to
something lighter, cheaper, and easier to reason about.

There's a broader lesson too. A lot of progress in AI doesn't come from a new
model at all; it comes from packaging hard-won engineering into something others
can reuse — turning a week of glue code into one `pip install`. That work rarely
makes headlines, but it's how a field compounds. Every tool we share is time
handed back to the next builder. AudioTrace is early — provider integrations,  
stage-by-stage, latency, and richer compliance checks are still to come.

```bash
pip install audiotrace
```

Keep building!

