# AudioTrace

**CI/CD for voice AI.** Drop in a call recording and get back a structured
[`CallReport`](reference/callreport.md): transcript with speakers, quality,
sentiment, response latency, estimated cost, outcome, and located compliance
findings. Then gate releases on it.

```python
import audiotrace

report = audiotrace.analyze("call.wav", num_speakers=2)
print(report.quality.overall_score)       # 0.0–1.0
print(report.sentiment.caller_frustration)
print(report.events.compliance_flags)     # e.g. ["pii_exposed"]
```

Everything runs locally (Whisper, pyannote, Librosa, Transformers). No audio
leaves your machine unless you use a hosted backend yourself, such as Claude
for [simulated callers](guides/simulated-callers.md).

## What you can do with it

- **Gate releases** on a folder of golden calls: per-call tolerances plus a
  run-level distribution check — [Regression gate](guides/regression-gate.md).
- **Flag compliance issues**: missing recording disclosure, PII said on the
  call, each located to a turn — [Compliance checks](guides/compliance.md).
- **Pull calls from Vapi, Retell, Twilio**, or any stack via a webhook mapping
  — [Providers and webhooks](guides/providers.md).
- **Test before release** with simulated callers — [Simulated callers](guides/simulated-callers.md).
- **Turn production failures into tests**, PII-redacted — [Production replay](guides/production-replay.md).

See [Status](status.md) for what is shipped and what isn't.
