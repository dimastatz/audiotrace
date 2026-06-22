# When the Right Tool Is the Simpler One

*Written in the spirit of Andrew Ng's letters in The Batch.*

Dear friends,

A recording of a voice-AI call is one of the richest artifacts in modern
software. Hidden inside a single `.mp3` is the transcript, the customer's
mood, the awkward four-second silence, the moment the conversation went wrong,
and even what the call cost. Yet most teams treat that file as a black box.
They listen to a handful by hand and move on, because extracting those signals
means assembling speech recognition, speaker separation, audio analysis, a
sentiment model, and a pricing sheet — and then doing it all again at the next
company.

This matters most when an AI agent, rather than a person, is the one on the
call. A human follows a script in roughly predictable ways. An AI agent does
not — its behavior shifts from call to call, drifts as you change a prompt or a
model, and surprises you in ways no test suite anticipates. You can't manage
what you can't see, so these conversations need to be monitored in detail, one
call at a time. And the same signals that tell you how the agent behaved —
where it stalled, where the caller grew frustrated, where it missed the intent —
are exactly the examples you feed back in to fine-tune and improve it. Detailed
monitoring isn't only oversight; it's the raw material for the next, better
version of the agent.

I kept seeing this duplicated effort, so I built a small open-source library
called AudioTrace. You hand it a call recording, and it hands back one
structured report: transcript, quality scores, sentiment, latency, cost, and
compliance flags. The hope is modest but useful — that voice-AI teams can stop
rebuilding the same plumbing and spend their time on the product instead.

I made one decision early that shaped everything: keep it all running locally.
No call audio leaves your machine. Speech recognition, speaker labeling, and
sentiment all run on open models you download once. For data as sensitive as
customer calls, I think privacy shouldn't be an upgrade you pay for. It should
be the default.

But the lesson I most want to share came from a smaller problem.

To label who is speaking — the agent or the customer — the obvious choice is a
well-known model called pyannote. It's very good. It's also gated: you need an
account, a token, and to accept a license before it will run. That's a fine
ask for a production system, but it means a newcomer who just wants to try the
library gets a degraded result, with every speaker labeled "unknown."

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
dependency, no token — and the labels came out right.

It isn't perfect. Two speakers with similar voices can fool it, and when you do
have a token, the heavyweight model still does a better job. But for the common
case, a simple, well-understood technique beat reaching for something larger. I
find this happens more often than we expect. We reach for the biggest model out
of habit, when a careful look at the data points to something lighter, cheaper,
and easier to reason about.

There's a broader pattern here, too. A lot of progress in AI doesn't come from a
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
