# AudioTrace: When the Right Tool Is the Simpler One

Dear signal-chasers,

A recording of a voice-AI call is one of the richest artifacts in modern
software. Hidden inside a single `.mp3` is the transcript, the customer's
mood, the awkward four-second silence, the moment the conversation went wrong,
and even what the call cost. Yet most teams treat that file as a black box.
They listen to a handful by hand and move on, because extracting those signals
means assembling speech recognition, speaker separation, audio analysis, a
sentiment model, and a pricing sheet — and then doing it all again at the next
company.

This matters most when the voice on the call is an AI agent rather than a
person. An AI agent's behavior isn't fixed: it shifts from one call to the next,
drifts as you tweak a prompt or swap a model, and surprises you in ways no test
suite anticipates. You can't manage what you can't see, so these conversations
have to be watched closely, one call at a time. If that agent were typing
instead of talking, you'd already have the instruments — LangChain to wire up
the chain, LangSmith to trace and grade each run, OpenTelemetry to fan spans out
to your dashboards. But the moment it speaks on a phone call, those tools see
tokens, not audio. AudioTrace is built to slot right into them rather than
replace them: because every call comes back as one structured, typed report, you
can emit it as OpenTelemetry spans, attach it to your LangChain and LangSmith
traces, or assert on it in a CI check that fails the build when a prompt change
makes the agent slower, colder, or less compliant. It gives the voice side the
same observability — and the same pre-deploy quality gate — you already expect
for text. And the very signals that reveal how the agent behaved — where it
stalled, where the caller grew frustrated, where it missed the intent — are the
examples you feed back in to fine-tune it. Detailed monitoring isn't just
oversight; it's the raw material for the next, better version of the agent.

Before getting to any tool, it helps to step back, because there are really two
ways to pull meaning out of audio, and a complete system needs both. One is
classical signal processing: deterministic math run directly on the waveform —
energy, pitch, the length of a silence. It is cheap, exact, needs no training
data, and it shines for physical questions. How long was the pause? How fast did
someone speak? Is the voice high or low? You measure the answer rather than
guess at it. The other is learned models: statistical systems like Whisper or a
sentiment classifier that have absorbed enormous amounts of data and estimate an
answer. They own everything that turns on meaning rather than physics — the
words, who is speaking, whether the caller is upset, what they intended — where
no hand-written rule survives the messiness of real speech.

Knowing which question belongs to which approach is most of the craft. Reach for
a model when you need to *estimate* meaning; reach for signal processing when you
can simply *measure* it. The two also reinforce each other — and, as you'll see
in a moment, when a model isn't available, a deterministic measurement can
sometimes stand in for it.

I kept seeing this duplicated effort, so I built a small open-source library
called AudioTrace. You hand it a call recording, and it hands back one
structured report: transcript, quality scores, sentiment, latency, cost, and
compliance flags. It splits along exactly that line — the acoustic layer
(silence, pace, pitch) is signal processing, and the semantic layer (transcript,
sentiment, intent) is models. The hope is modest but useful: that voice-AI teams
can stop rebuilding the same plumbing and spend their time on the product
instead.

I made one decision early that shaped everything: keep it all running locally.
No call audio leaves your machine. Speech recognition, speaker labeling, and
sentiment all run on open models you download once. For data as sensitive as
customer calls, I think privacy shouldn't be an upgrade you pay for. It should
be the default.

The clearest illustration of choosing between the two approaches came from a
small problem. To label who is speaking — the agent or the customer — the
obvious choice is a well-known model called pyannote. It's very good. It's also
gated: you need an account, a token, and to accept a license before it will run.
That's a fine ask for a production system, but it means a newcomer who just
wants to try the library gets a degraded result, with every speaker labeled
"unknown."

My first fix was a shortcut: assume the two speakers simply take turns. It was
wrong almost immediately. Speech recognizers split audio on sentences, not on
speakers, so the agent's multi-sentence greeting flip-flopped between "Agent"
and "Customer" line by line. I was tempted to reach for a bigger model to
rescue the situation.

Instead, I asked what signal was actually available. In a typical support call,
the agent and the customer often have noticeably different voice pitch. So I
measured the pitch of each segment with a standard audio library I already had,
and clustered the segments into two groups. The agent's sentences fell into one
group, the customer's into the other. A few dozen lines of code, no new
dependency, no token, and the labels came out right — a deterministic
measurement standing in for a model I couldn't use.

So what's the lesson I keep relearning? It isn't perfect: two speakers with
similar voices can fool the pitch trick, and when you do have a token, the
heavyweight model still does a better job. But for the common case, a simple,
well-understood technique beat reaching for something larger. We reach for the
biggest model out of habit, when a careful look at the data often points to
something lighter, cheaper, and easier to reason about. Estimate meaning with a
model; measure it with signal processing — and don't confuse the two.

There's a broader lesson here, too. A lot of progress in AI doesn't come from a
new model at all. It comes from packaging hard-won engineering into something
others can reuse — turning a week of glue code into a single `pip install`. That
kind of work rarely makes headlines, but it's how a field compounds. Every tool
we share is time given back to the next builder.

AudioTrace is early, and there's plenty left to do — pulling recordings directly
from telephony providers, breaking latency down stage by stage, richer
compliance checks. If you build voice agents, I'd love for you to try it, and
even more for you to improve it.

```bash
pip install audiotrace
```

Keep building!

Dima
