# Getting started

## Install

```bash
pip install audiotrace
```

AudioTrace needs **Python 3.9+** and **FFmpeg** on the system path
(`brew install ffmpeg`, `apt-get install ffmpeg`). Models (Whisper, the
sentiment and intent classifiers) download on first use and are cached.

### Speaker diarization

For the best speaker separation, AudioTrace uses
[pyannote](https://huggingface.co/pyannote/speaker-diarization-3.1), a gated
model: accept its terms on Hugging Face and set `HF_TOKEN`. Without a token,
speakers are separated by voice pitch instead (`provenance.diarization ==
"pitch"`), which works for two clearly different voices; see
[Pricing and speaker labels](guides/pricing-and-speakers.md).

## Analyze a first call

The repository ships a 64-second synthetic hotel-booking call:

```python
import audiotrace

report = audiotrace.analyze("tests/fixtures/paradise_hotel_booking_60s.mp3", num_speakers=2)

for turn in report.transcript.turns:
    print(f"{turn.speaker}: {turn.text}")

print("quality", report.quality.overall_score)
print("agent response gaps", [s.duration_ms for s in report.latency.waterfall])
print("outcome", report.events.outcome, "intent", report.events.intent_detected)
print("compliance", report.events.compliance_flags)
```

`num_speakers=2` labels the speakers `AI Agent` and `Customer` in order of
appearance; pass `speaker_labels=[...]` to choose your own.

## Read the report

```python
audiotrace.write_report(report, "out/")   # out/report.json + out/report.html
```

The HTML page is self-contained: summary tiles, the transcript as a chat with
timestamps, the latency waterfall, and compliance findings linked to their
turns. Every field is described in the [CallReport reference](reference/callreport.md).

## Next

Gate a folder of calls in CI: [Regression gate](guides/regression-gate.md).
