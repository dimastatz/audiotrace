# Test fixtures

Golden audio and other fixtures used by the test suite.

## `paradise_hotel_booking_60s.mp3`

A ~64-second synthetic customer-support call: an AI hotel agent ("Aria" at
Paradise Hotel, female voice) and a customer ("Mik Maclay", male voiqce) booking
a room for a vacation. Used as golden data for the media, transcription,
diarization, quality, sentiment, cost, latency, and events tests.

- **Format:** MP3, 48 kHz, stereo, 128 kbps, ~63.9 s (~1.0 MB)
- **Source:** fully synthetic — generated locally, no third-party audio.
  Voices rendered with [Kokoro](https://github.com/hexgrad/kokoro) TTS
  (Apache-2.0): `af_heart` (agent) and `am_michael` (customer), then encoded
  to MP3 with FFmpeg.
- **Provenance:** the dialogue is original and includes a recording-consent
  disclosure so the compliance check passes. Because it is synthetic and
  self-generated, it is unencumbered and safe to redistribute.

## `paradise_hotel_booking_60s.opus`

The same call encoded as Opus mono at 24 kbps (~178 KB) — ~5.7x smaller than
the MP3 with no perceptible loss for speech. Decodes natively through the
pipeline (FFmpeg/Whisper/librosa). Provided as a compact demo input; the test
suite's media/format assertions use the MP3 variant.
