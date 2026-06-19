# AudioTrace Roadmap

High-level milestones and ordering. Each item links to its spec in
[`docs/prd/`](./prd/README.md). Granular tasks live in GitHub Issues, not here —
this file answers *what's next and in what order*.

## Phase 0 — Foundation

- [x] Repo scaffolding: packaging, `src/` layout, tests, CI, Docker
- [x] Public data contract: `CallReport` Pydantic models
- [x] Core `analyze()` pipeline (MediaInfo) — [PRD 0001](./prd/0001-mediainfo.md)

## Phase 1 — Single-call analysis (current)

- [x] Transcription + speaker diarization (Whisper + pyannote) — [PRD 0002](./prd/0002-transcript.md)
- [x] Quality signals (silence gaps, interruptions, pace, pitch — Librosa) — [PRD 0003](./prd/0003-quality.md)
- [x] Sentiment extraction (local Transformers) — [PRD 0004](./prd/0004-sentiment.md)
- [x] Cost attribution model
- [ ] Events extraction (outcome, drop-off, intent, compliance) — [PRD 0005](./prd/0005-events.md)
- [ ] Latency waterfall extraction — [PRD 0006](./prd/0006-latency.md)

## Phase 2 — Providers & Intelligence

- [ ] Provider adapters: Vapi, Retell, Twilio, Deepgram, ElevenLabs

## Phase 3 — Compliance & polish

- [ ] Compliance flag detection (PII, consent gaps)
- [ ] Custom webhook adapter
- [ ] Docs site + examples
