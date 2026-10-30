# Golden call set

Twenty synthetic two-party calls (about 19 minutes in total, ~3 MB of Opus)
for the regression gate ([PRD 0008](../../../docs/prd/0008-regression-gate.md))
and distributional drift checks ([PRD 0009](../../../docs/prd/0009-drift-gating.md)).

```
scenarios/<id>.yaml   # the script: voices, line condition, turns, timing, expected signals
calls/<id>.opus       # the rendered call: mono, 24 kbps Opus
baseline.json         # `audiotrace baseline` output for calls/
```

## Provenance and license

Fully synthetic and self-generated, like the existing `paradise_hotel_booking_60s`
fixture: original dialogue, voiced with [Kokoro](https://github.com/hexgrad/kokoro)
TTS (Apache-2.0), mixed and encoded with FFmpeg. Names, card numbers, SSNs, and
email addresses in the scripts are fake (test card `4111…`, SSN `123-45-6789`,
`example.com`). Safe to redistribute under the repository's MIT license.

## Coverage

Four calls per intent label (`billing`, `technical support`, `sales`,
`cancellation`, `general inquiry`). Most calls are for "Brightline", a
fictional internet and mobile provider; `sales_04` is a hotel booking.
Defects are planted on purpose, and each scenario's `expect` block records the
ground truth:

| Planted signal | Calls |
|---|---|
| No recording disclosure | `billing_04`, `sales_03`, `inquiry_02` |
| PII read out (card, email, SSN) | `billing_03`, `sales_02`, `cancel_03` |
| Frustrated caller | `billing_02`, `support_03`, `cancel_02` |
| Barge-in (caller talks over agent) | `support_02`, `cancel_02`, `inquiry_04` |
| Slow agent (2.5–4 s replies) | `billing_04`, `support_04`, `inquiry_02` |
| Dropped call | `support_03`, `cancel_04` |
| Phone line (300–3400 Hz band-pass) | `billing_03`, `support_01`, `cancel_03`, `inquiry_03` |
| Background noise | `support_03`, `sales_04`, `inquiry_04` |

Voices vary across calls (American and British, both genders, agent and caller
of opposite genders in most calls).

## Regenerating

```bash
brew install espeak-ng                     # macOS; see the script's docstring
python3.12 -m venv .venv-golden            # Kokoro supports Python <= 3.12
.venv-golden/bin/pip install "kokoro>=0.9" soundfile pyyaml
.venv-golden/bin/python scripts/gen_golden.py           # all calls
.venv-golden/bin/python scripts/gen_golden.py sales_02  # one call
```

Rendering is seeded from the scenario id, so re-running on the same machine
produces byte-identical files. After changing a scenario, re-render it and
re-baseline:

```bash
audiotrace baseline tests/fixtures/golden/calls -o tests/fixtures/golden/baseline.json
```

The committed baseline was produced **without** a HuggingFace token, so speakers
are separated by the pitch-clustering fallback (`provenance.diarization ==
"pitch"`), matching CI. Running with `HF_TOKEN` set uses pyannote instead, and
`audiotrace check` will report that stack change.

## What AudioTrace currently gets right

Scoring AudioTrace 1.3.0 (pitch fallback, `num_speakers=2`, as the CLI runs it)
against the `expect` blocks:

| Signal | Correct | Misses and why |
|---|---|---|
| Consent disclosure | 20/20 | — |
| Dropped call | 20/20 | — |
| PII | 18/20 | Whisper writes the SSN as `12340-56789` and the email as "Jordan Lay at Example Com", which the regexes don't match ([PRD 0013](../../../docs/prd/0013-compliance-detection.md)) |
| Barge-in present | 17/20 | Interruptions are counted from overlapping turns, but Whisper segments never overlap on mono audio, so it's always 0 |
| Frustrated caller | 10/20 | All 3 frustrated calls are caught, but 10 calm ones are flagged too: the SST-2 sentiment model scores neutral questions ("what time does the store close?") near −1, and Whisper often splits one sentence into two turns, so "two negative caller turns in a row" fires easily. No streak length separates the classes on this set (3 in a row: 3/3 caught, 5 false alarms; 4: 2/3, none) — it needs a better model, not a tuned threshold |
| Intent | 12/20 | Most sales and support calls read as `general inquiry` |
| Latency waterfall | 81 spans in 20 calls | — |

Speakers collapse to one in 3 calls (`support_02`, `support_04`, `inquiry_03`)
because the voices' pitch ranges overlap too much for the fallback.

These numbers describe the extractors, not the calls. Re-baseline after fixing
any of them; the drift note from `audiotrace check` will show the stack change.
